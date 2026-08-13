# プロジェクト概要（ひろば / Hiroba）

本ファイルは、キッズ向けSNSアプリ「ひろば」のプログラム構造、アーキテクチャ、主要な設計をまとめたものです。
今後の開発や改修作業を行う際は、**必ず事前にこのファイルを確認・参照**してください。

---

## 1. アプリ概要

- **名称**: ひろば (Hiroba)
- **コンセプト**: 文字入力不要で使える子ども向けソーシャルアプリ。
- **特記事項**: 既存のアプリ「縁側（Engawa）」とは**完全に分離した新規プロジェクト**です。データベース、依存パッケージ、静的ファイル、テンプレートはすべて `hiroba/` ディレクトリ内に独立しています。

---

## 2. ディレクトリ構成 (`hiroba/`)

```text
hiroba/
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI メインアプリケーション、ルーティング設定
│   ├── config.py              # 設定・環境変数管理
│   ├── database.py            # SQLAlchemy 接続・セッション管理
│   ├── auth.py                # 認証・セッション関連ユーティリティ
│   ├── paths.py               # パス定義
│   ├── models/                # データベースモデル (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── user.py            # 保護者・キッズアカウント
│   │   ├── post.py            # 投稿（写真、お絵描き、ボイスメモ、気分スタンプなど）
│   │   ├── promise.py         # 約束機能関連モデル
│   │   ├── reaction.py        # リアクション（やばい！/おもしろい！/すごい！/すてき！）
│   │   └── room.py            # ルーム機能関連モデル
│   ├── routers/               # 各機能のエンドポイント（ルーター）
│   │   ├── __init__.py
│   │   ├── auth.py            # ログイン・認証・キッズ選択
│   │   ├── kids.py            # キッズ向け画面エンドポイント
│   │   ├── oauth.py           # LINE / Google OAuth 連携
│   │   ├── parent_settings.py # 保護者向け管理設定
│   │   ├── promises.py        # 約束機能
│   │   ├── reactions.py       # リアクション機能
│   │   ├── room_content.py    # ルームコンテンツ
│   │   └── rooms.py           # ルーム機能
│   ├── services/              # ビジネスロジック・外部API連携
│   │   ├── __init__.py
│   │   ├── line_notify_service.py # LINE通知サービス
│   │   ├── oauth_service.py   # OAuth 認証サービス
│   │   ├── promise_ai.py      # 約束AIサービス
│   │   ├── sms_service.py     # SMS認証・通知サービス
│   │   ├── uploads.py         # ファイルアップロード処理
│   │   └── whisper_service.py # Whisper音声認識サービス
│   ├── static/                # 静的ファイル (CSS, JS, sounds, uploads)
│   │   ├── css/
│   │   │   └── kids_theme.css
│   │   ├── js/
│   │   └── sounds/
│   └── templates/             # Jinja2 テンプレート
│       ├── auth/              # 認証関連画面 (login, select_kid 等)
│       ├── kids/              # キッズ向け画面 (home, rooms, create 等)
│       └── parent/            # 保護者向け画面 (dashboard, children, rooms 等)
├── tests/                     # pytest によるテストコード
├── requirements.txt           # 依存パッケージ
├── run.py                     # 起動用スクリプト
└── README.md                  # 詳細説明
```

---

## 3. 主要な機能と特徴

1. **文字入力不要のキッズUI**:
   - 特大ボタン、ボイスメモ（音声録音）、お絵描き、気分スタンプなどで直感的に操作可能。
   - ボイスメモは Whisper API 等で自動音声認識され、保護者が内容をテキストで確認可能。
2. **アカウント管理**:
   - 保護者アカウントが子ども（キッズ）アカウントを作成・管理。
   - ログイン方式：電話番号認証に加え、LINEおよびGoogleのOAuth 2.0ログインに対応。
3. **リアクションシステム**:
   - 「やばい！」「おもしろい！」「すごい！」「すてき！」の4種類のスタンプリアクション。
4. **ルーム・約束機能**:
   - 家族やグループごとのルームでコミュニケーション。
   - 子どもと保護者間での「約束」やその達成状況を管理する機能。

---

## 4. 起動時の注意事項（最重要）

ルートディレクトリ（Engawa）にも同名の `app` パッケージが存在するため、**ルートからそのまま起動すると「縁側」のアプリが起動してしまいます。**

必ず `hiroba` ディレクトリを起点として実行してください：

```bash
# 方法1: hirobaディレクトリに移動して起動
cd hiroba
uvicorn app.main:app --reload --port 8001

# 方法2: 専用スクリプトを使用
cd hiroba
python run.py
```

- アクセスURL: `http://localhost:8001` (キッズホーム)、`http://localhost:8001/parent` (保護者ダッシュボード)

---

## 5. 今後の開発におけるガイドライン

1. **ルートの混同防止**: 編集・テスト・起動の際は必ず `hiroba/` 内のコードであることを確認すること。
2. **コードの変更**: 追加・修正時は、本ファイル `PROJECT_OVERVIEW.md` および `hiroba/README.md` の記述と整合性を保つこと。
3. **事前確認**: 今後の作業開始時には、まずこの `PROJECT_OVERVIEW.md` を読み込んでコンテキストを保持すること。
