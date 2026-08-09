"""
RoomPromise / RoomPromiseApproval モデル（ひろば）

「おへや」内の3つ目のタブ「やくそく（約束をするへや）」用のシンプルな
遊ぶ約束モデル。既存の Promise（1対1・保護者承認フロー）とは異なり、
おへやメンバー全員に対してオープンに提示され、メンバーが自分の
アイコンをタップするだけで「✔ さんかする！」を表明できるポップな
カード形式にする（文字入力は最小限、保護者承認は必須にしない）。

- RoomPromise      : 「いつ？」「どこで？」「なにをする？」の3項目からなる
                      約束の提案（おへやの正式メンバーが作成できる）。
- RoomPromiseApproval : メンバーが「さんかする！」をタップしたことを表す
                      レコード（Reactionと同様、行が存在する＝参加表明）。
                      再タップで取り消し（行を削除）できる。
"""

import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


class RoomPromise(Base):
    """おへやメンバー向けの「やくそく」提案カード"""

    __tablename__ = "room_promises"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    created_by_kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 「いつ？」「どこで？」「なにをする？」（タップ選択 or 簡単な文字入力）
    when_text = Column(String(100), nullable=False, default="")
    where_text = Column(String(100), nullable=False, default="")
    what_text = Column(String(100), nullable=False, default="")

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    room = relationship("Room")
    creator = relationship("User", foreign_keys=[created_by_kid_id])
    approvals = relationship(
        "RoomPromiseApproval", back_populates="room_promise", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RoomPromise id={self.id} room_id={self.room_id}>"


class RoomPromiseApproval(Base):
    """メンバーの「さんかする！」表明（緑の✔チェックマーク表示用）"""

    __tablename__ = "room_promise_approvals"

    id = Column(Integer, primary_key=True, index=True)
    room_promise_id = Column(
        Integer, ForeignKey("room_promises.id"), nullable=False, index=True
    )
    kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    room_promise = relationship("RoomPromise", back_populates="approvals")
    kid = relationship("User", foreign_keys=[kid_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RoomPromiseApproval room_promise_id={self.room_promise_id} kid_id={self.kid_id}>"
