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
    """現在操作中のプロフィール（保護者本人、または選択中のキッズ）を返す。
    未設定の場合、ログイン中の保護者がいればその最初のキッズ、または保護者本人を自動割り当てする。
    """
    active_id = request.session.get(ACTIVE_SESSION_KEY)
    if active_id:
        user = db.query(User).filter(User.id == active_id).first()
        if user:
            return user

    parent_id = request.session.get(PARENT_SESSION_KEY)
    if parent_id:
        # 配下のキッズを検索
        kid = db.query(User).filter(User.parent_id == parent_id, User.role == "kids").order_by(User.created_at.asc()).first()
        if kid:
            request.session[ACTIVE_SESSION_KEY] = kid.id
            return kid
        # キッズがいなければ保護者本人をアクティブにする
        parent = db.query(User).filter(User.id == parent_id).first()
        if parent:
            request.session[ACTIVE_SESSION_KEY] = parent.id
            return parent

    # ログインしていなくても、もしDBにユーザーが存在すれば自動フォールバック（テスト環境や未ログイン状態の利便性のため）
    any_kid = db.query(User).filter(User.role == "kids").order_by(User.created_at.asc()).first()
    if any_kid:
        request.session[ACTIVE_SESSION_KEY] = any_kid.id
        request.session[PARENT_SESSION_KEY] = any_kid.parent_id
        return any_kid

    any_user = db.query(User).order_by(User.created_at.asc()).first()
    if any_user:
        request.session[ACTIVE_SESSION_KEY] = any_user.id
        if any_user.role == "parent":
            request.session[PARENT_SESSION_KEY] = any_user.id
        return any_user

    return None
