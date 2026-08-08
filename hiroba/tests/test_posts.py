"""
投稿（Post）の削除機能の検証テスト

要件との対応:
- 削除できるのは投稿本人（キッズ）、またはその保護者のみ
- 削除は理由メッセージを出さず、タイムラインから静かに消える（第三者には
  「もともとなかった」ように見える）
- 権限のないユーザーからの削除要求は404で存在自体を明かさない
"""

from conftest import create_family, new_client, switch_to_parent


def _create_post(client, mood_stamp="たのしい"):
    resp = client.post("/api/posts/create", data={"stamps": mood_stamp})
    assert resp.status_code == 200, resp.text
    return resp.json()["post"]


def test_author_can_delete_own_post_and_it_quietly_disappears():
    client = new_client()
    create_family(client, "07011111111", "親P1", "こどもP1")

    post = _create_post(client)
    post_id = post["id"]
    # 本人には can_delete=True が見える
    assert post["can_delete"] is True

    resp = client.get("/api/posts/timeline")
    assert post_id in [p["id"] for p in resp.json()["posts"]]

    # 本人が削除する
    resp = client.post(f"/api/posts/{post_id}/delete")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"success": True}  # 理由や通知メッセージは一切含まれない

    # タイムラインから静かに消える（「削除されました」等の表示は一切ない）
    resp = client.get("/api/posts/timeline")
    assert resp.status_code == 200
    assert post_id not in [p["id"] for p in resp.json()["posts"]]


def test_parent_of_author_can_delete_post():
    """投稿本人の保護者も削除できる"""
    client = new_client()
    create_family(client, "07022222222", "親P2", "こどもP2")

    post = _create_post(client)
    post_id = post["id"]

    switch_to_parent(client)
    resp = client.post(f"/api/posts/{post_id}/delete")
    assert resp.status_code == 200, resp.text

    resp = client.get("/api/posts/timeline")
    assert post_id not in [p["id"] for p in resp.json()["posts"]]


def test_other_kid_cannot_delete_post_and_gets_404():
    """他人の投稿は削除できない。存在自体を明かさないため404を返す（403にはしない）"""
    client_author = new_client()
    create_family(client_author, "07033333333", "親P3", "こどもP3")
    post = _create_post(client_author)
    post_id = post["id"]

    client_other = new_client()
    create_family(client_other, "07044444444", "親P4", "こどもP4")

    # 他人の投稿には can_delete=False が見える（けすボタンが表示されない）
    resp = client_other.get("/api/posts/timeline")
    other_view_post = next(p for p in resp.json()["posts"] if p["id"] == post_id)
    assert other_view_post["can_delete"] is False

    # 削除しようとしても404（403ではない）
    resp = client_other.post(f"/api/posts/{post_id}/delete")
    assert resp.status_code == 404

    # 投稿はまだ存在し、タイムラインにも残っている（第三者には何も変化がない）
    resp = client_author.get("/api/posts/timeline")
    assert post_id in [p["id"] for p in resp.json()["posts"]]


def test_unrelated_parent_cannot_delete_post():
    """投稿者の保護者ではない別の保護者も削除できない（404で統一）"""
    client_author = new_client()
    create_family(client_author, "07055555555", "親P5", "こどもP5")
    post = _create_post(client_author)
    post_id = post["id"]

    client_other = new_client()
    create_family(client_other, "07066666666", "親P6", "こどもP6")
    switch_to_parent(client_other)

    resp = client_other.post(f"/api/posts/{post_id}/delete")
    assert resp.status_code == 404


def test_third_party_sees_no_notification_after_deletion():
    """第三者の視点では、削除された投稿は最初から存在しなかったかのように振る舞う
    （通知・理由メッセージが一切残らないことの確認）"""
    client_author = new_client()
    create_family(client_author, "07077777777", "親P7", "こどもP7")
    post = _create_post(client_author, mood_stamp="みてみて")
    post_id = post["id"]

    client_observer = new_client()
    create_family(client_observer, "07088888888", "親P8", "こどもP8")

    # 削除前は第三者にも見える
    resp = client_observer.get("/api/posts/timeline")
    assert post_id in [p["id"] for p in resp.json()["posts"]]

    client_author.post(f"/api/posts/{post_id}/delete")

    # 削除後、第三者のタイムラインからも静かに消え、レスポンスに理由等の
    # フィールドは一切含まれない
    resp = client_observer.get("/api/posts/timeline")
    assert resp.status_code == 200
    remaining_ids = [p["id"] for p in resp.json()["posts"]]
    assert post_id not in remaining_ids
    for p in resp.json()["posts"]:
        assert "deleted_reason" not in p
        assert "is_hidden" not in p
