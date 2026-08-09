"""
LINEログイン／Googleログイン（本番OAuth 2.0 認証フロー）の検証テスト

外部プロバイダへの実際のHTTP通信は行わず、app.services.oauth_service の
トークン交換・プロフィール取得関数を monkeypatch して、
「認可URLへのリダイレクト → コールバック → 既存/新規保護者のログイン」
というフロー全体をエンドツーエンドで検証する。
"""

from urllib.parse import parse_qs, urlparse

from conftest import create_family, new_client

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.services import oauth_service


def _enable_line(monkeypatch):
    monkeypatch.setattr(settings, "LINE_CHANNEL_ID", "test-line-channel-id")
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", "test-line-channel-secret")


def _enable_google(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-google-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-google-client-secret")


def _extract_state(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["state"][0]


# ------------------------------------------------------------------
# LINEログイン
# ------------------------------------------------------------------
def test_line_login_returns_503_when_not_configured():
    client = new_client()
    resp = client.get("/auth/line/login", follow_redirects=False)
    assert resp.status_code == 503


def test_line_login_redirects_to_line_authorize_url(monkeypatch):
    _enable_line(monkeypatch)
    client = new_client()

    resp = client.get("/auth/line/login", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location.startswith(oauth_service.LINE_AUTHORIZE_URL)
    assert "client_id=test-line-channel-id" in location
    assert "state=" in location


def test_line_callback_creates_new_parent_and_logs_in(monkeypatch):
    _enable_line(monkeypatch)
    client = new_client()

    resp = client.get("/auth/line/login", follow_redirects=False)
    state = _extract_state(resp.headers["location"])

    async def fake_exchange_line_code(code):
        assert code == "dummy-auth-code"
        return {"access_token": "dummy-access-token"}

    async def fake_fetch_line_profile(access_token):
        assert access_token == "dummy-access-token"
        return {"userId": "line-user-001", "displayName": "山田太郎"}

    monkeypatch.setattr(oauth_service, "exchange_line_code", fake_exchange_line_code)
    monkeypatch.setattr(oauth_service, "fetch_line_profile", fake_fetch_line_profile)

    resp = client.get(
        f"/auth/line/callback?code=dummy-auth-code&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 307
    assert resp.headers["location"] == "/select-kid"

    # ログイン状態が確立され、保護者として認識される
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["logged_in"] is True
    assert body["user"]["role"] == "parent"
    assert body["user"]["display_name"] == "山田太郎"

    db = SessionLocal()
    try:
        parent = db.query(User).filter(User.line_user_id == "line-user-001").first()
        assert parent is not None
        assert parent.role == "parent"
    finally:
        db.close()


def test_line_callback_existing_line_user_logs_into_same_account(monkeypatch):
    _enable_line(monkeypatch)

    async def fake_exchange_line_code(code):
        return {"access_token": "tok"}

    async def fake_fetch_line_profile(access_token):
        return {"userId": "line-user-existing", "displayName": "既存さん"}

    monkeypatch.setattr(oauth_service, "exchange_line_code", fake_exchange_line_code)
    monkeypatch.setattr(oauth_service, "fetch_line_profile", fake_fetch_line_profile)

    # 1回目：新規登録
    client1 = new_client()
    resp = client1.get("/auth/line/login", follow_redirects=False)
    state1 = _extract_state(resp.headers["location"])
    client1.get(f"/auth/line/callback?code=abc&state={state1}", follow_redirects=False)
    parent_id_1 = client1.get("/api/auth/me").json()["user"]["id"]

    # 2回目：別デバイス（別クライアント）から同じLINEアカウントでログイン→同一アカウントに紐づく
    client2 = new_client()
    resp = client2.get("/auth/line/login", follow_redirects=False)
    state2 = _extract_state(resp.headers["location"])
    client2.get(f"/auth/line/callback?code=def&state={state2}", follow_redirects=False)
    parent_id_2 = client2.get("/api/auth/me").json()["user"]["id"]

    assert parent_id_1 == parent_id_2

    db = SessionLocal()
    try:
        count = (
            db.query(User)
            .filter(User.line_user_id == "line-user-existing")
            .count()
        )
        assert count == 1
    finally:
        db.close()


def test_line_callback_rejects_invalid_state(monkeypatch):
    _enable_line(monkeypatch)
    client = new_client()
    client.get("/auth/line/login", follow_redirects=False)

    resp = client.get(
        "/auth/line/callback?code=whatever&state=totally-wrong-state",
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_line_callback_without_prior_login_call_is_rejected(monkeypatch):
    """stateをセッションに保存する /auth/line/login を経ずに直接callbackを叩いても拒否される"""
    _enable_line(monkeypatch)
    client = new_client()
    resp = client.get(
        "/auth/line/callback?code=whatever&state=some-state",
        follow_redirects=False,
    )
    assert resp.status_code == 400


# ------------------------------------------------------------------
# Googleログイン
# ------------------------------------------------------------------
def test_google_login_returns_503_when_not_configured():
    client = new_client()
    resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code == 503


def test_google_login_redirects_to_google_authorize_url(monkeypatch):
    _enable_google(monkeypatch)
    client = new_client()

    resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location.startswith(oauth_service.GOOGLE_AUTHORIZE_URL)
    assert "client_id=test-google-client-id" in location
    assert "state=" in location


def test_google_callback_creates_new_parent_and_logs_in(monkeypatch):
    _enable_google(monkeypatch)
    client = new_client()

    resp = client.get("/auth/google/login", follow_redirects=False)
    state = _extract_state(resp.headers["location"])

    async def fake_exchange_google_code(code):
        assert code == "dummy-google-code"
        return {"access_token": "dummy-google-token"}

    async def fake_fetch_google_userinfo(access_token):
        assert access_token == "dummy-google-token"
        return {
            "sub": "google-user-001",
            "email": "taro@example.com",
            "name": "グーグル太郎",
        }

    monkeypatch.setattr(oauth_service, "exchange_google_code", fake_exchange_google_code)
    monkeypatch.setattr(oauth_service, "fetch_google_userinfo", fake_fetch_google_userinfo)

    resp = client.get(
        f"/auth/google/callback?code=dummy-google-code&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 307
    assert resp.headers["location"] == "/select-kid"

    resp = client.get("/api/auth/me")
    body = resp.json()
    assert body["logged_in"] is True
    assert body["user"]["role"] == "parent"
    assert body["user"]["display_name"] == "グーグル太郎"

    db = SessionLocal()
    try:
        parent = db.query(User).filter(User.google_user_id == "google-user-001").first()
        assert parent is not None
        assert parent.email == "taro@example.com"
    finally:
        db.close()


def test_google_callback_links_to_existing_account_by_email(monkeypatch):
    """既に電話番号ログインで作成済みの保護者と同じemailなら、そのアカウントに紐づく（新規作成しない）"""
    _enable_google(monkeypatch)

    # 既存の保護者アカウント（電話番号ログイン）を作成し、キッズも登録しておく
    existing_client = new_client()
    family = create_family(existing_client, "07900000001", "花子", "こどもH1")

    db = SessionLocal()
    try:
        parent = db.query(User).filter(User.id == family["parent_id"]).first()
        parent.email = "hanako@example.com"
        db.commit()
    finally:
        db.close()

    google_client = new_client()
    resp = google_client.get("/auth/google/login", follow_redirects=False)
    state = _extract_state(resp.headers["location"])

    async def fake_exchange_google_code(code):
        return {"access_token": "tok2"}

    async def fake_fetch_google_userinfo(access_token):
        return {
            "sub": "google-user-linked",
            "email": "hanako@example.com",
            "name": "花子（Google表示名）",
        }

    monkeypatch.setattr(oauth_service, "exchange_google_code", fake_exchange_google_code)
    monkeypatch.setattr(oauth_service, "fetch_google_userinfo", fake_fetch_google_userinfo)

    google_client.get(
        f"/auth/google/callback?code=g-code&state={state}", follow_redirects=False
    )

    resp = google_client.get("/api/auth/me")
    body = resp.json()
    assert body["user"]["id"] == family["parent_id"]

    # 既存のキッズがそのまま見える（＝同一保護者アカウントに紐づいている）
    resp = google_client.get("/api/auth/kids")
    names = [k["display_name"] for k in resp.json()["kids"]]
    assert "こどもH1" in names

    db = SessionLocal()
    try:
        count = db.query(User).filter(User.email == "hanako@example.com").count()
        assert count == 1
    finally:
        db.close()


def test_google_callback_rejects_invalid_state(monkeypatch):
    _enable_google(monkeypatch)
    client = new_client()
    client.get("/auth/google/login", follow_redirects=False)

    resp = client.get(
        "/auth/google/callback?code=whatever&state=totally-wrong-state",
        follow_redirects=False,
    )
    assert resp.status_code == 400
