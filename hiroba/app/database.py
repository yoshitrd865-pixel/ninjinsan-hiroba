"""
データベース接続設定（ひろば専用）

「縁側」とは完全に独立したデータベースを使用する。
デフォルトでは SQLite (hiroba.db) を使用する。
本番運用時は環境変数 HIROBA_DATABASE_URL を設定することで
PostgreSQL 等に切り替えられる。
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BASE_DIR / "hiroba.db"

DATABASE_URL = os.environ.get(
    "HIROBA_DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}"
)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI の Depends 用データベースセッション取得関数"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """アプリ起動時にテーブルを作成する"""
    # モデルをインポートしてから create_all することで登録を確実にする
    from app.models import user, post, reaction  # noqa: F401

    Base.metadata.create_all(bind=engine)
