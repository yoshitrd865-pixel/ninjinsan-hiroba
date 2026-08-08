"""
AIおしゃべり機能サービス

環境変数 OPENAI_API_KEY が設定されている場合、OpenAI Chat Completions API
を使って実際にAIと会話できる。設定されていない場合は、その旨を伝える
固定メッセージを返す（アプリ自体は問題なく動作する）。

将来的な音声認識AI（Speech-to-Text）機能を組み込む際は、
この service 層に transcribe_audio() 等の関数を追加すればよい。
"""

import os
import logging
from typing import List, Dict

logger = logging.getLogger("engawa.ai")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
AI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

AI_ENABLED = bool(OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "あなたは「縁側」というシニア向けSNSアプリの中で、"
    "60歳以上の利用者とおしゃべりする優しいAIアシスタントです。"
    "ゆっくり、わかりやすい言葉で、あたたかく短めに応答してください。"
    "難しい専門用語は使わず、相手の話に共感しながら会話してください。"
)

_client = None
if AI_ENABLED:
    try:
        from openai import OpenAI

        _client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        logger.exception("OpenAIクライアントの初期化に失敗しました。")
        _client = None


def generate_reply(history: List[Dict[str, str]]) -> str:
    """
    会話履歴（[{"role": "user"/"assistant", "content": "..."}]）を受け取り、
    AIの返答テキストを返す。

    OpenAI APIキーが設定されていない場合は、案内メッセージを返す。
    """
    if not AI_ENABLED or _client is None:
        return (
            "（AI機能は現在準備中です。管理者が OPENAI_API_KEY を設定すると、"
            "この画面で実際にAIとおしゃべりできるようになります。）"
        )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    try:
        response = _client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("OpenAI API呼び出しに失敗しました。")
        return "申し訳ありません、少し電波の調子が悪いようです。もう一度お話しかけてください。"
