"""
Promise モデル（ひろば）

キッズ同士が「公園で遊ぼう」「ゲームしよう」などの遊ぶ約束をした際に、
AIお兄さん・お姉さんが会話やボイスメモの内容から約束の要点（タイトル・
日時・場所）を抽出して作成されるレコード。

安全のため、約束は双方の保護者が承認するまで「成立」しない
（sender側・receiver側それぞれの保護者が個別に承認する）。

status の遷移:
- "pending_parents" : 作成直後。両方またはどちらかの保護者がまだ未回答
- "approved"         : 両方の保護者が承認した（約束成立！）
- "rejected"         : どちらかの保護者が拒否した（即時に確定）
"""

import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Promise(Base):
    """キッズ同士の「遊ぶ約束」（AI司会＋保護者承認フロー）"""

    __tablename__ = "promises"

    id = Column(Integer, primary_key=True, index=True)

    # 約束を提案したキッズ / 約束の相手のキッズ
    sender_kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # AIが抽出した約束の要約タイトル（例:「公園で遊ぼう」）
    title = Column(String(200), nullable=False)

    # AIが抽出した場所・内容の詳細（例:「近くの公園」「オンラインゲーム」）
    place = Column(String(200), nullable=True)

    # AIが抽出した提案日時（わからない場合は None）
    suggested_datetime = Column(DateTime, nullable=True)

    # 抽出元となった会話ログ・ボイスメモの文字化テキスト（保護者確認用）
    raw_text = Column(Text, nullable=True)

    # ボイスメモで約束を提案した場合の音声ファイルURL（任意）
    voice_memo_url = Column(String(255), nullable=True)

    # "pending_parents" / "approved" / "rejected"
    status = Column(String(20), nullable=False, default="pending_parents", index=True)

    # 双方の保護者それぞれの承認状態
    sender_parent_approved = Column(Boolean, nullable=False, default=False)
    receiver_parent_approved = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    sender_kid = relationship("User", foreign_keys=[sender_kid_id])
    receiver_kid = relationship("User", foreign_keys=[receiver_kid_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Promise id={self.id} status={self.status!r} title={self.title!r}>"
