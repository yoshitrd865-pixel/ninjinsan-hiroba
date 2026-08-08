"""
Room / RoomMember モデル（ひろば）

「おへや」は招待制・完全クローズドなグループ機能。
参加していない「おへや」の存在は一覧化・検索できず、招待された
キッズ本人と保護者の双方が承認したときのみ、正式メンバー
(RoomMember.status == "active") として扱われ、初めて
「わたしのおへや」に表示される。

RoomMember.status の遷移:
- "invited"  : 招待直後。キッズ本人はまだ応答していない
- "accepted" : キッズ本人は「さんかする」を選んだが、保護者の承認待ち
- "active"   : 保護者も承認済み。正式メンバーとして「わたしのおへや」に表示される
- "declined" : キッズ本人または保護者が断った

サーバーサイドでは、正式メンバー(status=="active")以外のユーザーには
おへやのデータ（投稿・音声・メンバー情報など）を絶対に返さない
（routers/rooms.py 参照）。
"""

import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base

# RoomMember の状態
ROOM_MEMBER_STATUSES = ("invited", "accepted", "active", "declined")


class Room(Base):
    """完全クローズドな「おへや」（招待制グループ）"""

    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, default="おへや")
    icon = Column(String(20), nullable=True, default="🏠")
    created_by_kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    members = relationship(
        "RoomMember", back_populates="room", cascade="all, delete-orphan"
    )
    creator = relationship("User", foreign_keys=[created_by_kid_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Room id={self.id} name={self.name!r}>"


class RoomMember(Base):
    """おへやの正式メンバー（招待〜承認フローの状態を保持）"""

    __tablename__ = "room_members"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # "invited" / "accepted" / "active" / "declined"
    status = Column(String(20), nullable=False, default="invited", index=True)

    invited_by_kid_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    kid_responded_at = Column(DateTime, nullable=True)
    parent_approved_at = Column(DateTime, nullable=True)
    joined_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    room = relationship("Room", back_populates="members")
    kid = relationship("User", foreign_keys=[kid_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RoomMember room_id={self.room_id} kid_id={self.kid_id} status={self.status!r}>"
