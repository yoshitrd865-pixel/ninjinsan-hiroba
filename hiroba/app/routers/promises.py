"""
遊ぶ約束（プロミス）APIルーター（ひろば）

キッズ同士が「公園で遊ぼう」「ゲームしよう」などの遊ぶ約束をした際、
AIお兄さん・お姉さんが会話やボイスメモの内容から約束の要点
（タイトル・日時・場所）を抽出してPromiseを作成する。

安全のため、約束は双方の保護者が承認するまで「成立」しない。
- POST /api/promises/create               : キッズが約束を提案する
- POST /api/promises/{id}/parent-response : 保護者が承認/拒否する
- GET  /api/promises/my-promises          : 自分に関わる約束一覧を取得する
- GET  /api/promises/other-kids           : 約束の相手を選ぶためのキッズ一覧を取得する
"""

import datetime as dt
import uuid
from pathlib import Path


from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import get_active_user, get_current_parent
from app.database import get_db
from app.models import Promise, User
from app.paths import UPLOAD_DIR
from app.services.promise_ai import extract_promise_details
from app.services.whisper_service import transcribe_audio

router = APIRouter(prefix="/api/promises", tags=["promises"])

_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d")


def _parse_datetime(value: str | None) -> dt.datetime | None:
    """AIが返した日時文字列を datetime に変換する（不明な形式なら None）"""
    if not value:
        return None
    value = str(value).strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _save_voice_memo(file: UploadFile, prefix: str) -> tuple[str, Path]:
    """約束提案時のボイスメモを保存し、(公開URL, 実ファイルパス) を返す"""
    ext = "bin"
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()

    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    dest_path = UPLOAD_DIR / filename
    with dest_path.open("wb") as buffer:
        buffer.write(file.file.read())

    return f"/static/uploads/{filename}", dest_path


def _serialize_promise(promise: Promise) -> dict:
    return {
        "id": promise.id,
        "sender_kid_id": promise.sender_kid_id,
        "sender_kid_name": promise.sender_kid.display_name if promise.sender_kid else None,
        "sender_kid_avatar": promise.sender_kid.avatar_icon if promise.sender_kid else None,
        "receiver_kid_id": promise.receiver_kid_id,
        "receiver_kid_name": promise.receiver_kid.display_name if promise.receiver_kid else None,
        "receiver_kid_avatar": promise.receiver_kid.avatar_icon if promise.receiver_kid else None,
        "title": promise.title,
        "place": promise.place,
        "suggested_datetime": (
            promise.suggested_datetime.strftime("%Y-%m-%d %H:%M")
            if promise.suggested_datetime
            else None
        ),
        "voice_memo_url": promise.voice_memo_url,
        "status": promise.status,
        "sender_parent_approved": promise.sender_parent_approved,
        "receiver_parent_approved": promise.receiver_parent_approved,
        "created_at": promise.created_at.strftime("%Y-%m-%d %H:%M"),
    }


# ------------------------------------------------------------------
# 約束の相手を選ぶための、自分以外のキッズ一覧
# ------------------------------------------------------------------
@router.get("/other-kids")
async def list_other_kids(
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """約束する相手を選ぶための、自分以外のキッズ一覧を返す"""
    if user is None:
        raise HTTPException(status_code=401, detail="ログインしてください")

    kids = (
        db.query(User)
        .filter(User.role == "kids", User.id != user.id)
        .order_by(User.display_name.asc())
        .all()
    )
    return JSONResponse(
        {
            "success": True,
            "kids": [
                {
                    "id": k.id,
                    "display_name": k.display_name,
                    "avatar_icon": k.avatar_icon,
                }
                for k in kids
            ],
        }
    )


# ------------------------------------------------------------------
# 約束の提案（AIお兄さん・お姉さんが内容を抽出してPromiseを作成）
# ------------------------------------------------------------------
@router.post("/create")
async def create_promise(
    receiver_kid_id: int = Form(...),
    raw_text: str = Form(""),
    audio: UploadFile | None = File(None),
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """キッズが約束を提案する

    - receiver_kid_id : 約束したい相手のキッズID
    - raw_text         : クイックフレーズなどで組み立てたテキスト（任意）
    - audio            : ボイスメモ（任意。Whisperで文字化してAI抽出に使う）

    raw_text と ボイスメモの文字化テキストを合わせてAIに渡し、
    「約束の意図」「日時」「場所/内容」を抽出してPromiseを作成する。
    """
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    receiver = (
        db.query(User)
        .filter(User.id == receiver_kid_id, User.role == "kids")
        .first()
    )
    if receiver is None:
        raise HTTPException(status_code=404, detail="やくそくする あいてが みつかりません")
    if receiver.id == user.id:
        raise HTTPException(status_code=400, detail="じぶん自身とは やくそくできません")

    voice_memo_url = None
    transcribed_text = None

    has_audio = audio is not None and bool(audio.filename)
    if has_audio:
        voice_memo_url, audio_path = _save_voice_memo(
            audio, prefix=f"promise_voice_{user.id}"
        )
        transcribed_text = transcribe_audio(audio_path)

    combined_text = " ".join(
        part.strip()
        for part in [raw_text or "", transcribed_text or ""]
        if part and part.strip()
    )

    if not combined_text and not has_audio:
        raise HTTPException(
            status_code=400,
            detail="やくそくの内容（クイックフレーズ or ボイスメモ）をえらんでね",
        )

    extracted = extract_promise_details(combined_text)

    promise = Promise(
        sender_kid_id=user.id,
        receiver_kid_id=receiver.id,
        title=extracted["title"],
        place=extracted.get("place"),
        suggested_datetime=_parse_datetime(extracted.get("suggested_datetime")),
        raw_text=combined_text or None,
        voice_memo_url=voice_memo_url,
        status="pending_parents",
        sender_parent_approved=False,
        receiver_parent_approved=False,
    )
    db.add(promise)
    db.commit()
    db.refresh(promise)

    return JSONResponse({"success": True, "promise": _serialize_promise(promise)})


# ------------------------------------------------------------------
# 保護者による承認／拒否
# ------------------------------------------------------------------
@router.post("/{promise_id}/parent-response")
async def parent_response(
    promise_id: int,
    decision: str = Form(...),  # "approve" or "reject"
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """保護者が約束を承認(approve)または拒否(reject)する

    - 送信者側の保護者は sender_parent_approved を、
      受信者側の保護者は receiver_parent_approved を承認する。
    - どちらかが拒否した場合は即座に status="rejected" となる。
    - 双方が承認した場合のみ status="approved"（約束成立）となる。
    """
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="不正な回答です")

    promise = (
        db.query(Promise)
        .options(joinedload(Promise.sender_kid), joinedload(Promise.receiver_kid))
        .filter(Promise.id == promise_id)
        .first()
    )
    if promise is None:
        raise HTTPException(status_code=404, detail="やくそくが みつかりません")

    is_sender_parent = bool(
        promise.sender_kid and promise.sender_kid.parent_id == parent.id
    )
    is_receiver_parent = bool(
        promise.receiver_kid and promise.receiver_kid.parent_id == parent.id
    )

    if not (is_sender_parent or is_receiver_parent):
        raise HTTPException(
            status_code=403, detail="この やくそくを かくにんする けんげんがありません"
        )

    if promise.status != "pending_parents":
        # 既に確定済みの場合はそのまま現在の状態を返す
        return JSONResponse({"success": True, "promise": _serialize_promise(promise)})

    if decision == "reject":
        promise.status = "rejected"
    else:
        if is_sender_parent:
            promise.sender_parent_approved = True
        if is_receiver_parent:
            promise.receiver_parent_approved = True

        if promise.sender_parent_approved and promise.receiver_parent_approved:
            promise.status = "approved"

    db.commit()
    db.refresh(promise)

    return JSONResponse({"success": True, "promise": _serialize_promise(promise)})


# ------------------------------------------------------------------
# 自分に関わる約束一覧（キッズ／保護者いずれの視点でも取得可能）
# ------------------------------------------------------------------
@router.get("/my-promises")
async def my_promises(
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """現在アクティブなプロフィール（キッズ or 保護者）に関わる約束一覧を返す"""
    if user is None:
        raise HTTPException(status_code=401, detail="ログインしてください")

    query = db.query(Promise).options(
        joinedload(Promise.sender_kid), joinedload(Promise.receiver_kid)
    )

    if user.role == "kids":
        promises = (
            query.filter(
                (Promise.sender_kid_id == user.id)
                | (Promise.receiver_kid_id == user.id)
            )
            .order_by(Promise.created_at.desc())
            .all()
        )
    else:
        # 保護者本人としてログイン中の場合：自分の子ども全員が関わる約束を表示
        kid_ids = [
            k.id
            for k in db.query(User)
            .filter(User.parent_id == user.id, User.role == "kids")
            .all()
        ]
        if kid_ids:
            promises = (
                query.filter(
                    (Promise.sender_kid_id.in_(kid_ids))
                    | (Promise.receiver_kid_id.in_(kid_ids))
                )
                .order_by(Promise.created_at.desc())
                .all()
            )
        else:
            promises = []

    return JSONResponse(
        {"success": True, "promises": [_serialize_promise(p) for p in promises]}
    )
