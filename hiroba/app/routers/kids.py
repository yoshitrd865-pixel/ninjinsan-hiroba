"""
キッズ用投稿ルーター（ひろば）

小学生が文字入力をしなくても投稿できるように、以下の3要素だけで
投稿を作成できるAPIを提供する。
- stamps : 特大気分スタンプ（例:「たのしい」「できた！」「みてみて」）
- image  : お絵描きCanvasのBase64データ、または写真ファイル（どちらか/両方）
- audio  : ボイスメモ（録音した音声ファイル）

音声はオプションで Whisper により文字化され Post.whisper_text に保存される
（保護者確認用。キッズ自身には表示しない想定）。

投稿の削除について（「理由を表示せず静かに消す」プライバシー設計）:
- 削除を実行できるのは、投稿した本人（キッズ）またはそのキッズの保護者のみ。
- 削除は実際のDeleteではなく Post.is_hidden = True を立てるだけの
  論理削除とし、タイムライン等の一覧クエリから静かに除外する。
  「削除されました」等のメッセージは一切表示しない。
- 権限のないユーザーからのアクセスには、投稿の存在自体を明かさないため
  404を返す（403にはしない）。
"""

import base64
import binascii
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import get_active_user
from app.database import get_db
from app.models import Post, RoomMember, User
from app.models.reaction import REACTION_LABELS
from app.paths import UPLOAD_DIR
from app.services.whisper_service import transcribe_audio


def _require_active_room_membership(db: Session, room_id: int, kid_id: int) -> None:
    """おへや内投稿・タイムラインの操作前に、正式メンバーであることを確認する

    メンバーでない場合は、おへやの存在自体を明かさないため404を返す。
    """
    is_member = (
        db.query(RoomMember)
        .filter(
            RoomMember.room_id == room_id,
            RoomMember.kid_id == kid_id,
            RoomMember.status == "active",
        )
        .first()
        is not None
    )
    if not is_member:
        raise HTTPException(status_code=404, detail="おへやが みつかりません")



router = APIRouter(prefix="/api/posts", tags=["posts"])

# 特大気分スタンプの候補（キッズがタップで選ぶだけ。自由入力も許容する）
SUGGESTED_STAMPS = ["たのしい", "できた！", "みてみて", "うれしい", "びっくり"]

_DATA_URL_RE = re.compile(
    r"^data:image/(?P<ext>png|jpeg|jpg|gif|webp);base64,(?P<data>.+)$", re.DOTALL
)


def _require_active_user(user: User | None) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="ログインしてください")
    return user


def _save_upload_file(file: UploadFile, prefix: str) -> tuple[str, Path]:
    """アップロードファイルを保存し、(公開URL, 実ファイルパス) を返す"""
    ext = "bin"
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()

    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    dest_path = UPLOAD_DIR / filename
    with dest_path.open("wb") as buffer:
        buffer.write(file.file.read())

    return f"/static/uploads/{filename}", dest_path


def _save_base64_image(data_url: str, prefix: str) -> tuple[str, Path]:
    """お絵描きCanvasのdata URL（Base64）を画像として保存する"""
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise HTTPException(
            status_code=400, detail="おえかきデータの形式が正しくありません"
        )

    ext = match.group("ext")
    raw = match.group("data")
    try:
        binary = base64.b64decode(raw)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=400, detail="おえかきデータの読み込みに失敗しました"
        )

    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    dest_path = UPLOAD_DIR / filename
    with dest_path.open("wb") as buffer:
        buffer.write(binary)

    return f"/static/uploads/{filename}", dest_path


def _serialize_post(post: Post, viewer: User | None = None) -> dict:
    """タイムライン表示用に投稿をシリアライズする（4種のリアクション数を含む）

    - can_delete : 閲覧者が「けす」ボタンを操作できるか（本人 or その保護者）
    """
    reaction_counts = {rt: 0 for rt in REACTION_LABELS}
    for r in post.reactions:
        if r.reaction_type in reaction_counts:
            reaction_counts[r.reaction_type] += 1

    can_delete = False
    if viewer is not None:
        if post.user_id == viewer.id:
            can_delete = True
        elif (
            viewer.role == "parent"
            and post.user is not None
            and post.user.parent_id == viewer.id
        ):
            can_delete = True

    return {
        "id": post.id,
        "user_id": post.user_id,
        "author_name": post.user.display_name if post.user else "きっず",
        "author_avatar": post.user.avatar_icon if post.user else None,
        "photo_url": post.photo_url,
        "drawing_url": post.drawing_url,
        "voice_memo_url": post.voice_memo_url,
        "mood_stamp": post.mood_stamp,
        "created_at": post.created_at.strftime("%Y-%m-%d %H:%M"),
        "reactions": reaction_counts,
        "reaction_total": sum(reaction_counts.values()),
        "can_delete": can_delete,
    }


@router.post("/create")
async def create_post(
    stamps: str = Form(""),
    drawing_data: str | None = Form(None),
    image: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """写真/お絵描き＋ボイスメモ＋気分スタンプから投稿を作成する

    - stamps       : 気分スタンプ（例:「たのしい」）。空文字も許容。
    - drawing_data : お絵描きCanvasのBase64データURL（任意）
    - image        : 写真ファイル（任意。drawing_dataと同時指定も可）
    - audio        : ボイスメモ音声ファイル（任意）

    最低1つ（スタンプ・写真・お絵描き・ボイスメモのいずれか）が必要。
    """
    active_user = _require_active_user(user)

    has_image = image is not None and bool(image.filename)
    has_drawing = bool(drawing_data)
    has_audio = audio is not None and bool(audio.filename)
    has_stamp = bool(stamps.strip())

    if not (has_image or has_drawing or has_audio or has_stamp):
        raise HTTPException(
            status_code=400,
            detail="スタンプ・しゃしん・おえかき・ボイスメモのいずれかが必要です",
        )

    photo_url = None
    drawing_url = None
    voice_memo_url = None
    whisper_text = None

    if has_image:
        photo_url, _ = _save_upload_file(image, prefix=f"photo_{active_user.id}")

    if has_drawing:
        drawing_url, _ = _save_base64_image(
            drawing_data, prefix=f"drawing_{active_user.id}"
        )

    if has_audio:
        voice_memo_url, audio_path = _save_upload_file(
            audio, prefix=f"voice_{active_user.id}"
        )
        # Whisper未設定（OPENAI_API_KEY未設定）の場合は None が返る
        whisper_text = transcribe_audio(audio_path)

    post = Post(
        user_id=active_user.id,
        photo_url=photo_url,
        drawing_url=drawing_url,
        voice_memo_url=voice_memo_url,
        mood_stamp=stamps.strip() or None,
        whisper_text=whisper_text,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return JSONResponse({"success": True, "post": _serialize_post(post, active_user)})


@router.get("/timeline")
async def get_timeline(
    limit: int = 50,
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """みんなのひろば（タイムライン）を新着順に取得する

    削除済み（is_hidden=True）の投稿は、理由を出さず静かに除外する
    （第三者には「もともとなかった」ように見える）。
    """
    active_user = _require_active_user(user)

    # グローバルタイムラインには「おへや」内投稿(room_id有り)は含めない
    posts = (
        db.query(Post)
        .options(joinedload(Post.user), joinedload(Post.reactions))
        .filter(Post.is_hidden == False, Post.room_id.is_(None))  # noqa: E712
        .order_by(Post.created_at.desc())
        .limit(limit)
        .all()
    )


    return JSONResponse(
        {
            "success": True,
            "posts": [_serialize_post(p, active_user) for p in posts],
        }
    )


# ------------------------------------------------------------------
# 投稿の削除（本人キッズ、またはその保護者のみ実行可能）
# ------------------------------------------------------------------
@router.post("/{post_id}/delete")
async def delete_post(
    post_id: int,
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """投稿を削除する（静かに非表示にするだけで、理由は一切表示しない）

    - 実行できるのは投稿した本人（キッズ）、またはそのキッズの保護者のみ。
    - それ以外のユーザーからは、投稿の存在自体を明かさないため404を返す。
    - 実際にDeleteはせず is_hidden=True にするのみ（タイムライン等から
      静かに消えるだけで、「削除されました」等の表示は一切行わない）。
    """
    active_user = _require_active_user(user)

    post = (
        db.query(Post)
        .options(joinedload(Post.user))
        .filter(Post.id == post_id, Post.is_hidden == False)  # noqa: E712
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="投稿が見つかりません")

    is_owner = post.user_id == active_user.id
    is_parent_of_owner = (
        active_user.role == "parent"
        and post.user is not None
        and post.user.parent_id == active_user.id
    )
    if not (is_owner or is_parent_of_owner):
        # 権限がない場合も存在自体を明かさない（404で統一。403は使わない）
        raise HTTPException(status_code=404, detail="投稿が見つかりません")

    post.is_hidden = True
    db.commit()

    return JSONResponse({"success": True})
