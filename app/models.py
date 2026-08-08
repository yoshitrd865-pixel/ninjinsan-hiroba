"""
SQLAlchemy モデル定義
"""

import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """利用者（電話番号でログインする）"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    display_name = Column(String(50), default="ゲスト")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship(
        "ChatMessage", back_populates="user", cascade="all, delete-orphan"
    )


class SmsCode(Base):
    """SMS認証コード

    開発モードでは実際にSMSを送信せず、生成したコードを
    レスポンスに含めて画面表示する。
    本番でTwilio等を連携する場合は app/services/sms_service.py
    の send_sms() を実装すればよい。
    """

    __tablename__ = "sms_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), index=True, nullable=False)
    code = Column(String(4), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Post(Base):
    """かんたん投稿（写真＋気分スタンプ）"""

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    image_path = Column(String(255), nullable=True)
    stamp = Column(String(10), nullable=False)
    stamp_label = Column(String(30), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", back_populates="posts")
    reactions = relationship(
        "PostReaction", back_populates="post", cascade="all, delete-orphan"
    )


class PostReaction(Base):
    """投稿への反応（🌸温かいね／📣応援する）

    Instagramの「いいね」のような機能。同じユーザーが同じ投稿に
    同じ種類のリアクションを二重に押せないよう一意制約を設けている。
    もう一度押すと解除（トグル）される。
    """

    __tablename__ = "post_reactions"
    __table_args__ = (
        UniqueConstraint(
            "post_id", "user_id", "reaction_type", name="uq_post_user_reaction"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reaction_type = Column(String(20), nullable=False)  # "warm" または "cheer"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    post = relationship("Post", back_populates="reactions")
    user = relationship("User")


class ChatMessage(Base):
    """AIとのおしゃべりチャット履歴"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(10), nullable=False)  # "user" または "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", back_populates="chat_messages")
