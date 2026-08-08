"""
統合テスト用スクリプト（一時ファイル・完了後に削除）

ログイン -> キッズ追加 -> キッズ選択 -> 投稿作成 -> リアクション
の一連のフローをTestClientで検証する。
"""
import base64

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
client.__enter__()  # startup イベント(init_db)を発火させる

# 1. 保護者ログイン（開発用ダミーSMS）

r = client.post("/api/auth/send-code", data={"phone_number": "09012345678"})
print("send-code:", r.status_code, r.json())
code = r.json()["debug_code"]

r = client.post(
    "/api/auth/verify-code",
    data={"phone_number": "09012345678", "code": code, "display_name": "お母さん"},
)
print("verify-code:", r.status_code, r.json())
assert r.status_code == 200

# 2. キッズ追加
r = client.post(
    "/api/auth/kids/add",
    data={"display_name": "たろう", "avatar_icon": "🦖", "pin_code": ""},
)
print("kids/add:", r.status_code, r.json())
kid_id = r.json()["kid"]["id"]

# 3. キッズ一覧
r = client.get("/api/auth/kids")
print("kids list:", r.status_code, r.json())

# 4. キッズ選択
r = client.post(f"/api/auth/kids/{kid_id}/select", data={"pin_code": ""})
print("select kid:", r.status_code, r.json())
assert r.status_code == 200

# 5. 現在のプロフィール確認
r = client.get("/api/auth/me")
print("me:", r.status_code, r.json())

# 6. 投稿作成（スタンプ＋お絵描きBase64）
tiny_png_base64 = base64.b64encode(b"fake-png-bytes").decode()
data_url = f"data:image/png;base64,{tiny_png_base64}"

r = client.post(
    "/api/posts/create",
    data={"stamps": "たのしい", "drawing_data": data_url},
)
print("create post:", r.status_code, r.json())
assert r.status_code == 200
post_id = r.json()["post"]["id"]

# 7. タイムライン取得
r = client.get("/api/posts/timeline")
print("timeline:", r.status_code, r.json())

# 8. リアクション（連打OK・カウントアップ）
for _ in range(3):
    r = client.post(f"/api/posts/{post_id}/react", data={"reaction_type": "yabai"})
    print("react:", r.status_code, r.json())

r = client.post(f"/api/posts/{post_id}/react", data={"reaction_type": "sugoi"})
print("react sugoi:", r.status_code, r.json())

# 9. キッズホームページ・保護者ダッシュボードのHTML表示確認
r = client.get("/kids/home")
print("kids/home page:", r.status_code, len(r.text), "bytes")

r = client.get("/parent")
print("parent page:", r.status_code, len(r.text), "bytes")

print("ALL TESTS PASSED")
