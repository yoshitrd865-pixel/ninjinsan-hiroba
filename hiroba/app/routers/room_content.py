"""
おへやの中コンテンツAPIルーター（ひろば）

「おへやの中」画面（3タブ構成）のうち、以下の内容に対応するAPIを提供する。
- 🏞️ ひろば（みるへや）／🎨 つくる（つくるへや）:
    おへや内投稿（Post に room_id を指定したもの）の一覧取得・作成・削除
- 🤝 やくそく（約束をするへや）:
    おへや内の「やくそく」提案カード（RoomPromise / RoomPromiseApproval）

いずれのAPIも、そのおへやの正式メンバー（RoomMember.status == "active"）
以外には一切データを返さない（存在自体を明かさないため404で統一する、
既存 app/routers/rooms.py の設計方針をそのまま継承する）。
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import get_active_user
from app.database import get_db
from app.models import Post, RoomMember, RoomPromise, RoomPromiseApproval, User
from app.models.reaction import REACTION_LABELS
from app.routers.rooms import _get_active_membership, _get_active_room
from app.services.uploads import save_upload_file

router = APIRouter(prefix="/api/rooms", tags=["room-content"])


def _require_member(db: Session, room_id: int, user: User | None) -> RoomMember:
    """おへやの正式メンバーであることを確認する（それ以外は404で統一）"""
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    membership = _get_active_membership(db, room_id, user.id)
    if membership is None or _get_active_room(db, room_id) is None:
        raise HTTPException(status_code=404, detail="おへやが みつかりません")
    return membership


# ------------------------------------------------------------------
# おへや内投稿（ひろば／つくる タブ）
# ------------------------------------------------------------------
def _serialize_room_post(post: Post, viewer: User) -> dict:
    reaction_counts = {rt: 0 for rt in REACTION_LABELS}
    for r in post.reactions:
        if r.reaction_type in reaction_counts:
            reaction_counts[r.reaction_type] += 1

    can_delete = post.user_id == viewer.id or (
        viewer.role == "parent"
        and post.user is not None
        and post.user.parent_id == viewer.id
    )

    return {
        "id": post.id,
        "user_id": post.user_id,
        "room_id": post.room_id,
        "author_name": post.user.display_name if post.user else "きっず",
        "author_avatar": post.user.avatar_icon if post.user else None,
        "photo_url": post.photo_url,
        "voice_memo_url": post.voice_memo_url,
        "mood_stamp": post.mood_stamp,
        "message": post.message,
        "created_at": post.created_at.strftime("%Y-%m-%d %H:%M"),
        "reactions": reaction_counts,
        "reaction_total": sum(reaction_counts.values()),
        "can_delete": can_delete,
    }


@router.get("/{room_id}/posts")
async def list_room_posts(
    room_id: int,
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """おへやの「ひろば（みるへや）」タイムラインを新着順に取得する"""
    _require_member(db, room_id, user)

    posts = (
        db.query(Post)
        .options(joinedload(Post.user), joinedload(Post.reactions))
        .filter(Post.room_id == room_id, Post.is_hidden == False)  # noqa: E712
        .order_by(Post.created_at.desc())
        .all()
    )
    return JSONResponse(
        {"success": True, "posts": [_serialize_room_post(p, user) for p in posts]}
    )


@router.post("/{room_id}/posts/create")
async def create_room_post(
    room_id: int,
    message: str = Form(""),
    stamps: str = Form(""),
    image: UploadFile | None = File(None),
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """おへやの「つくる（つくるへや）」タブから投稿する

    - message : ✏️ メッセージをかく（任意の短い文章）
    - stamps  : 😆 スタンプをツカウ（任意）
    - image   : 📷 写真をえらぶ（任意）
    最低1つが必要。
    """
    _require_member(db, room_id, user)

    message = (message or "").strip()
    stamps = (stamps or "").strip()
    has_image = image is not None and bool(image.filename)

    if not (message or stamps or has_image):
        raise HTTPException(
            status_code=400,
            detail="しゃしん・メッセージ・スタンプの どれかを えらんでね！",
        )

    photo_url = None
    if has_image:
        photo_url, _ = save_upload_file(image, prefix=f"room{room_id}_photo_{user.id}")

    post = Post(
        user_id=user.id,
        room_id=room_id,
        photo_url=photo_url,
        mood_stamp=stamps or None,
        message=message or None,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return JSONResponse({"success": True, "post": _serialize_room_post(post, user)})


@router.post("/{room_id}/posts/{post_id}/delete")
async def delete_room_post(
    room_id: int,
    post_id: int,
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """おへや内投稿を削除する（本人キッズ、またはその保護者のみ。静かに消えるだけ）"""
    if user is None:
        raise HTTPException(status_code=401, detail="ログインしてください")

    post = (
        db.query(Post)
        .options(joinedload(Post.user))
        .filter(
            Post.id == post_id,
            Post.room_id == room_id,
            Post.is_hidden == False,  # noqa: E712
        )
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="投稿が見つかりません")

    is_owner = post.user_id == user.id
    is_parent_of_owner = (
        user.role == "parent"
        and post.user is not None
        and post.user.parent_id == user.id
    )
    if not (is_owner or is_parent_of_owner):
        raise HTTPException(status_code=404, detail="投稿が見つかりません")

    post.is_hidden = True
    db.commit()
    return JSONResponse({"success": True})


# ------------------------------------------------------------------
# やくそく（約束をするへや）
# ------------------------------------------------------------------
def _serialize_room_promise(rp: RoomPromise, members: list[RoomMember]) -> dict:
    approved_kid_ids = {a.kid_id for a in rp.approvals}
    return {
        "id": rp.id,
        "room_id": rp.room_id,
        "when_text": rp.when_text,
        "where_text": rp.where_text,
        "what_text": rp.what_text,
        "created_by_kid_id": rp.created_by_kid_id,
        "created_at": rp.created_at.strftime("%Y-%m-%d %H:%M"),
        "members": [
            {
                "kid_id": m.kid_id,
                "kid_name": m.kid.display_name if m.kid else None,
                "kid_avatar": m.kid.avatar_icon if m.kid else None,
                "approved": m.kid_id in approved_kid_ids,
            }
            for m in members
        ],
    }


def _active_room_members(db: Session, room_id: int) -> list[RoomMember]:
    return (
        db.query(RoomMember)
        .options(joinedload(RoomMember.kid))
        .filter(RoomMember.room_id == room_id, RoomMember.status == "active")
        .all()
    )


@router.get("/{room_id}/promises")
async def list_room_promises(
    room_id: int,
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """おへやの「やくそく（約束をするへや）」一覧を取得する"""
    _require_member(db, room_id, user)

    members = _active_room_members(db, room_id)
    promises = (
        db.query(RoomPromise)
        .options(joinedload(RoomPromise.approvals))
        .filter(RoomPromise.room_id == room_id, RoomPromise.is_active == True)  # noqa: E712
        .order_by(RoomPromise.created_at.desc())
        .all()
    )
    return JSONResponse(
        {
            "success": True,
            "promises": [_serialize_room_promise(p, members) for p in promises],
        }
    )


@router.post("/{room_id}/promises/create")
async def create_room_promise(
    room_id: int,
    when_text: str = Form(""),
    where_text: str = Form(""),
    what_text: str = Form(""),
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """「遊ぶ約束をしよう！」カードを作成する（いつ？／どこで？／なにをする？）"""
    _require_member(db, room_id, user)

    when_text = (when_text or "").strip()[:100]
    where_text = (where_text or "").strip()[:100]
    what_text = (what_text or "").strip()[:100]
    if not (when_text or where_text or what_text):
        raise HTTPException(
            status_code=400, detail="いつ・どこで・なにをする か きめてね！"
        )

    rp = RoomPromise(
        room_id=room_id,
        created_by_kid_id=user.id,
        when_text=when_text,
        where_text=where_text,
        what_text=what_text,
    )
    db.add(rp)
    db.commit()
    db.refresh(rp)

    # 提案した本人は自動的に「さんかする！」状態にしておく
    db.add(RoomPromiseApproval(room_promise_id=rp.id, kid_id=user.id))
    db.commit()
    db.refresh(rp)

    members = _active_room_members(db, room_id)
    return JSONResponse(
        {"success": True, "promise": _serialize_room_promise(rp, members)}
    )


@router.post("/promises/{promise_id}/toggle")
async def toggle_room_promise_approval(
    promise_id: int,
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """「さんかする！」の緑チェックマークをオン/オフする（正式メンバー本人のみ）"""
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    rp = (
        db.query(RoomPromise)
        .filter(RoomPromise.id == promise_id, RoomPromise.is_active == True)  # noqa: E712
        .first()
    )
    if rp is None:
        raise HTTPException(status_code=404, detail="やくそくが みつかりません")

    membership = _get_active_membership(db, rp.room_id, user.id)
    if membership is None:
        raise HTTPException(status_code=404, detail="やくそくが みつかりません")

    existing = (
        db.query(RoomPromiseApproval)
        .filter(
            RoomPromiseApproval.room_promise_id == rp.id,
            RoomPromiseApproval.kid_id == user.id,
        )
        .first()
    )
    if existing:
        db.delete(existing)
    else:
        db.add(RoomPromiseApproval(room_promise_id=rp.id, kid_id=user.id))
    db.commit()
    db.refresh(rp)

    members = _active_room_members(db, rp.room_id)
    return JSONResponse(
        {"success": True, "promise": _serialize_room_promise(rp, members)}
    )
