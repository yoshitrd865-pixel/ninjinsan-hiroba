# 縁側（えんがわ）

60歳以上向けSNS Webアプリ。FastAPI + Jinja2 + SQLite（SQLAlchemy）構成。

## 主な機能（実際に動作します）

- 携帯電話番号によるログイン・SMS認証
  - Twilio の環境変数（`TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER`）を設定すると本物のSMSを送信
  - 未設定の場合は「開発モード」として画面上に認証コードを表示（そのまま入力してログインできます）
- 写真＋気分スタンプのかんたん投稿（データベースに保存、一覧表示）
- 「〇年前の今日」振り返り（実際の投稿履歴から自動抽出）
- AIとのおしゃべり（`OPENAI_API_KEY` を設定すると実際にAIと会話できます）
- 家族にすぐ電話（`tel:` リンク）
- 🍵 お茶の間（グループおしゃべり）
  - 「誰かとおしゃべりしたい」ボタンで待機列に入り、必要人数が集まると「お茶の間が開きます」とポップアップ通知
  - 待機中は他のページに移動してもOK（サーバー側で状態を保持し、ポーリングで復元）
  - 会話中はAI司会が最初の話題を提示し、会話が止まると次の話題を提案
  - ワンタップ定型文、いつでも退出できる大きなボタンを用意
  - デモ環境では実際の複数ユーザーの代わりに「AIが用意する参加者」で体験できます


## セットアップ

```bash
pip install -r requirements.txt
copy .env.example .env   # Windowsの場合。値を必要に応じて編集
uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000/login` を開いてください。

## 環境変数

`.env.example` を参照してください。

## Renderへのデプロイ

- `render.yaml` / `Procfile` を用意済みです。
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Render管理画面の Environment Variables に `SECRET_KEY` / `OPENAI_API_KEY` 等を設定してください。
- 無料プランではファイルシステムが永続化されない場合があるため、本番運用では外部DB（PostgreSQL等）・外部ストレージの利用を推奨します。

## 将来の拡張

- 音声認識AI（Speech-to-Text）を使った文字入力不要の投稿・会話（`app/services/` にサービスを追加する想定）
- Twilio以外のSMSプロバイダ対応
