"""
お茶の間（グループおしゃべり）サービス

「誰かとおしゃべりしたい」ボタンを押した利用者を待機列に入れ、
一定人数（デモでは3人）が集まったら「お茶の間」を開始する。

実際の複数ユーザー同時マッチングは将来的な拡張（WebSocket等）を想定しつつ、
現状はデモとして「あなた＋AIが用意する参加者」で成立させ、
・待機画面を閉じても（他ページに移動しても）状態が保持される
・必要人数が集まったらポップアップで参加確認ができる
・お茶の間の中ではAI司会が最初の話題を出し、会話が止まったら次の話題を提案する
・ワンタップの定型文、いつでも退出できる
という一連の体験をサーバー側の状態管理（インメモリ）で再現する。

本番運用で複数の実利用者を本当にマッチングさせたい場合は、
この waiting_queue / rooms をDBまたはRedis等に置き換え、
実際に集まった利用者同士でルームを組む処理に差し替えればよい。
"""

import random
import uuid
import datetime
from typing import Dict, List, Optional

# ------------------------------------------------------------------
# 設定
# ------------------------------------------------------------------
REQUIRED_PARTICIPANTS = 3  # お茶の間が開くのに必要な人数（あなたを含む）
FAKE_JOIN_SCHEDULE = [4, 9]  # 何秒後に「他の参加者」が集まったことにするか
SILENCE_SECONDS = 25  # このくらい会話が止まったらAIが次の話題を提案する
FAKE_REPLY_DELAY_RANGE = (3, 6)  # 参加者からの相づちが届くまでの秒数
FAKE_REPLY_PROBABILITY = 0.8

FAKE_PARTICIPANTS_POOL = [
    ("よしこさん", "👵"),
    ("たけしさん", "👴"),
    ("はるえさん", "👵"),
    ("まさおさん", "👴"),
    ("きみこさん", "👵"),
    ("しげるさん", "👴"),
]

CANNED_REPLIES = [
    "そうなんですね、いいですね！",
    "わかります🌸　私も同じです",
    "素敵なお話ですね！",
    "私もそう思います😊",
    "なるほど、面白いですね〜",
    "うんうん、よくわかります",
]

NEXT_TOPIC_PROMPTS = [
    "少し話題を変えてみましょうか。最近楽しかったことはありますか？",
    "皆さんの好きな食べ物について、ぜひ教えてください♪",
    "最近の天気の話でもいいですね。体調はいかがですか？",
    "昔の思い出話もぜひ聞かせてくださいね。",
    "お孫さんやペットのお話も大歓迎ですよ〜",
]

TOPIC_GREETINGS = {
    "雑談": "こんばんは！まずは簡単に挨拶してみませんか？今日はどんな一日でしたか？",
    "趣味": "こんばんは！今日は「趣味」のお話をしてみませんか？最近はまっていることはありますか？",
    "料理": "こんばんは！今日は「料理」のお話です。最近作った美味しいものはありますか？",
    "昔の思い出": "こんばんは！今日は「昔の思い出」を語り合いましょう。ふと思い出すことはありますか？",
}
DEFAULT_GREETING = "こんばんは！まずは簡単に挨拶してみませんか？"


# ------------------------------------------------------------------
# インメモリ状態
# ------------------------------------------------------------------
# waiting_queue: user_id -> {joined_at, style, topics, room_id, confirmed}
waiting_queue: Dict[int, dict] = {}

# rooms: room_id -> {id, topic, participants, messages, created_at,
#                     last_activity_at, topic_prompt_index,
#                     pending_fake_reply, owner_user_id}
rooms: Dict[str, dict] = {}


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _build_greeting(topic: Optional[str]) -> str:
    if topic and topic in TOPIC_GREETINGS:
        return TOPIC_GREETINGS[topic]
    return DEFAULT_GREETING


def _new_message(role: str, content: str, name: str = "", avatar: str = "") -> dict:
    return {
        "role": role,  # "ai" | "user" | "participant"
        "name": name,
        "avatar": avatar,
        "content": content,
        "created_at": _now().isoformat(),
    }


# ------------------------------------------------------------------
# 待機列
# ------------------------------------------------------------------
def join_waiting(user_id: int, display_name: str, style: str, topics: List[str]) -> dict:
    """「誰かとおしゃべりしたい」ボタンが押されたときに呼ぶ"""
    waiting_queue[user_id] = {
        "joined_at": _now(),
        "display_name": display_name or "あなた",
        "style": style,
        "topics": topics or [],
        "room_id": None,
        "confirmed": False,
    }
    return get_status(user_id)


def leave_ochanoma(user_id: int) -> None:
    """待機のキャンセル／マッチング見送り／お茶の間からの退出をすべてこれで行う"""
    entry = waiting_queue.pop(user_id, None)
    if entry and entry.get("room_id"):
        rooms.pop(entry["room_id"], None)


def _create_room(user_id: int, entry: dict, fake_count: int) -> dict:
    fake_choices = random.sample(
        FAKE_PARTICIPANTS_POOL, min(fake_count, len(FAKE_PARTICIPANTS_POOL))
    )
    participants = [
        {
            "id": "self",
            "name": entry["display_name"],
            "avatar": "🧓",
            "is_self": True,
        }
    ]
    for name, avatar in fake_choices:
        participants.append(
            {"id": f"fake-{uuid.uuid4().hex[:6]}", "name": name, "avatar": avatar, "is_self": False}
        )

    topic = entry["topics"][0] if entry["topics"] else "雑談"
    room_id = uuid.uuid4().hex[:12]
    now = _now()
    room = {
        "id": room_id,
        "topic": topic,
        "participants": participants,
        "messages": [_new_message("ai", _build_greeting(topic), name="AI司会", avatar="🤖")],
        "created_at": now,
        "last_activity_at": now,
        "topic_prompt_index": 0,
        "pending_fake_reply": None,
        "owner_user_id": user_id,
    }
    rooms[room_id] = room
    return room


def get_status(user_id: int) -> dict:
    """待機／マッチング状況を返す（ポーリング用）"""
    entry = waiting_queue.get(user_id)
    if entry is None:
        return {"status": "idle"}

    if entry.get("room_id"):
        return {
            "status": "matched",
            "room_id": entry["room_id"],
            "confirmed": entry.get("confirmed", False),
            "topic": rooms.get(entry["room_id"], {}).get("topic"),
        }

    elapsed = (_now() - entry["joined_at"]).total_seconds()
    fake_joined = sum(1 for t in FAKE_JOIN_SCHEDULE if elapsed >= t)
    current_count = 1 + fake_joined

    if current_count >= REQUIRED_PARTICIPANTS:
        room = _create_room(user_id, entry, REQUIRED_PARTICIPANTS - 1)
        entry["room_id"] = room["id"]
        return {
            "status": "matched",
            "room_id": room["id"],
            "confirmed": False,
            "topic": room["topic"],
        }

    return {
        "status": "waiting",
        "waiting_for": REQUIRED_PARTICIPANTS - current_count,
        "current_count": current_count,
        "required": REQUIRED_PARTICIPANTS,
    }


def confirm_room(user_id: int, room_id: str) -> Optional[dict]:
    entry = waiting_queue.get(user_id)
    if not entry or entry.get("room_id") != room_id:
        return None
    entry["confirmed"] = True
    return get_room_detail(user_id, room_id)


def get_room_detail(user_id: int, room_id: str) -> Optional[dict]:
    entry = waiting_queue.get(user_id)
    if not entry or entry.get("room_id") != room_id:
        return None
    room = rooms.get(room_id)
    if not room:
        return None
    return {
        "id": room["id"],
        "topic": room["topic"],
        "participants": room["participants"],
        "messages": room["messages"],
    }


# ------------------------------------------------------------------
# 会話中のロジック（AI司会・相づち）
# ------------------------------------------------------------------
def _maybe_inject_silence_prompt(room: dict) -> None:
    now = _now()
    elapsed = (now - room["last_activity_at"]).total_seconds()
    if elapsed < SILENCE_SECONDS:
        return
    idx = room["topic_prompt_index"] % len(NEXT_TOPIC_PROMPTS)
    prompt = NEXT_TOPIC_PROMPTS[idx]
    room["topic_prompt_index"] += 1
    room["messages"].append(_new_message("ai", prompt, name="AI司会", avatar="🤖"))
    room["last_activity_at"] = now


def _maybe_inject_fake_reply(room: dict) -> None:
    pending = room.get("pending_fake_reply")
    if not pending:
        return
    if _now() < pending["at"]:
        return
    room["messages"].append(
        _new_message(
            "participant",
            pending["text"],
            name=pending["participant"]["name"],
            avatar=pending["participant"]["avatar"],
        )
    )
    room["last_activity_at"] = _now()
    room["pending_fake_reply"] = None


def get_messages(user_id: int, room_id: str) -> Optional[List[dict]]:
    entry = waiting_queue.get(user_id)
    if not entry or entry.get("room_id") != room_id:
        return None
    room = rooms.get(room_id)
    if not room:
        return None

    _maybe_inject_fake_reply(room)
    _maybe_inject_silence_prompt(room)
    return room["messages"]


def post_message(user_id: int, room_id: str, text: str) -> Optional[List[dict]]:
    entry = waiting_queue.get(user_id)
    if not entry or entry.get("room_id") != room_id:
        return None
    room = rooms.get(room_id)
    if not room:
        return None

    room["messages"].append(_new_message("user", text, name=entry["display_name"], avatar="🧓"))
    room["last_activity_at"] = _now()

    fake_participants = [p for p in room["participants"] if not p["is_self"]]
    if fake_participants and random.random() < FAKE_REPLY_PROBABILITY:
        participant = random.choice(fake_participants)
        delay = random.randint(*FAKE_REPLY_DELAY_RANGE)
        room["pending_fake_reply"] = {
            "at": _now() + datetime.timedelta(seconds=delay),
            "text": random.choice(CANNED_REPLIES),
            "participant": participant,
        }

    return room["messages"]
