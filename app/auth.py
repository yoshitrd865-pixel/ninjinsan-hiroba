"""
認証ヘルパー

Cookieベースのセッション（starlette.middleware.sessions.SessionMiddleware）
に user_id を保存してログイン状態を管理する。
"""

from fastapi import Request, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

SESSION_KEY = "user_id"


def login_user(request: Request, user: User) -> None:
    request.session[SESSION_KEY] = user.id


def logout_user(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """ログイン中のユーザーを返す。未ログインなら None。"""
    user_id = request.session.get(SESSION_KEY)
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()
