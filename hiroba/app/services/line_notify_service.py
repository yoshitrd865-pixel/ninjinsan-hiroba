"""
保護者LINE通知サービス（ひろば・開発用ダミー実装）

本番では LINE Messaging API 等と連携し、双方の保護者へ
お約束の確認依頼・成立・キャンセル・おへやのお誘いなどの
メッセージを送信する想定。

開発モードでは実際には送信せず、ログ出力とプロセス内メモリの
履歴保存のみを行う（保護者ダッシュボードでの確認や、テストコードでの
検証に利用できる）。

本番運用時に実際のLINE連携へ切り替える場合は、notify_parent() の
中身を実際のMessaging API呼び出しに置き換えればよい
（呼び出し元のロジックは変更不要）。
"""

import logging

logger = logging.getLogger("hiroba.line_notify")

# テスト・デバッグ用：送信履歴をプロセス内に保持する（本番のLINE連携時は不要）
sent_messages: list[dict] = []


def notify_parent(parent, message: str) -> None:
    """保護者へ確認依頼・成立・キャンセル等のLINE通知を送る（開発モードはログのみ）

    - parent  : 通知先の保護者 User（None なら何もしない）
    - message : 送信するメッセージ本文（日付・時間帯・場所・相手キッズ名など
                キッズ向け情報のみを含み、どちらの親が断ったか等の理由は含めない）

    保護者が /parent/notifications でLINE通知をOFFにしている場合は、
    実際には送信しない（履歴にも残さない）。
    """
    if parent is None:
        return
    if getattr(parent, "line_notify_enabled", True) is False:
        logger.info(
            "[開発モードLINE] parent_id=%s は通知OFFのため送信をスキップしました",
            getattr(parent, "id", None),
        )
        return


    entry = {"parent_id": getattr(parent, "id", None), "message": message}
    sent_messages.append(entry)
    logger.info("[開発モードLINE] parent_id=%s message=%s", entry["parent_id"], message)
