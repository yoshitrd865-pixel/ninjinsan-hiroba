"""
AIによる「遊ぶ約束」抽出サービス（ひろば）

キッズ同士の会話ログ（クイックフレーズの組み合わせ）やボイスメモの
文字化テキストから、OpenAI GPT を使って「約束の意図」「日時」
「場所/内容」をJSONデータとして抽出する。

AIお兄さん・お姉さんが会話を整理して保護者に伝える、という
体験を実現するためのロジック。

環境変数 OPENAI_API_KEY が設定されていない場合、または
API呼び出しに失敗した場合は、簡易的なフォールバック抽出を行う
（開発環境でAPIキーなしでも約束機能自体は使えるようにする）。
"""

import datetime
import json
import logging
import os
import re

logger = logging.getLogger("hiroba.promise_ai")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
AI_ENABLED = bool(OPENAI_API_KEY)

# フォールバック抽出時に使う簡単なキーワード -> 場所/内容の対応表
_PLACE_KEYWORDS = {
    "こうえん": "こうえん",
    "公園": "公園",
    "うち": "おうち",
    "いえ": "おうち",
    "がっこう": "がっこう",
    "学校": "学校",
    "げーむ": "ゲーム",
    "ゲーム": "ゲーム",
    "ぷーる": "プール",
    "プール": "プール",
}


def extract_promise_details(raw_text: str) -> dict:
    """会話ログ・ボイスメモのテキストから約束の内容を抽出する

    戻り値: {"title": str, "suggested_datetime": Optional[str], "place": Optional[str]}
    - suggested_datetime は "YYYY-MM-DD HH:MM" 形式の文字列、不明な場合は None
    """
    text = (raw_text or "").strip()
    if not text:
        return {
            "title": "あそぶ やくそく",
            "suggested_datetime": None,
            "place": None,
        }

    if AI_ENABLED:
        try:
            return _extract_with_openai(text)
        except Exception:
            logger.exception("AIによる約束抽出に失敗したため、簡易抽出にフォールバックします")

    return _fallback_extract(text)


def _extract_with_openai(text: str) -> dict:
    """OpenAI GPT (Chat Completions, JSONモード) を使って約束の内容を抽出する"""
    from openai import OpenAI  # 遅延インポート（未使用時は依存しない）

    client = OpenAI(api_key=OPENAI_API_KEY)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M（%A）")

    system_prompt = (
        "あなたは『ひろば』というキッズ向けSNSで、子ども同士の"
        "『遊ぶ約束』の会話を整理するAIお兄さん・お姉さんです。\n"
        f"現在の日時は {now_str} です。\n"
        "与えられた会話やボイスメモの文字化テキストから、約束の内容を"
        "次のJSON形式だけで出力してください（説明文やコードブロックは不要です）。\n"
        "{\n"
        '  "title": "約束の短い要約（例:「公園で遊ぼう」）。20文字以内。",\n'
        '  "suggested_datetime": "YYYY-MM-DD HH:MM 形式の提案日時。わからない場合は null。",\n'
        '  "place": "場所や内容の詳細（例:「近くの公園」「オンラインゲーム」）。わからない場合は null。"\n'
        "}"
    )


    response = client.chat.completions.create(
        model=os.environ.get("HIROBA_PROMISE_AI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    content = response.choices[0].message.content
    data = json.loads(content)

    title = (data.get("title") or "").strip() or text[:20]
    suggested_datetime = data.get("suggested_datetime") or None
    place = data.get("place") or None

    # AIが返したdatetime文字列の形式が想定と違う場合に備えて簡易検証する
    if suggested_datetime and not re.match(
        r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2})?$", str(suggested_datetime)
    ):
        suggested_datetime = None

    return {
        "title": title[:200],
        "suggested_datetime": suggested_datetime,
        "place": (place or None) and str(place)[:200],
    }


def _fallback_extract(text: str) -> dict:
    """OPENAI_API_KEY未設定時・AI呼び出し失敗時の簡易抽出

    キーワードマッチによる簡易的な場所推定と、テキストの先頭部分を
    タイトルとして使う。日時は解析せず None を返す（保護者側で
    チャット内容を確認して調整してもらう想定）。
    """
    place = None
    for keyword, label in _PLACE_KEYWORDS.items():
        if keyword in text:
            place = label
            break

    title = text[:20] if text else "あそぶ やくそく"

    return {
        "title": title,
        "suggested_datetime": None,
        "place": place,
    }
