"""
「おへや」（Room / RoomMember）の完全クローズド・アクセス制御の検証テスト

要件との対応:
- 自分が正式メンバーのおへやだけが一覧に出る（検索・一覧・おすすめはそもそも存在しない）
- 招待→本人応答→保護者承認 の3段階を経て初めて正式メンバーになる
- /api/rooms/{room_id} はメンバー以外には常に404（403で存在を明かすこともしない）
"""

from conftest import create_family, new_client, switch_to_kid, switch_to_parent



def test_create_room_and_owner_is_active_member():
    client = new_client()
    create_family(client, "08011111111", "親R1", "こどもR1")

    resp = client.post("/api/rooms/create", data={"name": "ひみつきち", "icon": "🏠"})
    assert resp.status_code == 200, resp.text
    room_id = resp.json()["room"]["id"]

    resp = client.get("/api/rooms/my-rooms")
    assert resp.status_code == 200
    room_ids = [r["id"] for r in resp.json()["rooms"]]
    assert room_id in room_ids

    # 作成者は正式メンバーなので詳細取得もできる
    resp = client.get(f"/api/rooms/{room_id}")
    assert resp.status_code == 200
    assert resp.json()["room"]["id"] == room_id


def test_non_member_gets_404_not_403():
    """メンバーでないユーザーには403ではなく404を返し、存在自体を明かさない"""
    client_owner = new_client()
    create_family(client_owner, "08022222222", "親R2", "こどもR2")
    resp = client_owner.post("/api/rooms/create", data={"name": "きみつのへや", "icon": "🔒"})
    room_id = resp.json()["room"]["id"]

    client_outsider = new_client()
    create_family(client_outsider, "08033333333", "親R3", "こどもR3")

    resp = client_outsider.get(f"/api/rooms/{room_id}")
    assert resp.status_code == 404

    # 一覧にも出てこない
    resp = client_outsider.get("/api/rooms/my-rooms")
    assert room_id not in [r["id"] for r in resp.json()["rooms"]]


def test_invitation_flow_requires_kid_and_parent_approval():
    client_owner = new_client()
    owner_family = create_family(client_owner, "08044444444", "親R4", "こどもR4")
    resp = client_owner.post("/api/rooms/create", data={"name": "なかよしのへや", "icon": "🌈"})
    room_id = resp.json()["room"]["id"]

    client_invitee = new_client()
    invitee_family = create_family(client_invitee, "08055555555", "親R5", "こどもR5")

    # 招待前は詳細にアクセスできない
    resp = client_invitee.get(f"/api/rooms/{room_id}")
    assert resp.status_code == 404

    # 招待する
    resp = client_owner.post(
        f"/api/rooms/{room_id}/invite",
        data={"receiver_kid_id": invitee_family["kid_id"]},
    )
    assert resp.status_code == 200, resp.text
    membership_id = resp.json()["membership"]["id"]
    assert resp.json()["membership"]["status"] == "invited"

    # 招待された側の一覧に出る
    resp = client_invitee.get("/api/rooms/invitations")
    assert resp.status_code == 200
    invitation_ids = [inv["membership_id"] for inv in resp.json()["invitations"]]
    assert membership_id in invitation_ids

    # まだ本人が応答していないので、正式メンバーではない → 詳細アクセス不可
    resp = client_invitee.get(f"/api/rooms/{room_id}")
    assert resp.status_code == 404

    # 本人が「さんかする」を選ぶ（まだ保護者承認待ち）
    resp = client_invitee.post(
        f"/api/rooms/invitations/{membership_id}/respond", data={"decision": "accept"}
    )
    assert resp.status_code == 200
    assert resp.json()["membership"]["status"] == "accepted"

    # 保護者承認前はまだメンバーではない
    resp = client_invitee.get(f"/api/rooms/{room_id}")
    assert resp.status_code == 404
    resp = client_invitee.get("/api/rooms/my-rooms")
    assert room_id not in [r["id"] for r in resp.json()["rooms"]]

    # 保護者の承認待ち一覧に出る
    switch_to_parent(client_invitee)
    resp = client_invitee.get("/api/rooms/parent/pending-approvals")
    assert resp.status_code == 200
    pending_ids = [a["membership_id"] for a in resp.json()["approvals"]]
    assert membership_id in pending_ids

    # 保護者が承認する
    resp = client_invitee.post(
        f"/api/rooms/invitations/{membership_id}/parent-approve",
        data={"decision": "approve"},
    )
    assert resp.status_code == 200
    assert resp.json()["membership"]["status"] == "active"

    # 承認後は正式メンバーとして「わたしのおへや」に表示され、詳細も取得できる
    # （保護者としての操作の後、キッズ本人のプロフィールに戻す）
    switch_to_kid(client_invitee, invitee_family["kid_id"])
    resp = client_invitee.get("/api/rooms/my-rooms")
    assert room_id in [r["id"] for r in resp.json()["rooms"]]

    resp = client_invitee.get(f"/api/rooms/{room_id}")

    assert resp.status_code == 200
    member_kid_ids = [m["kid_id"] for m in resp.json()["members"]]
    assert invitee_family["kid_id"] in member_kid_ids
    assert owner_family["kid_id"] in member_kid_ids


def test_kid_can_decline_invitation():
    client_owner = new_client()
    create_family(client_owner, "08066666666", "親R6", "こどもR6")
    resp = client_owner.post("/api/rooms/create", data={"name": "だれかのへや", "icon": "🎈"})
    room_id = resp.json()["room"]["id"]

    client_invitee = new_client()
    invitee_family = create_family(client_invitee, "08077777777", "親R7", "こどもR7")

    resp = client_owner.post(
        f"/api/rooms/{room_id}/invite", data={"receiver_kid_id": invitee_family["kid_id"]}
    )
    membership_id = resp.json()["membership"]["id"]

    resp = client_invitee.post(
        f"/api/rooms/invitations/{membership_id}/respond", data={"decision": "decline"}
    )
    assert resp.status_code == 200
    assert resp.json()["membership"]["status"] == "declined"

    switch_to_kid(client_invitee, invitee_family["kid_id"])
    resp = client_invitee.get(f"/api/rooms/{room_id}")
    assert resp.status_code == 404


def test_parent_can_reject_room_membership():

    client_owner = new_client()
    create_family(client_owner, "08088888888", "親R8", "こどもR8")
    resp = client_owner.post("/api/rooms/create", data={"name": "そのへや", "icon": "⭐"})
    room_id = resp.json()["room"]["id"]

    client_invitee = new_client()
    invitee_family = create_family(client_invitee, "08099999999", "親R9", "こどもR9")

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

    switch_to_kid(client_invitee, invitee_family["kid_id"])
    resp = client_invitee.get(f"/api/rooms/{room_id}")
    assert resp.status_code == 404


