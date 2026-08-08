"""
「あそぶ お約束」フロー（PromisePost / Promise）の検証テスト

要件との対応:
- タップ選択式の投稿（日付・時間帯・場所）
- 1日1件ルール・確認中の重複防止
- 第三者に人間関係を見せない匿名性（掲示板・my-promisesの絞り込み）
- 双方の保護者承認フロー（いいよ／じかんを決める／今回はむずかしい）
- 成立時の投稿の静かな非表示化、キャンセル機能
"""

import datetime as dt

from conftest import create_family, new_client, switch_to_kid, switch_to_parent

TOMORROW = (dt.date.today() + dt.timedelta(days=1)).isoformat()
DAY_AFTER = (dt.date.today() + dt.timedelta(days=2)).isoformat()
YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def _create_post(client, date_=TOMORROW, time_frame="morning", location_type="home_my"):
    return client.post(
        "/api/promises/posts/create",
        data={"date": date_, "time_frame": time_frame, "location_type": location_type},
    )


def test_create_post_rejects_past_date():
    client = new_client()
    create_family(client, "09000000001", "親A", "こどもA")

    resp = _create_post(client, date_=YESTERDAY)
    assert resp.status_code == 400
    assert "まえ" in resp.json()["detail"]


def test_create_post_other_location_requires_audio():
    client = new_client()
    create_family(client, "09000000002", "親B", "こどもB")

    resp = _create_post(client, location_type="other")
    assert resp.status_code == 400
    assert "ボイスメモ" in resp.json()["detail"]


def test_full_approval_flow_matches_and_hides_from_board():
    """A投稿→B応募→両親承認→成立。第三者Cには何も見えないことを確認する"""
    client_a = new_client()
    family_a = create_family(client_a, "09011111111", "親A", "こどもA")

    client_b = new_client()
    family_b = create_family(client_b, "09022222222", "親B", "こどもB")

    client_c = new_client()
    create_family(client_c, "09033333333", "親C", "こどもC")

    # A が投稿
    resp = _create_post(client_a, date_=TOMORROW, time_frame="morning", location_type="home_my")
    assert resp.status_code == 200, resp.text
    post_id = resp.json()["post"]["id"]

    # C の掲示板には A の投稿が見える（まだ成立していないので当然表示される）
    resp = client_c.get("/api/promises/board")
    assert resp.status_code == 200
    board_ids = [p["id"] for p in resp.json()["posts"]]
    assert post_id in board_ids
    # 応募人数・応募者一覧などのフィールドが一切含まれないことを確認
    posted = [p for p in resp.json()["posts"] if p["id"] == post_id][0]
    forbidden_keys = {"applicants", "applicant_count", "likes", "like_count", "apply_count"}
    assert forbidden_keys.isdisjoint(posted.keys())

    # B が応募
    resp = client_b.post(f"/api/promises/posts/{post_id}/apply")
    assert resp.status_code == 200, resp.text
    promise_id = resp.json()["promise"]["promise_id"] if "promise_id" in resp.json().get("promise", {}) else resp.json()["promise"]["id"]
    assert resp.json()["promise"]["status"] == "pending_parents"

    # 成立していないので、Cの掲示板からはまだ消えていない想定だが、
    # Bが応募済みのためBの掲示板には出ない
    resp = client_b.get("/api/promises/board")
    assert post_id not in [p["id"] for p in resp.json()["posts"]]

    # 第三者Cには「確認中」等の情報は一切見えない（my-promisesは当事者のみ）
    resp = client_c.get("/api/promises/my-promises")
    assert resp.json()["promises"] == []

    # A側の保護者が「いいよ」
    switch_to_parent(client_a)
    resp = client_a.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["promise"]["status"] == "pending_parents"  # まだ片方だけ

    # B側の保護者が「いいよ」→ 成立
    switch_to_parent(client_b)
    resp = client_b.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["promise"]["status"] == "approved"

    # 成立後、投稿は掲示板から静かに消える（第三者Cから見て「消えた」ように見える）
    resp = client_c.get("/api/promises/board")
    assert post_id not in [p["id"] for p in resp.json()["posts"]]

    # 当事者（A・B）には成立した約束が見える
    switch_to_kid(client_a, family_a["kid_id"])
    resp = client_a.get("/api/promises/my-promises")
    statuses = [p["status"] for p in resp.json()["promises"]]
    assert "approved" in statuses

    switch_to_kid(client_b, family_b["kid_id"])
    resp = client_b.get("/api/promises/my-promises")
    statuses = [p["status"] for p in resp.json()["promises"]]
    assert "approved" in statuses

    # 第三者Cには相変わらず何も見えない
    resp = client_c.get("/api/promises/my-promises")
    assert resp.json()["promises"] == []


def test_one_promise_per_day_rule():
    """成立済みの約束がある日は、新たな投稿・応募ができない"""
    client_a = new_client()
    family_a = create_family(client_a, "09044444444", "親A2", "こどもA2")

    client_b = new_client()
    create_family(client_b, "09055555555", "親B2", "こどもB2")

    resp = _create_post(client_a, date_=TOMORROW)
    post_id = resp.json()["post"]["id"]

    resp = client_b.post(f"/api/promises/posts/{post_id}/apply")
    promise_id = resp.json()["promise"]["id"]

    switch_to_parent(client_a)
    client_a.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"})
    switch_to_parent(client_b)
    resp = client_b.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"})
    assert resp.json()["promise"]["status"] == "approved"

    # 成立済みなので、Aが同じ日にもう一件投稿しようとすると拒否される
    # （保護者による承認操作の後はアクティブプロフィールが保護者になっているため、
    #   キッズに切り替え直す）
    switch_to_kid(client_a, family_a["kid_id"])
    resp = _create_post(client_a, date_=TOMORROW)

    assert resp.status_code == 400
    assert "もうやくそくがあるよ" in resp.json()["detail"]




def test_pending_engagement_blocks_new_post():
    """確認中の約束がある間は、新たな投稿・応募ができない"""
    client_a = new_client()
    create_family(client_a, "09066666666", "親A3", "こどもA3")

    client_b = new_client()
    create_family(client_b, "09077777777", "親B3", "こどもB3")

    resp = _create_post(client_a, date_=TOMORROW)
    assert resp.status_code == 200
    post_id = resp.json()["post"]["id"]

    resp = client_b.post(f"/api/promises/posts/{post_id}/apply")
    assert resp.status_code == 200

    # Bはまだ確認中の約束があるので、別の日の投稿はできない
    resp = _create_post(client_b, date_=DAY_AFTER)
    assert resp.status_code == 400
    assert "かくにんしている" in resp.json()["detail"]

    # Aも自分の投稿が確認中(open)の応募待ち状態のため、別投稿はできない
    resp = _create_post(client_a, date_=DAY_AFTER)
    assert resp.status_code == 400


def test_decline_flow_shows_gentle_message_and_no_blame():
    """「今回はむずかしい」を選ぶと、非責めメッセージのみが伝わる"""
    client_a = new_client()
    create_family(client_a, "09088888888", "親A4", "こどもA4")

    client_b = new_client()
    create_family(client_b, "09099999999", "親B4", "こどもB4")

    resp = _create_post(client_a, date_=TOMORROW)
    post_id = resp.json()["post"]["id"]
    resp = client_b.post(f"/api/promises/posts/{post_id}/apply")
    promise_id = resp.json()["promise"]["id"]

    switch_to_parent(client_a)
    resp = client_a.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "decline"})
    assert resp.status_code == 200
    assert resp.json()["promise"]["status"] == "cancelled"

    # 断った理由や、どちらが断ったかはレスポンスに含まれない
    body = resp.json()["promise"]
    assert "declined_by" not in body
    assert "reason" not in body


def test_adjust_time_requires_both_reapproval():
    """「じかんを決める」提案後は、双方の再承認が必要になる"""
    client_a = new_client()
    create_family(client_a, "09010101010", "親A5", "こどもA5")

    client_b = new_client()
    create_family(client_b, "09020202020", "親B5", "こどもB5")

    resp = _create_post(client_a, date_=TOMORROW)
    post_id = resp.json()["post"]["id"]
    resp = client_b.post(f"/api/promises/posts/{post_id}/apply")
    promise_id = resp.json()["promise"]["id"]

    switch_to_parent(client_a)
    resp = client_a.post(
        f"/api/promises/{promise_id}/parent-response",
        data={"decision": "adjust_time", "start_time": "14:00", "end_time": "16:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["promise"]["detailed_time"] == "14:00〜16:00"
    assert resp.json()["promise"]["status"] == "pending_parents"

    switch_to_parent(client_b)
    resp = client_b.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"})
    assert resp.status_code == 200
    assert resp.json()["promise"]["status"] == "approved"
    assert resp.json()["promise"]["detailed_time"] == "14:00〜16:00"


def test_cancel_after_approval():
    """成立後も保護者はキャンセルでき、投稿は再度掲示板に戻る"""
    client_a = new_client()
    create_family(client_a, "09030303030", "親A6", "こどもA6")

    client_b = new_client()
    create_family(client_b, "09040404040", "親B6", "こどもB6")

    resp = _create_post(client_a, date_=TOMORROW)
    post_id = resp.json()["post"]["id"]
    resp = client_b.post(f"/api/promises/posts/{post_id}/apply")
    promise_id = resp.json()["promise"]["id"]

    switch_to_parent(client_a)
    client_a.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"})
    switch_to_parent(client_b)
    resp = client_b.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"})
    assert resp.json()["promise"]["status"] == "approved"

    resp = client_b.post(f"/api/promises/{promise_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["promise"]["status"] == "cancelled"


def test_unauthorized_parent_cannot_respond_to_others_promise():
    client_a = new_client()
    create_family(client_a, "09050505050", "親A7", "こどもA7")

    client_b = new_client()
    create_family(client_b, "09060606060", "親B7", "こどもB7")

    client_c = new_client()
    create_family(client_c, "09070707070", "親C7", "こどもC7")

    resp = _create_post(client_a, date_=TOMORROW)
    post_id = resp.json()["post"]["id"]
    resp = client_b.post(f"/api/promises/posts/{post_id}/apply")
    promise_id = resp.json()["promise"]["id"]

    switch_to_parent(client_c)
    resp = client_c.post(f"/api/promises/{promise_id}/parent-response", data={"decision": "approve"})
    assert resp.status_code == 403
