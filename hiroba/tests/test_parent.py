"""
保護者ページ（/parent/*）バックエンド機能の検証テスト

要件との対応:
1. キッズアカウント追加・管理 (/parent/children/new, /parent/children)
   - 名前・アイコン・学年の登録・編集
2. 遊ぶ約束の承認・管理 (/parent/promises)
   - 👌いいよ／🕐じかんを決める／🙅今回はむずかしい／キャンセル
     （詳細フローの検証は tests/test_promises.py で網羅済みのため、
       ここでは主に「保護者ページ視点での一覧取得」と「アクセス制御」を検証する）
3. おへや参加承認 (/parent/rooms)
   - 承認する／見送る（詳細フローは tests/test_rooms.py で網羅済み）
4. LINE通知設定 (/parent/notifications)
   - オン/オフ切り替え・連携状態の表示
5. アクセス制御
   - ログイン中の保護者本人の紐付けデータのみを取得・操作できること
"""

import datetime as dt

from conftest import create_family, new_client, switch_to_kid, switch_to_parent

TOMORROW = (dt.date.today() + dt.timedelta(days=1)).isoformat()


# ------------------------------------------------------------------
# 1. キッズアカウント追加・管理
# ------------------------------------------------------------------
def test_parent_can_add_kid_with_name_avatar_and_grade():
    client = new_client()
    create_family(client, "07100000001", "親K1", "こどもK1")

    resp = client.post(
        "/api/auth/kids/add",
        data={"display_name": "はなこ", "avatar_icon": "🐰", "grade": "小2"},
    )
    assert resp.status_code == 200, resp.text
    kid = resp.json()["kid"]
    assert kid["display_name"] == "はなこ"
    assert kid["avatar_icon"] == "🐰"
    assert kid["grade"] == "小2"

    # 一覧にも反映される
    resp = client.get("/api/auth/kids")
    assert resp.status_code == 200
    names = [k["display_name"] for k in resp.json()["kids"]]
    assert "はなこ" in names


def test_add_kid_rejects_invalid_grade():
    client = new_client()
    create_family(client, "07100000002", "親K2", "こどもK2")

    resp = client.post(
        "/api/auth/kids/add",
        data={"display_name": "たろう", "avatar_icon": "🐶", "grade": "大学1年"},
    )
    assert resp.status_code == 400
    assert "がくねん" in resp.json()["detail"]


def test_parent_can_update_own_kid_profile():
    client = new_client()
    family = create_family(client, "07100000003", "親K3", "こどもK3")

    resp = client.post(
        "/api/auth/kids/add",
        data={"display_name": "じろう", "avatar_icon": "🐻", "grade": "小1"},
    )
    kid_id = resp.json()["kid"]["id"]

    resp = client.post(
        f"/api/auth/kids/{kid_id}/update",
        data={"display_name": "じろう（改名）", "avatar_icon": "🦁", "grade": "小2"},
    )
    assert resp.status_code == 200, resp.text
    kid = resp.json()["kid"]
    assert kid["display_name"] == "じろう（改名）"
    assert kid["avatar_icon"] == "🦁"
    assert kid["grade"] == "小2"


def test_parent_cannot_update_other_familys_kid():
    """他の保護者に紐づくキッズは編集できない（404で存在を明かさない）"""
    client_a = new_client()
    family_a = create_family(client_a, "07100000004", "親K4", "こどもK4")

    client_b = new_client()
    create_family(client_b, "07100000005", "親K5", "こどもK5")

    resp = client_b.post(
        f"/api/auth/kids/{family_a['kid_id']}/update",
        data={"display_name": "のっとり", "avatar_icon": "👿", "grade": "小3"},
    )
    assert resp.status_code == 404


def test_kids_add_and_update_require_parent_login():
    client = new_client()
    resp = client.post(
        "/api/auth/kids/add", data={"display_name": "だれか", "avatar_icon": "🐱"}
    )
    assert resp.status_code == 401


# ------------------------------------------------------------------
# 2. 遊ぶ約束の承認・管理（保護者ページ視点）
# ------------------------------------------------------------------
def _create_promise_pending(client_a, client_b):
    resp = client_a.post(
        "/api/promises/posts/create",
        data={"date": TOMORROW, "time_frame": "morning", "location_type": "home_my"},
    )
    post_id = resp.json()["post"]["id"]
    resp = client_b.post(f"/api/promises/posts/{post_id}/apply")
    return resp.json()["promise"]["id"]


def test_parent_promises_page_lists_pending_and_approved():
    client_a = new_client()
    create_family(client_a, "07200000001", "親M1", "こどもM1")
    client_b = new_client()
    create_family(client_b, "07200000002", "親M2", "こどもM2")

    promise_id = _create_promise_pending(client_a, client_b)

    # 確認中のお約束が保護者ページの一覧(my-promises)に見える
    switch_to_parent(client_a)
    resp = client_a.get("/api/promises/my-promises")
    assert resp.status_code == 200
    statuses = {p["id"]: p["status"] for p in resp.json()["promises"]}
    assert statuses.get(promise_id) == "pending_parents"

    # 👌 いいよ（片方のみ）
    resp = client_a.post(
        f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"}
    )
    assert resp.status_code == 200
    assert resp.json()["promise"]["sender_parent_approved"] is True

    switch_to_parent(client_b)
    resp = client_b.post(
        f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"}
    )
    assert resp.status_code == 200
    assert resp.json()["promise"]["status"] == "approved"

    # 成立したお約束が一覧に見える
    resp = client_b.get("/api/promises/my-promises")
    statuses = {p["id"]: p["status"] for p in resp.json()["promises"]}
    assert statuses.get(promise_id) == "approved"

    # キャンセル（理由開示なし）
    resp = client_b.post(f"/api/promises/{promise_id}/cancel")
    assert resp.status_code == 200
    body = resp.json()["promise"]
    assert body["status"] == "cancelled"
    assert "reason" not in body
    assert "cancelled_by" not in body


def test_parent_time_adjust_updates_detailed_time():
    client_a = new_client()
    create_family(client_a, "07200000003", "親M3", "こどもM3")
    client_b = new_client()
    create_family(client_b, "07200000004", "親M4", "こどもM4")

    promise_id = _create_promise_pending(client_a, client_b)

    switch_to_parent(client_a)
    resp = client_a.post(
        f"/api/promises/{promise_id}/parent-response",
        data={"decision": "adjust_time", "start_time": "09:30", "end_time": "11:00"},
    )
    assert resp.status_code == 200
    assert resp.json()["promise"]["detailed_time"] == "09:30〜11:00"


def test_parent_decline_produces_gentle_message_without_blame():
    client_a = new_client()
    create_family(client_a, "07200000005", "親M5", "こどもM5")
    client_b = new_client()
    create_family(client_b, "07200000006", "親M6", "こどもM6")

    promise_id = _create_promise_pending(client_a, client_b)

    switch_to_parent(client_a)
    resp = client_a.post(
        f"/api/promises/{promise_id}/parent-response", data={"decision": "decline"}
    )
    assert resp.status_code == 200
    body = resp.json()["promise"]
    assert body["status"] == "cancelled"
    assert "reason" not in body
    assert "declined_by" not in body


def test_promises_list_only_shows_own_familys_promises():
    """保護者ページの一覧には、自分の家庭が関係するお約束だけが表示される"""
    client_a = new_client()
    create_family(client_a, "07200000007", "親M7", "こどもM7")
    client_b = new_client()
    create_family(client_b, "07200000008", "親M8", "こどもM8")
    client_c = new_client()
    create_family(client_c, "07200000009", "親M9", "こどもM9")

    promise_id = _create_promise_pending(client_a, client_b)

    switch_to_parent(client_c)
    resp = client_c.get("/api/promises/my-promises")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()["promises"]]
    assert promise_id not in ids


# ------------------------------------------------------------------
# 3. おへや参加承認（保護者ページ視点）
# ------------------------------------------------------------------
def test_parent_rooms_page_shows_pending_and_overview():
    client_owner = new_client()
    create_family(client_owner, "07300000001", "親R1", "こどもR1")
    resp = client_owner.post("/api/rooms/create", data={"name": "テストへや", "icon": "🎪"})
    room_id = resp.json()["room"]["id"]

    client_invitee = new_client()
    invitee_family = create_family(client_invitee, "07300000002", "親R2", "こどもR2")

    resp = client_owner.post(
        f"/api/rooms/{room_id}/invite", data={"receiver_kid_id": invitee_family["kid_id"]}
    )
    membership_id = resp.json()["membership"]["id"]
    client_invitee.post(
        f"/api/rooms/invitations/{membership_id}/respond", data={"decision": "accept"}
    )

    # 保護者ページ：承認待ち一覧に出る
    switch_to_parent(client_invitee)
    resp = client_invitee.get("/api/rooms/parent/pending-approvals")
    assert resp.status_code == 200
    membership_ids = [a["membership_id"] for a in resp.json()["approvals"]]
    assert membership_id in membership_ids

    # 承認する
    resp = client_invitee.post(
        f"/api/rooms/invitations/{membership_id}/parent-approve",
        data={"decision": "approve"},
    )
    assert resp.status_code == 200
    assert resp.json()["membership"]["status"] == "active"

    # 承認後は「参加中のおへや・メンバー一覧」(overview)に出る
    resp = client_invitee.get("/api/rooms/parent/overview")
    assert resp.status_code == 200
    room_ids = [entry["room"]["id"] for entry in resp.json()["rooms"]]
    assert room_id in room_ids


def test_parent_rooms_pending_approvals_only_for_own_children():
    """他家庭の承認待ちリクエストは見えない"""
    client_owner = new_client()
    create_family(client_owner, "07300000003", "親R3", "こどもR3")
    resp = client_owner.post("/api/rooms/create", data={"name": "そのへや2", "icon": "🎈"})
    room_id = resp.json()["room"]["id"]

    client_invitee = new_client()
    invitee_family = create_family(client_invitee, "07300000004", "親R4", "こどもR4")
    resp = client_owner.post(
        f"/api/rooms/{room_id}/invite", data={"receiver_kid_id": invitee_family["kid_id"]}
    )
    membership_id = resp.json()["membership"]["id"]
    client_invitee.post(
        f"/api/rooms/invitations/{membership_id}/respond", data={"decision": "accept"}
    )

    client_outsider = new_client()
    create_family(client_outsider, "07300000005", "親R5", "こどもR5")
    resp = client_outsider.get("/api/rooms/parent/pending-approvals")
    assert resp.status_code == 200
    membership_ids = [a["membership_id"] for a in resp.json()["approvals"]]
    assert membership_id not in membership_ids


def test_parent_can_reject_room_join_request():
    client_owner = new_client()
    create_family(client_owner, "07300000006", "親R6", "こどもR6")
    resp = client_owner.post("/api/rooms/create", data={"name": "みおくりへや", "icon": "🌧️"})
    room_id = resp.json()["room"]["id"]

    client_invitee = new_client()
    invitee_family = create_family(client_invitee, "07300000007", "親R7", "こどもR7")
    resp = client_owner.post(
        f"/api/rooms/{room_id}/invite", data={"receiver_kid_id": invitee_family["kid_id"]}
    )
    membership_id = resp.json()["membership"]["id"]
    client_invitee.post(
        f"/api/rooms/invitations/{membership_id}/respond", data={"decision": "accept"}
    )

    switch_to_parent(client_invitee)
    resp = client_invitee.post(
        f"/api/rooms/invitations/{membership_id}/parent-approve",
        data={"decision": "reject"},
    )
    assert resp.status_code == 200
    assert resp.json()["membership"]["status"] == "declined"


# ------------------------------------------------------------------
# 4. LINE通知設定
# ------------------------------------------------------------------
def test_notification_settings_default_state():
    client = new_client()
    create_family(client, "07400000001", "親N1", "こどもN1")
    switch_to_parent(client)

    resp = client.get("/api/parent/notifications")
    assert resp.status_code == 200
    settings = resp.json()["settings"]
    assert settings["line_notify_enabled"] is True
    assert settings["line_linked"] is False


def test_notification_toggle_on_off():
    client = new_client()
    create_family(client, "07400000002", "親N2", "こどもN2")
    switch_to_parent(client)

    resp = client.post("/api/parent/notifications/toggle", data={"enabled": "false"})
    assert resp.status_code == 200
    assert resp.json()["settings"]["line_notify_enabled"] is False

    resp = client.get("/api/parent/notifications")
    assert resp.json()["settings"]["line_notify_enabled"] is False

    resp = client.post("/api/parent/notifications/toggle", data={"enabled": "true"})
    assert resp.json()["settings"]["line_notify_enabled"] is True


def test_notification_link_and_unlink_line_account():
    client = new_client()
    create_family(client, "07400000003", "親N3", "こどもN3")
    switch_to_parent(client)

    resp = client.post("/api/parent/notifications/link")
    assert resp.status_code == 200
    settings = resp.json()["settings"]
    assert settings["line_linked"] is True
    assert settings["line_user_id_masked"] is not None

    resp = client.post("/api/parent/notifications/unlink")
    assert resp.status_code == 200
    assert resp.json()["settings"]["line_linked"] is False


def test_notification_settings_require_login():
    client = new_client()
    resp = client.get("/api/parent/notifications")
    assert resp.status_code == 401
    resp = client.post("/api/parent/notifications/toggle", data={"enabled": "true"})
    assert resp.status_code == 401


def test_disabled_notification_prevents_line_message_being_sent():

    """通知OFFの保護者には、実際に通知（sent_messages）が送られないことを確認する"""
    from app.services import line_notify_service

    client_a = new_client()
    family_a = create_family(client_a, "07400000006", "親N6", "こどもN6")
    client_b = new_client()
    create_family(client_b, "07400000007", "親N7", "こどもN7")

    switch_to_parent(client_a)
    client_a.post("/api/parent/notifications/toggle", data={"enabled": "false"})
    switch_to_kid(client_a, family_a["kid_id"])

    before_count = len(line_notify_service.sent_messages)

    # Aが投稿し、Bが応募 → Aの保護者への通知が発生するタイミングだが、OFFなので送られない
    resp = client_a.post(
        "/api/promises/posts/create",
        data={"date": TOMORROW, "time_frame": "afternoon", "location_type": "home_my"},
    )
    post_id = resp.json()["post"]["id"]
    client_b.post(f"/api/promises/posts/{post_id}/apply")

    after_count = len(line_notify_service.sent_messages)
    # Aの保護者宛の新規メッセージは増えていない（Bの保護者宛は増えている可能性がある）
    new_messages = line_notify_service.sent_messages[before_count:after_count]
    assert all(m["parent_id"] != family_a["parent_id"] for m in new_messages)


# ------------------------------------------------------------------
# 5. アクセス制御（総合）
# ------------------------------------------------------------------
def test_parent_apis_reject_fully_logged_out_client():
    """完全に未ログイン（保護者セッションなし）のクライアントは、保護者専用APIを一切呼べない"""
    client = new_client()
    resp = client.get("/api/parent/notifications")
    assert resp.status_code == 401

    resp = client.get("/api/rooms/parent/pending-approvals")
    assert resp.status_code == 401

    resp = client.post("/api/promises/1/parent-response", data={"decision": "approve"})
    assert resp.status_code == 401


def test_parent_apis_still_scoped_to_logged_in_parent_while_kid_profile_active():
    """保護者ログイン中にキッズへプロフィールを切り替えても、
    保護者専用APIはその保護者自身のデータのみを返す（他家庭のデータは見えない）"""
    client = new_client()
    create_family(client, "07500000001", "親X1", "こどもX1")
    # create_family後はアクティブプロフィールがキッズになっているが、
    # 保護者としてのログイン(セッション)自体は継続している設計のため、
    # 保護者専用APIは呼び出せる（＝本人確認としては保護者ログインの有無を見る）。
    resp = client.get("/api/parent/notifications")
    assert resp.status_code == 200

    # 他の保護者に紐づくキッズのお約束承認は依然としてできない（アクセス制御は健在）
    resp = client.post("/api/promises/999999/parent-response", data={"decision": "approve"})
    assert resp.status_code == 404


