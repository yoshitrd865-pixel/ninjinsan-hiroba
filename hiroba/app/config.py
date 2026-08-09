"""
アプリケーション設定（ひろば）

LINEログイン／Googleログイン（本番OAuth 2.0 認証フロー）、および
LINE Messaging API（保護者への通知送信）で使用する環境変数をまとめる。

.env（.env.example を参考に作成）または本番のホスティング環境の
環境変数として、以下を設定する。

- LINE_CHANNEL_ID                      : LINEログイン用チャネルID
- LINE_CHANNEL_SECRET                  : LINEログイン用チャネルシークレット
- LINE_MESSAGING_CHANNEL_ACCESS_TOKEN  : LINE Messaging API（通知送信）用アクセストークン
- GOOGLE_CLIENT_ID                     : GoogleログインのOAuthクライアントID
- GOOGLE_CLIENT_SECRET                 : GoogleログインのOAuthクライアントシークレット
- BASE_URL                             : このアプリの公開URL（OAuthコールバックURL生成に使用）

いずれも未設定の場合は空文字列がデフォルトとなり、該当のログイン方法は
無効（/auth/line/login 等が503を返す）になる。開発中は電話番号ログイン
（/api/auth/*）のみでも動作するよう設計している。
"""

import os


class Settings:
    """環境変数から読み込む設定値（インスタンス属性なのでテストでの上書きが容易）"""

    def __init__(self) -> None:
        # OAuthコールバックURLの生成に使うベースURL（末尾のスラッシュは除去する）
        self.BASE_URL: str = os.environ.get(
            "BASE_URL", "http://localhost:8000"
        ).rstrip("/")

        # --- LINEログイン（LINE Developersコンソールで発行） ---
        self.LINE_CHANNEL_ID: str = os.environ.get("LINE_CHANNEL_ID", "")
        self.LINE_CHANNEL_SECRET: str = os.environ.get("LINE_CHANNEL_SECRET", "")

        # --- LINE Messaging API（保護者への通知送信専用。ログインとは別チャネル） ---
        self.LINE_MESSAGING_CHANNEL_ACCESS_TOKEN: str = os.environ.get(
            "LINE_MESSAGING_CHANNEL_ACCESS_TOKEN", ""
        )

        # --- Googleログイン（Google Cloud ConsoleのOAuth 2.0クライアント） ---
        self.GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.GOOGLE_CLIENT_SECRET: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    @property
    def line_login_enabled(self) -> bool:
        return bool(self.LINE_CHANNEL_ID and self.LINE_CHANNEL_SECRET)

    @property
    def google_login_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)


# アプリ全体で共有する単一のSettingsインスタンス
# （テストでは `monkeypatch.setattr(settings, "LINE_CHANNEL_ID", "...")` のように
#   属性を直接差し替えることで、実際のOAuth連携なしに検証できる）
settings = Settings()


def line_redirect_uri() -> str:
    """LINEログインのコールバックURL（LINE Developersコンソールに登録するURLと一致させる）"""
    return f"{settings.BASE_URL}/auth/line/callback"


def google_redirect_uri() -> str:
    """GoogleログインのコールバックURL（Google Cloud ConsoleのOAuthクライアントに登録するURLと一致させる）"""
    return f"{settings.BASE_URL}/auth/google/callback"
