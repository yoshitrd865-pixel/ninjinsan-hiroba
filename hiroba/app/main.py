"""
ひろば - キッズ向けSNS Webアプリ
FastAPI エントリーポイント

既存アプリ「縁側」とは完全に分離された、新規プロジェクトです。
（データベース・静的ファイル・テンプレート・依存パッケージも独立しています）

特徴:
- 文字入力不要のキッズ向けUI（特大ボタン・ボイスメモ・お絵描き）
- 保護者アカウントがキッズアカウントを管理
- 「やばい！」「おもしろい！」「すごい！」「すてき！」の4種類のリアクション
- ボイスメモは Whisper で音声認識し、テキスト化して保護者が確認できる
"""

import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db
from app.paths import STATIC_DIR, TEMPLATES_DIR
from app.routers import auth as auth_router
from app.routers import kids as kids_router
from app.routers import reactions as reactions_router

SECRET_KEY = os.environ.get("HIROBA_SECRET_KEY", "hiroba-dev-secret-key-change-me")

# ------------------------------------------------------------------
# アプリケーション初期化
# ------------------------------------------------------------------
app = FastAPI(
    title="ひろば",
    description="キッズ向けSNS「ひろば」",
    version="0.2.0",
)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# 静的ファイル（CSS / JS / 音 / アップロード画像・音声）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Jinja2テンプレート（kids/ ・ parent/ の2系統）
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# APIルーターの登録
app.include_router(auth_router.router)
app.include_router(kids_router.router)
app.include_router(reactions_router.router)


@app.on_event("startup")
def on_startup():
    init_db()


# ------------------------------------------------------------------
# キッズ向けページ
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    """ルートアクセスはキッズ向けホーム画面へリダイレクトする"""
    return RedirectResponse(url="/kids/home")


@app.get("/kids/home", response_class=HTMLResponse)
async def kids_home(request: Request):
    """キッズ向けホーム画面（特大ボタンで撮影・お絵描き・録音へ）"""
    context = {
        "request": request,
        "active": "home",
        "app_name": "ひろば",
    }
    return templates.TemplateResponse("kids/home.html", context)


# ------------------------------------------------------------------
# 保護者向けページ
# ------------------------------------------------------------------
@app.get("/parent", response_class=HTMLResponse)
async def parent_dashboard(request: Request):
    """保護者用ダッシュボード（キッズアカウント管理・投稿確認）"""
    context = {
        "request": request,
        "app_name": "ひろば",
    }
    return templates.TemplateResponse("parent/dashboard.html", context)


# ------------------------------------------------------------------
# ヘルスチェック
# ------------------------------------------------------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok", "app": "hiroba"}
