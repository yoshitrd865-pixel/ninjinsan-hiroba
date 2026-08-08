"""
User モデル（ひろば）

保護者アカウントとキッズアカウントの両方をこのモデルで管理する。
- role="parent" : 保護者。メール＋パスワードでログインし、複数のキッズを紐づけられる。
- role="kids"   : キッズ。文字入力不要なので、アイコン選択＋4桁PINでログインする想定。
  parent_id で保護者アカウントに紐づく。
"""

import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """保護者・キッズを管理するアカウントモデル"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # "parent"（保護者） または "kids"（キッズ）
    role = Column(String(10), nullable=False, default="kids", index=True)

    # 表示名（キッズはニックネーム、保護者は名前）
    display_name = Column(String(50), nullable=False, default="ゲスト")

    # キッズがログイン時に選ぶアイコン（絵文字やイラストのキー）
    avatar_icon = Column(String(50), nullable=True)

    # --- 保護者ログイン用（電話番号＋開発用ダミーSMSコードでログイン） ---
    phone_number = Column(String(20), unique=True, index=True, nullable=True)
    email = Column(String(120), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)


    # --- キッズログイン用（文字入力不要：アイコン選択＋4桁PIN） ---
    pin_code = Column(String(4), nullable=True)

    # キッズは必ず保護者に紐づく（保護者が作成・管理する）
    parent_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # 保護者からみた、自分が管理するキッズアカウント一覧
    children = relationship(
        "User",
        backref="parent",
        remote_side=[id],
        cascade="all",
    )

    posts = relationship(
        "Post", back_populates="user", cascade="all, delete-orphan"
    )
    reactions = relationship(
        "Reaction", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} role={self.role} name={self.display_name!r}>"
