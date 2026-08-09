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

# キッズの学年選択肢（保護者がキッズ登録・編集時にタップ選択する）
GRADE_OPTIONS = (
    "年少",
    "年中",
    "年長",
    "小1",
    "小2",
    "小3",
    "小4",
    "小5",
    "小6",
    "中1",
    "中2",
    "中3",
)


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

    # キッズの学年（保護者が /parent/children/new・/parent/children で登録・編集する）
    # GRADE_OPTIONS のいずれか、または未設定(None)
    grade = Column(String(10), nullable=True)

    # --- 保護者ログイン用（電話番号＋開発用ダミーSMSコードでログイン） ---
    phone_number = Column(String(20), unique=True, index=True, nullable=True)
    email = Column(String(120), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)


    # --- キッズログイン用（文字入力不要：アイコン選択＋4桁PIN） ---
    pin_code = Column(String(4), nullable=True)

    # キッズは必ず保護者に紐づく（保護者が作成・管理する）
    parent_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # --- 保護者向けLINE通知設定（/parent/notifications） ---
    # LINEアカウント連携時に発行される想定のID（開発モードでは手動で紐付ける簡易フローのみ提供）
    line_user_id = Column(String(64), unique=True, index=True, nullable=True)
    # LINE通知を送るかどうか（保護者本人のトグル設定。デフォルトはON）
    line_notify_enabled = Column(Boolean, nullable=False, default=True)

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
