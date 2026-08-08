"""
pytest共通設定（ひろば）

- テスト専用のSQLiteファイルを使い、本番/開発用の hiroba.db を汚さない。
- 環境変数 HIROBA_DATABASE_URL は「app.database」がインポートされる前に
  設定しておく必要があるため、このファイルの先頭（他のimportより前）で設定する。
"""

import os
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
HIROBA_DIR = TESTS_DIR.parent  # hiroba/

# "app" パッケージ（hiroba/app）を解決できるようにする
if str(HIROBA_DIR) not in sys.path:
    sys.path.insert(0, str(HIROBA_DIR))

TEST_DB_PATH = TESTS_DIR / "test_hiroba.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["HIROBA_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ.setdefault("HIROBA_SECRET_KEY", "test-secret-key")
# OpenAIキーが誤って設定されていてもAI呼び出しをしないようにする
os.environ.pop("OPENAI_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    """テストセッション全体で1回だけテーブルを作成する"""
    # モデルをインポートしてメタデータに登録してから作成する
    from app.models import promise, reaction, room, post, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield
    try:
        Base.metadata.drop_all(bind=engine)
    except Exception:
        pass
    engine.dispose()
    try:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
    except PermissionError:
        # Windows ではSQLite接続がすぐに解放されないことがあるため、
        # テスト用ファイルの削除失敗はテスト結果に影響させない
        pass



def new_client() -> TestClient:
    """新しい「ブラウザ／デバイス」を模したTestClientを返す（独立したcookie jarを持つ）"""
    return TestClient(app)


def create_family(client: TestClient, phone_number: str, parent_name: str, kid_name: str, avatar: str = "🧒") -> dict:
    """保護者アカウント＋キッズアカウントを作成し、キッズをアクティブプロフィールにする

    戻り値: {"parent_id": int, "kid_id": int}
    """
    resp = client.post("/api/auth/send-code", data={"phone_number": phone_number})
    assert resp.status_code == 200, resp.text
    code = resp.json()["debug_code"]

    resp = client.post(
        "/api/auth/verify-code",
        data={"phone_number": phone_number, "code": code, "display_name": parent_name},
    )
    assert resp.status_code == 200, resp.text
    parent_id = resp.json()["parent"]["id"]

    resp = client.post(
        "/api/auth/kids/add",
        data={"display_name": kid_name, "avatar_icon": avatar, "pin_code": ""},
    )
    assert resp.status_code == 200, resp.text
    kid_id = resp.json()["kid"]["id"]

    resp = client.post(f"/api/auth/kids/{kid_id}/select", data={"pin_code": ""})
    assert resp.status_code == 200, resp.text

    return {"parent_id": parent_id, "kid_id": kid_id}


def switch_to_parent(client: TestClient) -> None:
    """アクティブプロフィールを保護者本人に戻す"""
    resp = client.post("/api/auth/select-parent")
    assert resp.status_code == 200, resp.text


def switch_to_kid(client: TestClient, kid_id: int) -> None:
    resp = client.post(f"/api/auth/kids/{kid_id}/select", data={"pin_code": ""})
    assert resp.status_code == 200, resp.text
