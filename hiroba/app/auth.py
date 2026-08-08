"""
認証・セッション管理ヘルパー（ひろば）

Cookieベースのセッション（starlette.middleware.sessions.SessionMiddleware）
に以下の2つの情報を保持してログイン状態を管理する。

- parent_id      : ログイン中の保護者の User.id（保護者としてログインしている限り保持）
- active_user_id : 現在「操作中」のプロフィールの User.id
                    （保護者自身、またはその配下のキッズのいずれか）

キッズは文字入力ができないため、保護者がログインしたあとにキッズの
アイコンをタップして「切り替える」ことで active_user_id を更新する。
投稿・リアクションなどキッズの操作はすべて active_user_id を基準に行う。
"""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

PARENT_SESSION_KEY = "parent_id"
ACTIVE_SESSION_KEY = "active_user_id"


def login_parent(request: Request, parent: User) -> None:
    """保護者としてログインする（同時にアクティブプロフィールも保護者本人にする）"""
    request.session[PARENT_SESSION_KEY] = parent.id
    request.session[ACTIVE_SESSION_KEY] = parent.id


def select_active_profile(request: Request, user: User) -> None:
    """操作中のプロフィールを切り替える（保護者本人 or 配下のキッズ）"""
    request.session[ACTIVE_SESSION_KEY] = user.id


def logout(request: Request) -> None:
    """完全にログアウトする（保護者・アクティブプロフィールとも解除）"""
    request.session.pop(PARENT_SESSION_KEY, None)
    request.session.pop(ACTIVE_SESSION_KEY, None)


def get_current_parent(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """ログイン中の保護者本人を返す。未ログインなら None。"""
    parent_id = request.session.get(PARENT_SESSION_KEY)
    if not parent_id:
        return None
    return (
        db.query(User)
        .filter(User.id == parent_id, User.role == "parent")
        .first()
    )


def get_active_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """現在操作中のプロフィール（保護者本人、または選択中のキッズ）を返す。"""
    active_id = request.session.get(ACTIVE_SESSION_KEY)
    if not active_id:
        return None
    return db.query(User).filter(User.id == active_id).first()
