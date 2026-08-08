"""
おへや（Room）APIルーター（ひろば）

完全クローズド・招待制のグループ機能。
- 自分が正式メンバー（RoomMember.status == "active"）として参加している
  「わたしのおへや」だけが見える（検索・一覧・おすすめ等は一切提供しない）。
- 招待された場合のみ「💌 おへやのおさそいがきてるよ！」が表示され、
  本人が「さんかする」を選び、さらに保護者が承認して初めて正式メンバーになる。
- /api/rooms/{room_id} は正式メンバー以外には常に404を返し、
  投稿・音声・メンバー情報などを絶対に返さない
  （メンバーでないことが分かってしまう403も避け、存在自体を明かさない）。

主なエンドポイント:
- GET  /api/rooms/my-rooms                          : わたしのおへや一覧
- GET  /api/rooms/invitations                        : 自分宛のおさそい一覧
- POST /api/rooms/create                             : おへやを つくる
- POST /api/rooms/{room_id}/invite                   : おともだちを しょうたいする
- POST /api/rooms/invitations/{membership_id}/respond       : キッズ本人の応答
- POST /api/rooms/invitations/{membership_id}/parent-approve: 保護者の承認
- GET  /api/rooms/parent/pending-approvals           : 保護者向け：承認待ち一覧
- GET  /api/rooms/{room_id}                          : おへや詳細（正式メンバーのみ）
"""

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import get_active_user, get_current_parent
from app.database import get_db
from app.models import Room, RoomMember, User

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


def _serialize_room_summary(room: Room) -> dict:
    return {
        "id": room.id,
        "name": room.name,
        "icon": room.icon or "🏠",
    }


def _serialize_member(member: RoomMember) -> dict:
    return {
        "id": member.id,
        "room_id": member.room_id,
        "kid_id": member.kid_id,
        "kid_name": member.kid.display_name if member.kid else None,
        "kid_avatar": member.kid.avatar_icon if member.kid else None,
        "status": member.status,
    }


def _get_active_membership(db: Session, room_id: int, kid_id: int) -> RoomMember | None:
    return (
        db.query(RoomMember)
        .filter(
            RoomMember.room_id == room_id,
            RoomMember.kid_id == kid_id,
            RoomMember.status == "active",
        )
        .first()
    )


# ------------------------------------------------------------------
# わたしのおへや（自分が正式メンバーのおへやだけ）
# ------------------------------------------------------------------
@router.get("/my-rooms")
async def my_rooms(
    user: User | None = Depends(get_active_user), db: Session = Depends(get_db)
):
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    memberships = (
        db.query(RoomMember)
        .options(joinedload(RoomMember.room))
        .filter(RoomMember.kid_id == user.id, RoomMember.status == "active")
        .all()
    )
    rooms = [m.room for m in memberships if m.room and m.room.is_active]
    return JSONResponse(
        {"success": True, "rooms": [_serialize_room_summary(r) for r in rooms]}
    )


# ------------------------------------------------------------------
# おへやの おさそい（招待）一覧：本人がまだ応答していない／保護者承認待ちのもの
# ------------------------------------------------------------------
@router.get("/invitations")
async def list_invitations(
    user: User | None = Depends(get_active_user), db: Session = Depends(get_db)
):
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    memberships = (
        db.query(RoomMember)
        .options(joinedload(RoomMember.room))
        .filter(
            RoomMember.kid_id == user.id,
            RoomMember.status.in_(["invited", "accepted"]),
        )
        .all()
    )
    result = []
    for m in memberships:
        if not m.room:
            continue
        result.append(
            {
                "membership_id": m.id,
                "room": _serialize_room_summary(m.room),
                # "invited"  : 本人がまだ応答していない（さんかする／やめておく を選べる）
                # "accepted" : 本人は「さんかする」を選んだが、保護者の承認待ち
                "status": m.status,
            }
        )
    return JSONResponse({"success": True, "invitations": result})


# ------------------------------------------------------------------
# おへやを つくる（作成者は自動的に正式メンバーになる）
# ------------------------------------------------------------------
@router.post("/create")
async def create_room(
    name: str = Form("おへや"),
    icon: str = Form("🏠"),
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    room = Room(
        name=(name or "").strip()[:50] or "おへや",
        icon=(icon or "🏠")[:20],
        created_by_kid_id=user.id,
    )
    db.add(room)
    db.commit()
    db.refresh(room)

    now = dt.datetime.utcnow()
    owner_membership = RoomMember(
        room_id=room.id,
        kid_id=user.id,
        status="active",
        kid_responded_at=now,
        parent_approved_at=now,
        joined_at=now,
    )
    db.add(owner_membership)
    db.commit()

    return JSONResponse({"success": True, "room": _serialize_room_summary(room)})


# ------------------------------------------------------------------
# おへやに おともだちを しょうたいする（正式メンバーのみ実行可）
# ------------------------------------------------------------------
@router.post("/{room_id}/invite")
async def invite_to_room(
    room_id: int,
    receiver_kid_id: int = Form(...),
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    membership = _get_active_membership(db, room_id, user.id)
    if membership is None:
        # メンバーでない場合、おへやの存在すら明かさない
        raise HTTPException(status_code=404, detail="おへやが みつかりません")

    receiver = (
        db.query(User).filter(User.id == receiver_kid_id, User.role == "kids").first()
    )
    if receiver is None:
        raise HTTPException(status_code=404, detail="しょうたいする あいてが みつかりません")
    if receiver.id == user.id:
        raise HTTPException(status_code=400, detail="じぶん自身は しょうたいできません")

    existing = (
        db.query(RoomMember)
        .filter(RoomMember.room_id == room_id, RoomMember.kid_id == receiver.id)
        .first()
    )
    if existing and existing.status in ("invited", "accepted", "active"):
        return JSONResponse({"success": True, "membership": _serialize_member(existing)})

    if existing:
        existing.status = "invited"
        existing.invited_by_kid_id = user.id
        existing.kid_responded_at = None
        existing.parent_approved_at = None
        existing.joined_at = None
        member = existing
    else:
        member = RoomMember(
            room_id=room_id,
            kid_id=receiver.id,
            status="invited",
            invited_by_kid_id=user.id,
        )
        db.add(member)

    db.commit()
    db.refresh(member)
    return JSONResponse({"success": True, "membership": _serialize_member(member)})


# ------------------------------------------------------------------
# キッズ本人が おさそいに 応答する（さんかする／やめておく）
# ------------------------------------------------------------------
@router.post("/invitations/{membership_id}/respond")
async def respond_invitation(
    membership_id: int,
    decision: str = Form(...),  # "accept" or "decline"
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")
    if decision not in ("accept", "decline"):
        raise HTTPException(status_code=400, detail="不正な回答です")

    member = (
        db.query(RoomMember)
        .filter(RoomMember.id == membership_id, RoomMember.kid_id == user.id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="おさそいが みつかりません")
    if member.status != "invited":
        return JSONResponse({"success": True, "membership": _serialize_member(member)})

    if decision == "decline":
        member.status = "declined"
    else:
        member.status = "accepted"
        member.kid_responded_at = dt.datetime.utcnow()

    db.commit()
    db.refresh(member)
    return JSONResponse({"success": True, "membership": _serialize_member(member)})


# ------------------------------------------------------------------
# 保護者が おへやへの さんかを 承認する
# ------------------------------------------------------------------
@router.post("/invitations/{membership_id}/parent-approve")
async def parent_approve_invitation(
    membership_id: int,
    decision: str = Form(...),  # "approve" or "reject"
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="不正な回答です")

    member = (
        db.query(RoomMember)
        .options(joinedload(RoomMember.kid))
        .filter(RoomMember.id == membership_id)
        .first()
    )
    if member is None or not member.kid or member.kid.parent_id != parent.id:
        raise HTTPException(status_code=404, detail="おさそいが みつかりません")

    if member.status != "accepted":
        return JSONResponse({"success": True, "membership": _serialize_member(member)})

    if decision == "reject":
        member.status = "declined"
    else:
        member.status = "active"
        member.parent_approved_at = dt.datetime.utcnow()
        member.joined_at = dt.datetime.utcnow()

    db.commit()
    db.refresh(member)
    return JSONResponse({"success": True, "membership": _serialize_member(member)})


# ------------------------------------------------------------------
# 保護者向け：承認待ちの おへや参加リクエスト一覧
# ------------------------------------------------------------------
@router.get("/parent/pending-approvals")
async def parent_pending_approvals(
    parent: User | None = Depends(get_current_parent), db: Session = Depends(get_db)
):
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    kid_ids = [
        k.id
        for k in db.query(User)
        .filter(User.parent_id == parent.id, User.role == "kids")
        .all()
    ]
    if not kid_ids:
        return JSONResponse({"success": True, "approvals": []})

    members = (
        db.query(RoomMember)
        .options(joinedload(RoomMember.kid), joinedload(RoomMember.room))
        .filter(RoomMember.kid_id.in_(kid_ids), RoomMember.status == "accepted")
        .all()
    )
    approvals = [
        {
            "membership_id": m.id,
            "kid_name": m.kid.display_name if m.kid else None,
            "room": _serialize_room_summary(m.room) if m.room else None,
        }
        for m in members
    ]
    return JSONResponse({"success": True, "approvals": approvals})


# ------------------------------------------------------------------
# おへや詳細（正式メンバーのみアクセス可能。それ以外は常に404）
# ------------------------------------------------------------------
@router.get("/{room_id}")
async def get_room_detail(
    room_id: int,
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if user is None or user.role != "kids":
        raise HTTPException(status_code=401, detail="キッズとしてログインしてください")

    membership = _get_active_membership(db, room_id, user.id)
    if membership is None:
        # メンバーでない場合はデータの存在自体を明かさない（403ではなく404）
        raise HTTPException(status_code=404, detail="おへやが みつかりません")

    room = db.query(Room).filter(Room.id == room_id, Room.is_active == True).first()  # noqa: E712
    if room is None:
        raise HTTPException(status_code=404, detail="おへやが みつかりません")

    active_members = (
        db.query(RoomMember)
        .options(joinedload(RoomMember.kid))
        .filter(RoomMember.room_id == room_id, RoomMember.status == "active")
        .all()
    )

    return JSONResponse(
        {
            "success": True,
            "room": _serialize_room_summary(room),
            "members": [_serialize_member(m) for m in active_members],
        }
    )
