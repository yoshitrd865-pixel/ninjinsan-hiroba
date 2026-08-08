"""
ボイスメモの音声認識サービス（ひろば）

キッズが録音したボイスメモを OpenAI Whisper API でテキスト化する。
キッズ自身は文字を読み書きしないため、この文字化テキストは
保護者確認・検索・モデレーション用途にのみ使う想定（Post.whisper_text）。

環境変数 OPENAI_API_KEY が設定されていない場合は音声認識を行わず、
常に None を返す（開発環境でAPIキーなしでも投稿自体は可能にする）。
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("hiroba.whisper")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
WHISPER_ENABLED = bool(OPENAI_API_KEY)


def transcribe_audio(file_path: Path) -> str | None:
    """音声ファイルをテキスト化する。失敗時・未設定時は None を返す。"""
    if not WHISPER_ENABLED:
        return None

    try:
        from openai import OpenAI  # 遅延インポート（未使用時は依存しない）

        client = OpenAI(api_key=OPENAI_API_KEY)
        with open(file_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return getattr(result, "text", None)
    except Exception:
        logger.exception("Whisperによる音声認識に失敗しました: %s", file_path)
        return None
