# ひろば

キッズ向けSNS「ひろば」- 文字入力不要で使える子ども向けソーシャルアプリ。

既存アプリ「縁側（Engawa）」とは **完全に分離した新規プロジェクト** です。
データベース、依存パッケージ、静的ファイル、テンプレートはすべて独立しています。

## 特徴

- 文字入力不要のキッズ向けUI（特大ボタン・ボイスメモ・お絵描き）
- 保護者アカウントがキッズアカウントを作成・管理
- 「やばい！」「おもしろい！」「すごい！」「すてき！」の4種類のリアクション
- ボイスメモを Whisper 等で音声認識し、保護者が内容を確認できる

## 構成

```
hiroba/
├── app/
│   ├── main.py            # FastAPI エントリーポイント
│   ├── database.py        # SQLAlchemy 接続設定
│   ├── models/
│   │   ├── user.py        # 保護者・キッズアカウント
│   │   ├── post.py        # 投稿（写真/お絵描き/ボイスメモ/気分スタンプ）
│   │   └── reaction.py    # リアクション（やばい！/おもしろい！/すごい！/すてき！）
│   ├── routers/            # （今後のAPIルーター追加用）
│   ├── services/           # （今後のビジネスロジック追加用）
│   ├── static/
│   │   ├── css/kids_theme.css
│   │   ├── js/
│   │   └── sounds/
│   └── templates/
│       ├── kids/           # キッズ向け画面
│       └── parent/         # 保護者向け画面
└── requirements.txt
```

## セットアップ

```bash
cd hiroba
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env
```

## 起動方法（重要）

⚠️ **注意**: リポジトリのルートディレクトリ（Engawa）にも「縁側」用の
`app` パッケージが存在します。**`hiroba` ディレクトリに `cd` せずに
ルートディレクトリのまま `uvicorn app.main:app` を実行すると、
Pythonが縁側側の `app` パッケージを読み込んでしまい、
「ひろば」ではなく「縁側」の画面が表示されます。**

必ず以下のいずれかの方法で起動してください。

### 方法1: `hiroba` ディレクトリに移動してから起動する（推奨）

```bash
cd hiroba
uvicorn app.main:app --reload --port 8001
```

### 方法2: 付属の起動スクリプトを使う

`hiroba` ディレクトリを確実に優先読み込みするため、以下のスクリプトも用意しています。

```bash
cd hiroba
python run.py
```

いずれの方法でも、ブラウザで `http://localhost:8001` を開くと
キッズ向けホーム画面（`/kids/home` にリダイレクト）、
`http://localhost:8001/parent` で保護者用ダッシュボードが表示されます。

もし「縁側」の画面（ログイン画面等）が表示された場合は、
カレントディレクトリが `hiroba` になっていない可能性が高いです。
`cd` コマンドで `hiroba` ディレクトリに入っているか確認してください。

## Renderへのデプロイ

このリポジトリのルート `render.yaml` には `engawa` と `hiroba` の
2つのWebサービスが定義済みです（`hiroba` サービスは `rootDir: hiroba` を
指定しており、このディレクトリを起点にビルド・起動されます）。

- Render を **Blueprint（Infrastructure as Code）** で連携している場合：
  そのまま push すれば `hiroba` サービスも自動的にデプロイされます。
- `engawa` を Render管理画面から手動でWebサービスとして作成している場合：
  `render.yaml` は自動反映されないため、Render管理画面で新しいWebサービスを
  手動作成し、以下を設定してください。
  - Root Directory: `hiroba`
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  - Environment Variables:
    - `HIROBA_SECRET_KEY`（ランダムな文字列）
    - `OPENAI_API_KEY`（ボイスメモのWhisper音声認識を使う場合のみ）
    - `HIROBA_DATABASE_URL`（本番運用ではSQLiteではなくPostgreSQL等を推奨）
    - `BASE_URL`（このアプリの公開URL。OAuthコールバックURL生成に使用）
    - `LINE_CHANNEL_ID` / `LINE_CHANNEL_SECRET`（LINEログインを使う場合）
    - `LINE_MESSAGING_CHANNEL_ACCESS_TOKEN`（LINE通知送信を使う場合）
    - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`（Googleログインを使う場合）

無料プランではファイルシステムが永続化されない場合があるため、
本番運用ではアップロード画像・音声も外部ストレージの利用を推奨します。

## LINEログイン／Googleログイン（本番OAuth 2.0）

保護者は電話番号ログインに加え、LINEアカウント・Googleアカウントでも
ログインできます（`/auth/line/login`, `/auth/google/login`）。

セットアップ:

1. **LINEログイン**: [LINE Developers](https://developers.line.biz/) で
   LINEログイン用チャネルを作成し、Callback URLに
   `{BASE_URL}/auth/line/callback` を登録。発行された
   Channel ID / Channel Secret を `LINE_CHANNEL_ID` / `LINE_CHANNEL_SECRET`
   に設定してください。
2. **Googleログイン**: [Google Cloud Console](https://console.cloud.google.com/)
   でOAuthクライアント（ウェブアプリケーション）を作成し、承認済みの
   リダイレクトURIに `{BASE_URL}/auth/google/callback` を登録。
   発行されたクライアントID/シークレットを `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET` に設定してください。
3. いずれの環境変数も未設定の場合、対応するログインボタンを押すと
   503エラー（現在利用できません）になりますが、既存の電話番号ログインは
   影響を受けず動作します。

ログイン成功時は、LINEのuserId／GoogleのsubIDに紐づく既存の保護者
アカウントがあればそのままログインし、なければ新規登録されます
（Googleログインの場合、既に電話番号ログインで登録済みの同一メール
アドレスの保護者アカウントがあれば、そのアカウントに自動的に紐付けます）。
その後 `/select-kid` （キッズ選択画面）へ遷移します。




