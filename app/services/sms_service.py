"""
SMS送信サービス

環境変数 TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER が
すべて設定されている場合は Twilio を使って実際にSMSを送信する。
設定されていない場合は「開発モード」として実際の送信は行わず、
呼び出し元（ルーティング側）でコードを画面表示できるようにする。
"""

import os
import logging

logger = logging.getLogger("engawa.sms")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")

SMS_LIVE_MODE = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)


def send_sms(phone_number: str, code: str) -> bool:
    """
    SMSで認証コードを送信する。

    戻り値:
        True  = 実際に送信できた（本番モード）
        False = 開発モード（実際には送っていない。呼び出し元で画面表示する）
    """
    message = f"【縁側】認証コードは {code} です。5分以内にご入力ください。"

    if not SMS_LIVE_MODE:
        # 開発モード: 実際には送信せず、ログにのみ出力する
        logger.info("[開発モードSMS] %s 宛: %s", phone_number, message)
        return False

    try:
        from twilio.rest import Client  # 遅延インポート（未インストール時にも起動可能にする）

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=phone_number,
        )
        return True
    except Exception:
        logger.exception("SMS送信に失敗しました。開発モードにフォールバックします。")
        return False
