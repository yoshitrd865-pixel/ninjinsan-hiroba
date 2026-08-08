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

### ⚠️ このリポジトリには「ひろば」も同居しています

`hiroba/` ディレクトリに、完全に独立した別アプリ「ひろば」（キッズ向けSNS）があります。
`render.yaml` には `engawa` と `hiroba` の2つのWebサービスを定義済みですが、
**Render側の設定方法によって挙動が変わる**ため注意してください。

- このリポジトリを Render の **Blueprint（Infrastructure as Code）** として連携している場合：
  `render.yaml` の変更を push すれば、Renderが自動検知して `hiroba` サービスも
  新規作成・デプロイされます。
- `engawa` サービスを Render管理画面から **手動で「New Web Service」として作成した場合**：
  その既存サービスは `render.yaml` を参照しないため、push だけでは `hiroba` は
  デプロイされません。この場合は、Render管理画面で以下の設定を行い、
  新しいWebサービスを手動で作成してください。
  - 同じGitHubリポジトリを選択
  - Root Directory: `hiroba`
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  - Environment Variables: `HIROBA_SECRET_KEY`（任意の値） / `OPENAI_API_KEY`（任意）

詳細は `hiroba/README.md` を参照してください。

## 将来の拡張


- 音声認識AI（Speech-to-Text）を使った文字入力不要の投稿・会話（`app/services/` にサービスを追加する想定）
- Twilio以外のSMSプロバイダ対応
