"""
OAuth 2.0 連携サービス（ひろば）

LINEログイン・Googleログインの本番認証フローで必要な、
外部プロバイダとのHTTP通信（認可URL生成・トークン交換・プロフィール取得）を
まとめたモジュール。

ルーター（app/routers/oauth.py）はこのモジュールの関数を呼び出すだけにし、
実際のHTTP通信の詳細（エンドポイントURL・パラメータ形式等）はここに閉じ込める。
これにより、テストでは本モジュールの関数を monkeypatch するだけで、
実際に外部ネットワークへアクセスせずにログインフロー全体を検証できる。
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.config import google_redirect_uri, line_redirect_uri, settings

# --- LINEログイン（LINE Developers: https://developers.line.biz/） ---
LINE_AUTHORIZE_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
LINE_PROFILE_URL = "https://api.line.me/v2/profile"

# --- Googleログイン（Google Identity Platform / OAuth 2.0） ---
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_HTTP_TIMEOUT = 10.0


# ------------------------------------------------------------------
# LINEログイン
# ------------------------------------------------------------------
def build_line_authorize_url(state: str) -> str:
    """LINEの認可URL（ユーザーをリダイレクトさせるURL）を生成する"""
    params = {
        "response_type": "code",
        "client_id": settings.LINE_CHANNEL_ID,
        "redirect_uri": line_redirect_uri(),
        "state": state,
        "scope": "profile openid",
    }
    return f"{LINE_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_line_code(code: str) -> dict:
    """認可コードをLINEのアクセストークンに交換する

    戻り値には少なくとも "access_token" が含まれる（LINEのトークンエンドポイント仕様）。
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": line_redirect_uri(),
        "client_id": settings.LINE_CHANNEL_ID,
        "client_secret": settings.LINE_CHANNEL_SECRET,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            LINE_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()


async def fetch_line_profile(access_token: str) -> dict:
    """LINEのユーザープロフィール（userId・displayName等）を取得する"""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            LINE_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------------
# Googleログイン
# ------------------------------------------------------------------
def build_google_authorize_url(state: str) -> str:
    """Googleの認可URL（ユーザーをリダイレクトさせるURL）を生成する"""
    params = {
        "response_type": "code",
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": google_redirect_uri(),
        "state": state,
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_google_code(code: str) -> dict:
    """認可コードをGoogleのアクセストークンに交換する

    戻り値には "access_token"・"id_token" 等が含まれる（Googleのトークンエンドポイント仕様）。
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": google_redirect_uri(),
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data=data)
    resp.raise_for_status()
    return resp.json()


async def fetch_google_userinfo(access_token: str) -> dict:
    """Googleのユーザー情報（sub・email・name等）を取得する"""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    resp.raise_for_status()
    return resp.json()
