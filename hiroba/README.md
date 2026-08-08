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
uvicorn app.main:app --reload --port 8001
```

ブラウザで `http://localhost:8001` を開くとキッズ向けホーム画面、
`http://localhost:8001/parent` で保護者用ダッシュボードが表示されます。
