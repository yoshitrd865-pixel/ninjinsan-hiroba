"""
LINEログイン／Googleログイン 本番OAuth 2.0 認証フロー（ひろば）

保護者はこれまでの「電話番号＋開発用ダミーSMS認証コード」に加えて、
LINEアカウントまたはGoogleアカウントでログインできる。

フロー（Authorization Code フロー）:
1. GET /auth/line/login または /auth/google/login
   - CSRF対策用のランダムな state をセッションに保存し、
     各プロバイダの認可画面へリダイレクトする。
2. ユーザーがプロバイダ側でログイン・許可する。
3. GET /auth/line/callback または /auth/google/callback
   - state を検証し、認可コードをアクセストークンに交換する。
   - アクセストークンでユーザープロフィール（LINE: userId/displayName、
     Google: sub/email/name）を取得する。
   - そのプロバイダIDに紐づく保護者アカウントが既にあればログインし、
     なければ新規登録してログインする（=既存/新規どちらでも
     app.auth.login_parent() でセッションを確立し、ダッシュボード
     もしくはキッズ選択画面へ遷移する）。

開発・テスト時は LINE_CHANNEL_ID 等の環境変数が未設定のため、
/auth/line/login 等は503（未設定の案内）を返す。実際の外部通信を
伴う exchange_*/fetch_* 関数はテストで monkeypatch して検証する。
"""

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import login_parent
from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.services import oauth_service

logger = logging.getLogger("hiroba.oauth")

router = APIRouter(prefix="/auth", tags=["oauth"])

LINE_STATE_KEY = "oauth_line_state"
GOOGLE_STATE_KEY = "oauth_google_state"

# ログイン成功後の遷移先（キッズ選択画面。保護者はここでキッズを選ぶかそのまま保護者として使う）
LOGIN_SUCCESS_REDIRECT = "/select-kid"
LOGIN_FAILURE_REDIRECT = "/login"


def _new_state() -> str:
    return secrets.token_urlsafe(24)


def _find_or_create_parent_by_line(db: Session, line_user_id: str, display_name: str) -> User:
    """LINEのuserIdに紐づく保護者を取得、なければ新規登録する（既存/新規の統合ロジック）"""
    parent = (
        db.query(User)
        .filter(User.role == "parent", User.line_user_id == line_user_id)
        .first()
    )
    if parent:
        return parent

    parent = User(
        role="parent",
        display_name=(display_name or "保護者").strip() or "保護者",
        line_user_id=line_user_id,
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)
    return parent


def _find_or_create_parent_by_google(
    db: Session, google_user_id: str, email: str | None, display_name: str
) -> User:
    """GoogleのsubIDに紐づく保護者を取得、なければ（メール一致で既存を紐付け or）新規登録する"""
    parent = (
        db.query(User)
        .filter(User.role == "parent", User.google_user_id == google_user_id)
        .first()
    )
    if parent:
        return parent

    # 既に電話番号ログイン等で登録済みのメールアドレスがあれば、そのアカウントに紐付ける
    if email:
        parent = (
            db.query(User)
            .filter(User.role == "parent", User.email == email)
            .first()
        )
        if parent:
            parent.google_user_id = google_user_id
            db.commit()
            db.refresh(parent)
            return parent

    parent = User(
        role="parent",
        display_name=(display_name or "保護者").strip() or "保護者",
        email=email,
        google_user_id=google_user_id,
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)
    return parent


# ------------------------------------------------------------------
# LINEログイン
# ------------------------------------------------------------------
@router.get("/line/login")
async def line_login(request: Request):
    """LINEの認可画面へリダイレクトする"""
    if not settings.line_login_enabled:
        raise HTTPException(
            status_code=503,
            detail="LINEログインは現在利用できません（LINE_CHANNEL_ID/SECRET未設定）",
        )

    state = _new_state()
    request.session[LINE_STATE_KEY] = state
    return RedirectResponse(url=oauth_service.build_line_authorize_url(state))


@router.get("/line/callback")
async def line_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """LINEからのコールバックを受け取り、保護者としてログイン/新規登録する"""
    if not settings.line_login_enabled:
        raise HTTPException(status_code=503, detail="LINEログインは現在利用できません")

    expected_state = request.session.pop(LINE_STATE_KEY, None)

    if error:
        logger.info("[LINEログイン] ユーザーが認可を拒否またはエラー: %s", error)
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)

    if not code or not state or not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="不正なリクエストです（state不一致）")

    try:
        token_data = await oauth_service.exchange_line_code(code)
        access_token = token_data["access_token"]
        profile = await oauth_service.fetch_line_profile(access_token)
    except Exception:  # noqa: BLE001
        logger.exception("[LINEログイン] トークン交換/プロフィール取得に失敗しました")
        raise HTTPException(status_code=502, detail="LINEログインに失敗しました")

    line_user_id = profile.get("userId")
    display_name = profile.get("displayName", "保護者")
    if not line_user_id:
        raise HTTPException(status_code=502, detail="LINEプロフィールの取得に失敗しました")

    db = SessionLocal()
    try:
        parent = _find_or_create_parent_by_line(db, line_user_id, display_name)
        login_parent(request, parent)
    finally:
        db.close()

    return RedirectResponse(url=LOGIN_SUCCESS_REDIRECT)


# ------------------------------------------------------------------
# Googleログイン
# ------------------------------------------------------------------
@router.get("/google/login")
async def google_login(request: Request):
    """Googleの認可画面へリダイレクトする"""
    if not settings.google_login_enabled:
        raise HTTPException(
            status_code=503,
            detail="Googleログインは現在利用できません（GOOGLE_CLIENT_ID/SECRET未設定）",
        )

    state = _new_state()
    request.session[GOOGLE_STATE_KEY] = state
    return RedirectResponse(url=oauth_service.build_google_authorize_url(state))


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Googleからのコールバックを受け取り、保護者としてログイン/新規登録する"""
    if not settings.google_login_enabled:
        raise HTTPException(status_code=503, detail="Googleログインは現在利用できません")

    expected_state = request.session.pop(GOOGLE_STATE_KEY, None)

    if error:
        logger.info("[Googleログイン] ユーザーが認可を拒否またはエラー: %s", error)
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)

    if not code or not state or not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="不正なリクエストです（state不一致）")

    try:
        token_data = await oauth_service.exchange_google_code(code)
        access_token = token_data["access_token"]
        userinfo = await oauth_service.fetch_google_userinfo(access_token)
    except Exception:  # noqa: BLE001
        logger.exception("[Googleログイン] トークン交換/ユーザー情報取得に失敗しました")
        raise HTTPException(status_code=502, detail="Googleログインに失敗しました")

    google_user_id = userinfo.get("sub")
    email = userinfo.get("email")
    display_name = userinfo.get("name", "保護者")
    if not google_user_id:
        raise HTTPException(status_code=502, detail="Googleユーザー情報の取得に失敗しました")

    db = SessionLocal()
    try:
        parent = _find_or_create_parent_by_google(db, google_user_id, email, display_name)
        login_parent(request, parent)
    finally:
        db.close()

    return RedirectResponse(url=LOGIN_SUCCESS_REDIRECT)
