"""
遊ぶ約束（プロミス）APIルーター（ひろば）

「あそぶ お約束」フローは、以下の2ステップで構成される。

1. キッズが【📅 いつ？／🌞🌤 じかんたい／🏠🏡🏫🎤 どこで？】を
   タップ選択だけで投稿する（PromisePost = あそびたい投稿）。
2. 別のキッズが「いっしょにあそびたい！」をタップすると、その2人の
   お約束（Promise）が作成され、双方の保護者が承認するまで
   「確認中」のまま保たれる。

第三者に人間関係を見せない設計:
- /board は「まだ成立していない、自分以外の子の投稿」のみを返し、
  応募人数・応募者一覧・誰が応募したかは絶対に含めない。
- 投稿が成立(matched)すると、Deleteではなく status="matched" にする
  だけで掲示板から静かに外れる（第三者には「消えた」ようにしか見えない）。
- Promise（確認中／成立／キャンセルの状態）は当事者(sender・receiver)
  以外には一切返さない。

主なエンドポイント:
- GET  /api/promises/board                 : 掲示板（自分以外の「あそびたい」投稿一覧）
- GET  /api/promises/posts/mine            : 自分の現在の投稿状態
- POST /api/promises/posts/create          : 「あそびたい」を投稿する
- POST /api/promises/posts/{id}/apply      : 「いっしょにあそびたい！」で応募する
- GET  /api/promises/my-promises           : 自分に関わるお約束一覧
- POST /api/promises/{id}/parent-response  : 保護者の回答（いいよ／じかんを決める／今回はむずかしい）
- POST /api/promises/{id}/cancel           : 保護者による成立後キャンセル
"""

import datetime as dt
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import get_active_user, get_current_parent
from app.database import get_db
from app.models import Promise, PromisePost, User
from app.models.promise import LOCATION_TYPES, TIME_FRAMES
from app.paths import UPLOAD_DIR
from app.services.line_notify_service import notify_parent

router = APIRouter(prefix="/api/promises", tags=["promises"])

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")

# キッズに表示するためのメッセージ（第三者には理由を開示しない・非責めメッセージ）
MSG_ALREADY_APPROVED_TODAY = "このひは もうやくそくがあるよ😊"
MSG_ALREADY_PENDING = "いま おうちのひとに かくにんしている よていがあるよ😊"
MSG_WAITING_PARENTS = "おうちのひとに かくにんしてるよ😊"
MSG_DECLINED = "こんかいは むずかしいみたい。またこんど あそぼうね😊"


def _save_voice_memo(file: UploadFile, prefix: str) -> str:
    """ボイスメモを保存し、公開URLを返す（既存の録音・アップロード機能を活用）"""
    ext = "bin"
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()

    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    dest_path = UPLOAD_DIR / filename
    with dest_path.open("wb") as buffer:
        buffer.write(file.file.read())

    return f"/static/uploads/{filename}"


def _parse_date(value: str) -> dt.date:
    """"YYYY-MM-DD" 形式の日付文字列を検証しつつ date に変換する（過去日は不可）"""
    try:
        parsed = dt.date.fromisoformat((value or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="ひづけの けいしきが ただしくありません")

    if parsed < dt.date.today():
        raise HTTPException(status_code=400, detail="きょうより まえの ひは えらべません")
    return parsed


def _has_approved_on_date(
    db: Session, kid_id: int, date_: dt.date, exclude_promise_id: int | None = None
) -> bool:
    """指定キッズがその日に「成立済み」のお約束を既に持っているか"""
    query = db.query(Promise).filter(
        Promise.status == "approved",
        Promise.date == date_,
        (Promise.sender_kid_id == kid_id) | (Promise.receiver_kid_id == kid_id),
    )
    if exclude_promise_id is not None:
        query = query.filter(Promise.id != exclude_promise_id)
    return db.query(query.exists()).scalar()


def _has_pending_engagement(db: Session, kid_id: int) -> bool:
    """指定キッズが「現在確認中」の予定（保護者回答待ちのPromise、または
    まだ誰も応募していない自分の投稿）を持っているか"""
    pending_promise = (
        db.query(Promise)
        .filter(
            Promise.status == "pending_parents",
            (Promise.sender_kid_id == kid_id) | (Promise.receiver_kid_id == kid_id),
        )
        .first()
    )
    if pending_promise is not None:
        return True

    open_post = (
        db.query(PromisePost)
        .filter(PromisePost.kid_id == kid_id, PromisePost.status == "open")
        .first()
    )
    return open_post is not None


def _validate_new_engagement(db: Session, kid_id: int, date_: dt.date) -> None:
    """新しい投稿・応募が可能かどうかをチェックする（1日1件ルール等）"""
    if _has_approved_on_date(db, kid_id, date_):
        raise HTTPException(status_code=400, detail=MSG_ALREADY_APPROVED_TODAY)
    if _has_pending_engagement(db, kid_id):
        raise HTTPException(status_code=400, detail=MSG_ALREADY_PENDING)


def _other_parent(db: Session, promise: Promise, is_sender_parent: bool) -> User | None:
    """お約束のもう一方の家庭の保護者を取得する"""
    kid = promise.receiver_kid if is_sender_parent else promise.sender_kid
    if not kid or not kid.parent_id:
        return None
    return db.query(User).filter(User.id == kid.parent_id).first()


# ------------------------------------------------------------------
# シリアライズ
# ------------------------------------------------------------------
def _serialize_post_for_board(post: PromisePost) -> dict:
    """掲示板表示用（応募人数・応募者一覧など第三者に見せてはいけない情報は含めない）"""
    return {
        "id": post.id,
        "kid_name": post.kid.display_name if post.kid else None,
        "kid_avatar": post.kid.avatar_icon if post.kid else None,
        "date": post.date.isoformat(),
        "time_frame": post.time_frame,
        "location_type": post.location_type,
        "location_audio_url": post.location_audio_url,
        "created_at": post.created_at.strftime("%Y-%m-%d %H:%M"),
    }


def _serialize_own_post(post: PromisePost | None) -> dict | None:
    if post is None:
        return None
    return {
        "id": post.id,
        "date": post.date.isoformat(),
        "time_frame": post.time_frame,
        "location_type": post.location_type,
        "location_audio_url": post.location_audio_url,
        "status": post.status,
        "created_at": post.created_at.strftime("%Y-%m-%d %H:%M"),
    }


def _serialize_promise(promise: Promise) -> dict:
    """当事者（sender・receiverの家庭）にのみ返すことを前提としたシリアライズ"""
    return {
        "id": promise.id,
        "post_id": promise.post_id,
        "sender_kid_id": promise.sender_kid_id,
        "sender_kid_name": promise.sender_kid.display_name if promise.sender_kid else None,
        "sender_kid_avatar": promise.sender_kid.avatar_icon if promise.sender_kid else None,
        "receiver_kid_id": promise.receiver_kid_id,
        "receiver_kid_name": promise.receiver_kid.display_name if promise.receiver_kid else None,
        "receiver_kid_avatar": promise.receiver_kid.avatar_icon if promise.receiver_kid else None,
        "date": promise.date.isoformat(),
        "time_frame": promise.time_frame,
        "detailed_time": promise.detailed_time,
        "location_type": promise.location_type,
        "location_audio_url": promise.location_audio_url,
        "status": promise.status,
        "sender_parent_approved": promise.sender_parent_approved,
        "receiver_parent_approved": promise.receiver_parent_approved,
        "created_at": promise.created_at.strftime("%Y-%m-%d %H:%M"),
    }


# ------------------------------------------------------------------
# 自分以外のキッズ一覧（おへや招待の「おともだちをえらぶ」等で利用）
# ------------------------------------------------------------------
@router.get("/other-kids")
async def list_other_kids(
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

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
                {"id": k.id, "display_name": k.display_name, "avatar_icon": k.avatar_icon}
                for k in kids
            ],
        }
    )


# ------------------------------------------------------------------
# 掲示板（自分以外の「あそびたい」投稿一覧）
# ------------------------------------------------------------------
@router.get("/board")

async def list_board(
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """自分以外のキッズの「あそびたい」投稿一覧を取得する

    - 成立済み(matched)・キャンセル済みの投稿は表示しない
    - 自分が既に応募済み（確認中／成立）の投稿は表示しない
    - 応募人数・応募者一覧など、誰が応募したか分かる情報は絶対に含めない
    """
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    applied_post_ids = {
        row[0]
        for row in db.query(Promise.post_id)
        .filter(
            Promise.receiver_kid_id == user.id,
            Promise.status.in_(["pending_parents", "approved"]),
        )
        .all()
    }

    posts = (
        db.query(PromisePost)
        .options(joinedload(PromisePost.kid))
        .filter(PromisePost.status == "open", PromisePost.kid_id != user.id)
        .order_by(PromisePost.created_at.desc())
        .all()
    )
    posts = [p for p in posts if p.id not in applied_post_ids]

    return JSONResponse(
        {"success": True, "posts": [_serialize_post_for_board(p) for p in posts]}
    )


# ------------------------------------------------------------------
# 自分の現在の投稿状態
# ------------------------------------------------------------------
@router.get("/posts/mine")
async def my_post(
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    post = (
        db.query(PromisePost)
        .filter(PromisePost.kid_id == user.id, PromisePost.status == "open")
        .order_by(PromisePost.created_at.desc())
        .first()
    )
    return JSONResponse({"success": True, "post": _serialize_own_post(post)})


# ------------------------------------------------------------------
# 「あそびたい」を投稿する
# ------------------------------------------------------------------
@router.post("/posts/create")
async def create_post(
    date: str = Form(...),
    time_frame: str = Form(...),
    location_type: str = Form(...),
    audio: UploadFile | None = File(None),
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """キッズが「いつ／じかんたい／どこで あそびたい」をタップ選択で投稿する

    - date          : "YYYY-MM-DD"（過去日は不可）
    - time_frame    : "morning" / "afternoon"
    - location_type : "home_my" / "home_friend" / "school" / "other"
    - audio         : location_type=="other" のときのみ必須のボイスメモ
    """
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    date_ = _parse_date(date)

    if time_frame not in TIME_FRAMES:
        raise HTTPException(status_code=400, detail="じかんたいを えらんでね")
    if location_type not in LOCATION_TYPES:
        raise HTTPException(status_code=400, detail="どこで あそぶか えらんでね")

    _validate_new_engagement(db, user.id, date_)

    location_audio_url = None
    if location_type == "other":
        has_audio = audio is not None and bool(audio.filename)
        if not has_audio:
            raise HTTPException(
                status_code=400,
                detail="「そのほか」を えらんだときは ボイスメモを ろくおんしてね",
            )
        location_audio_url = _save_voice_memo(audio, prefix=f"promise_location_{user.id}")

    post = PromisePost(
        kid_id=user.id,
        date=date_,
        time_frame=time_frame,
        location_type=location_type,
        location_audio_url=location_audio_url,
        status="open",
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return JSONResponse({"success": True, "post": _serialize_own_post(post)})


# ------------------------------------------------------------------
# 「いっしょにあそびたい！」で応募する
# ------------------------------------------------------------------
@router.post("/posts/{post_id}/apply")
async def apply_to_post(
    post_id: int,
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """他のキッズの「あそびたい」投稿に応募する

    即座に成立させず、双方の保護者へ確認を依頼する状態(pending_parents)にする。
    """
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    post = (
        db.query(PromisePost)
        .options(joinedload(PromisePost.kid))
        .filter(PromisePost.id == post_id)
        .first()
    )
    if post is None or post.status != "open":
        raise HTTPException(status_code=404, detail="この やくそくは もう ないみたい…")
    if post.kid_id == user.id:
        raise HTTPException(status_code=400, detail="じぶんの とうこうには おうぼできません")

    _validate_new_engagement(db, user.id, post.date)

    existing = (
        db.query(Promise)
        .filter(
            Promise.post_id == post.id,
            Promise.receiver_kid_id == user.id,
            Promise.status.in_(["pending_parents", "approved"]),
        )
        .first()
    )
    if existing is not None:
        return JSONResponse({"success": True, "promise": _serialize_promise(existing)})

    promise = Promise(
        post_id=post.id,
        sender_kid_id=post.kid_id,
        receiver_kid_id=user.id,
        date=post.date,
        time_frame=post.time_frame,
        location_type=post.location_type,
        location_audio_url=post.location_audio_url,
        status="pending_parents",
        sender_parent_approved=False,
        receiver_parent_approved=False,
    )
    db.add(promise)
    db.commit()
    db.refresh(promise)

    sender_parent = (
        db.query(User).filter(User.id == post.kid.parent_id).first()
        if post.kid and post.kid.parent_id
        else None
    )
    receiver_parent = (
        db.query(User).filter(User.id == user.parent_id).first()
        if user.parent_id
        else None
    )
    location_label = {
        "home_my": "🏠 うち",
        "home_friend": "🏡 あいてのいえ",
        "school": "🏫 がっこう・こうてい",
        "other": "🎤 そのほか",
    }.get(promise.location_type, promise.location_type)
    time_label = "🌞 ごぜん" if promise.time_frame == "morning" else "🌤 ごご"
    detail = f"{promise.date.isoformat()}（{time_label}／{location_label}）"

    notify_parent(
        sender_parent,
        f"お子さまの投稿に「いっしょにあそびたい」という応募がありました。{detail}\n"
        "［👌 いいよ］［🕐 じかんを決める］［🙅 今回はむずかしい］でご回答ください。",
    )
    notify_parent(
        receiver_parent,
        f"お子さまが遊ぶ約束に応募しました。{detail}\n"
        "［👌 いいよ］［🕐 じかんを決める］［🙅 今回はむずかしい］でご回答ください。",
    )

    return JSONResponse({"success": True, "promise": _serialize_promise(promise)})


# ------------------------------------------------------------------
# 自分に関わるお約束一覧（キッズ／保護者いずれの視点でも取得可能）
# ------------------------------------------------------------------
@router.get("/my-promises")
async def my_promises(
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """現在アクティブなプロフィール（キッズ or 保護者）に関わるお約束一覧を返す

    ※必ず「当事者（sender・receiverの家庭）」に限定されるため、
      第三者に他の子の約束状況が漏れることはない。
    """
    if user is None:
        raise HTTPException(status_code=401, detail="ログインしてください")

    query = db.query(Promise).options(
        joinedload(Promise.sender_kid), joinedload(Promise.receiver_kid)
    )

    if user.role == "kids":
        promises = (
            query.filter(
                (Promise.sender_kid_id == user.id) | (Promise.receiver_kid_id == user.id)
            )
            .order_by(Promise.created_at.desc())
            .all()
        )
    else:
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


# ------------------------------------------------------------------
# 保護者による回答（👌 いいよ／🕐 じかんを決める／🙅 今回はむずかしい）
# ------------------------------------------------------------------
@router.post("/{promise_id}/parent-response")
async def parent_response(
    promise_id: int,
    decision: str = Form(...),  # "approve" / "adjust_time" / "decline"
    start_time: str | None = Form(None),
    end_time: str | None = Form(None),
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """保護者がタップ選択で回答する

    - "approve"     : 👌 いいよ
    - "adjust_time" : 🕐 じかんを決める（start_time・end_time が必須）
    - "decline"     : 🙅 今回はむずかしい（即キャンセル・非責めメッセージのみ配信）

    双方が approve した時点で、同日の二重約束がないか最終チェックを行い、
    問題なければ「成立」とする。
    """
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    if decision not in ("approve", "adjust_time", "decline"):
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
        # 既に確定済みの場合はそのまま現在の状態を返す（冪等）
        return JSONResponse({"success": True, "promise": _serialize_promise(promise)})

    other_parent = _other_parent(db, promise, is_sender_parent)

    if decision == "decline":
        promise.status = "cancelled"
        db.commit()
        notify_parent(other_parent, MSG_DECLINED)

    elif decision == "adjust_time":
        if not start_time or not end_time or not _TIME_RE.match(start_time) or not _TIME_RE.match(end_time):
            raise HTTPException(status_code=400, detail="じかんを えらんでね")
        promise.detailed_time = f"{start_time}〜{end_time}"
        # 時間が変わるため、双方の再確認が必要になる
        # （提案した側は「賛成」の状態にしておき、相手側だけ再確認を待つ）
        promise.sender_parent_approved = is_sender_parent
        promise.receiver_parent_approved = is_receiver_parent
        db.commit()
        notify_parent(
            other_parent,
            f"じかんの ていあんが きたよ: {promise.detailed_time}\n"
            "［👌 いいよ］［🕐 じかんを決める］［🙅 今回はむずかしい］でご回答ください。",
        )

    else:  # approve
        if is_sender_parent:
            promise.sender_parent_approved = True
        if is_receiver_parent:
            promise.receiver_parent_approved = True

        if promise.sender_parent_approved and promise.receiver_parent_approved:
            conflict = _has_approved_on_date(
                db, promise.sender_kid_id, promise.date, exclude_promise_id=promise.id
            ) or _has_approved_on_date(
                db, promise.receiver_kid_id, promise.date, exclude_promise_id=promise.id
            )
            if conflict:
                promise.status = "cancelled"
            else:
                promise.status = "approved"
                post = (
                    db.query(PromisePost)
                    .filter(PromisePost.id == promise.post_id)
                    .first()
                )
                if post is not None:
                    post.status = "matched"
                    post.matched_promise_id = promise.id

                # 同じ投稿への他の応募（他のキッズ）は静かにキャンセルする
                siblings = (
                    db.query(Promise)
                    .filter(
                        Promise.post_id == promise.post_id,
                        Promise.id != promise.id,
                        Promise.status == "pending_parents",
                    )
                    .all()
                )
                for sibling in siblings:
                    sibling.status = "cancelled"

        db.commit()

        if promise.status == "approved":
            notify_parent(other_parent, "🎉 やくそくが せいりつしました！")
        elif promise.status == "cancelled":
            notify_parent(other_parent, MSG_DECLINED)
        else:
            notify_parent(other_parent, "もう一方の おうちのかたが かくにんしました。")

    db.refresh(promise)
    return JSONResponse({"success": True, "promise": _serialize_promise(promise)})


# ------------------------------------------------------------------
# 成立後のキャンセル（保護者のみ）
# ------------------------------------------------------------------
@router.post("/{promise_id}/cancel")
async def cancel_promise(
    promise_id: int,
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """成立済みのお約束を保護者がキャンセルする（角の立たないLINE通知を相手親へ送る）"""
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

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
            status_code=403, detail="この やくそくを キャンセルする けんげんがありません"
        )

    if promise.status != "approved":
        raise HTTPException(status_code=400, detail="せいりつしている やくそくのみ キャンセルできます")

    promise.status = "cancelled"

    post = db.query(PromisePost).filter(PromisePost.id == promise.post_id).first()
    if post is not None and post.matched_promise_id == promise.id:
        post.status = "open"
        post.matched_promise_id = None

    db.commit()

    other_parent = _other_parent(db, promise, is_sender_parent)
    notify_parent(other_parent, "きょうは むずかしくなったみたい。またこんど あそぼうね😊")

    db.refresh(promise)
    return JSONResponse({"success": True, "promise": _serialize_promise(promise)})
