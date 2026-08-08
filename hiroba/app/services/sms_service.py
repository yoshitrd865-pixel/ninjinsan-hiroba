"""
SMS送信サービス（ひろば・開発用ダミー実装）

保護者ログインの認証コードを送信するためのサービス。
本番のSMSプロバイダとは未連携で、開発モードでは実際に送信せず、
生成したコードをプロセス内メモリに一時保存し、呼び出し元
（app/routers/auth.py）でレスポンスにそのまま含めて画面表示する。

本番運用時にTwilio等と連携する場合は、send_verification_code() の
中身を実際のSMS送信APIコールに置き換えればよい。
"""

import logging
import random
import time

logger = logging.getLogger("hiroba.sms")

CODE_TTL_SECONDS = 300  # 認証コードの有効期限（5分）

# phone_number -> (code, expires_at) のプロセス内メモリストア
# ※本番運用ではDBやRedis等の永続ストアに置き換えることを推奨
_pending_codes: dict[str, tuple[str, float]] = {}


def send_verification_code(phone_number: str) -> str:
    """認証コードを生成し、開発モードではログに出力するのみ（実送信はしない）"""
    code = f"{random.randint(0, 9999):04d}"
    _pending_codes[phone_number] = (code, time.time() + CODE_TTL_SECONDS)
    logger.info("[開発モードSMS] %s 宛の認証コード: %s", phone_number, code)
    return code


def verify_code(phone_number: str, code: str) -> bool:
    """送信済みの認証コードと一致するか確認する（一致したら使い捨て）"""
    entry = _pending_codes.get(phone_number)
    if not entry:
        return False

    stored_code, expires_at = entry
    if time.time() > expires_at:
        _pending_codes.pop(phone_number, None)
        return False

    if stored_code != code:
        return False

    _pending_codes.pop(phone_number, None)
    return True
