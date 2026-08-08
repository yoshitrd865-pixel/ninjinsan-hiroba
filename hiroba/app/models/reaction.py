"""
Reaction モデル（ひろば）

キッズ向けに「いいね」の代わりとなる、文字入力不要な4種類のポジティブな
リアクションを提供する。
- yabai      : 「やばい！」
- omoshiroi  : 「おもしろい！」
- sugoi      : 「すごい！」
- suteki     : 「すてき！」

キッズが何度タップしても楽しい「カウントアップ方式」を採用するため、
同一ユーザー・同一投稿・同一リアクション種別の重複連打を禁止する
一意制約は設けていない（1回のタップ = 1レコード追加）。
"""

import datetime
import enum

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class ReactionType(str, enum.Enum):
    """キッズ向けリアクションの種類"""

    YABAI = "yabai"  # やばい！
    OMOSHIROI = "omoshiroi"  # おもしろい！
    SUGOI = "sugoi"  # すごい！
    SUTEKI = "suteki"  # すてき！


REACTION_LABELS = {
    ReactionType.YABAI.value: "やばい！",
    ReactionType.OMOSHIROI.value: "おもしろい！",
    ReactionType.SUGOI.value: "すごい！",
    ReactionType.SUTEKI.value: "すてき！",
}


class Reaction(Base):
    """投稿への4種類のリアクション（やばい！/おもしろい！/すごい！/すてき！）

    連打OK・カウントアップ方式のため、同じユーザーが同じ投稿に同じ
    リアクションを何度送っても、その都度レコードが追加されカウントが増える。
    """

    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # "yabai" / "omoshiroi" / "sugoi" / "suteki"
    reaction_type = Column(String(20), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    post = relationship("Post", back_populates="reactions")
    user = relationship("User", back_populates="reactions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reaction post_id={self.post_id} type={self.reaction_type!r}>"
