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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db
from app.paths import STATIC_DIR, TEMPLATES_DIR
from app.routers import auth as auth_router
from app.routers import kids as kids_router
from app.routers import reactions as reactions_router
from app.routers import promises as promises_router
from app.routers import rooms as rooms_router



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

# Jinja2テンプレート（kids/ ・ parent/ ・ auth/ の3系統）
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# APIルーターの登録
app.include_router(auth_router.router)
app.include_router(kids_router.router)
app.include_router(reactions_router.router)
app.include_router(promises_router.router)
app.include_router(rooms_router.router)




@app.on_event("startup")
def on_startup():
    init_db()


# ------------------------------------------------------------------
# ログイン・キッズ選択ページ（保護者は電話番号＋認証コード、
# キッズはアイコンをワンタップで選ぶだけのUI）
# ------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@app.get("/select-kid", response_class=HTMLResponse)
async def select_kid_page(request: Request):
    return templates.TemplateResponse("auth/select_kid.html", {"request": request})


# ------------------------------------------------------------------
# キッズ向けページ
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    """ルートアクセスはキッズ向けホーム画面へリダイレクトする"""
    return RedirectResponse(url="/kids/home")


@app.get("/kids/home", response_class=HTMLResponse)
async def kids_home(request: Request):
    """「みんなのひろば」タイムライン画面（お絵描き・写真・ボイスメモ・リアクション）"""
    context = {
        "request": request,
        "active": "home",
        "app_name": "ひろば",
    }
    return templates.TemplateResponse("kids/home.html", context)


@app.get("/kids/create", response_class=HTMLResponse)
async def kids_create(request: Request):
    """作品・ボイス投稿画面（お絵描き・ボイスメモ・気分スタンプ）"""
    context = {
        "request": request,
        "active": "create",
        "app_name": "ひろば",
    }
    return templates.TemplateResponse("kids/create.html", context)


@app.get("/kids/ochanoma", response_class=HTMLResponse)
async def kids_ochanoma(request: Request):
    """おちゃのま（キッズ同士の「遊ぶ約束」機能：AI司会＋保護者承認フロー）"""
    context = {
        "request": request,
        "active": "ochanoma",
        "app_name": "ひろば",
    }
    return templates.TemplateResponse("kids/ochanoma.html", context)



@app.get("/kids/rooms", response_class=HTMLResponse)
async def kids_rooms(request: Request):
    """わたしのおへや（完全クローズド・招待制のグループ機能）"""
    context = {
        "request": request,
        "active": "rooms",
        "app_name": "ひろば",
    }
    return templates.TemplateResponse("kids/rooms.html", context)


@app.get("/kids/oyako", response_class=HTMLResponse)

async def kids_oyako(request: Request):
    """おうちひと（保護者ページへの案内。まだこの画面自体は簡易表示）"""
    context = {
        "request": request,
        "active": "oyako",
        "app_name": "ひろば",
        "emoji": "👨‍👩‍👧",
        "title": "おうちのひと",
        "message": "おうちの人と いっしょに みてね！",
        "action_url": "/parent",
        "action_label": "ほごしゃ用ページを ひらく",
    }
    return templates.TemplateResponse("kids/coming_soon.html", context)


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


# ------------------------------------------------------------------
# 404エラーハンドリング
# ナビゲーションタブや将来のリンク先が未実装でも、キッズ向けには
# 「準備中だよ！」の仮画面を表示し、素の404エラーにはしない。
# ------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # APIエンドポイント（/api/...）はこれまで通りJSONでエラーを返す
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    if exc.status_code == 404:
        context = {
            "request": request,
            "active": None,
            "app_name": "ひろば",
            "emoji": "🚧",
            "title": "じゅんびちゅう",
            "message": "このページは まだ じゅんびちゅうだよ！\n「ひろば」にもどって あそんでね。",
        }
        return templates.TemplateResponse(
            "kids/coming_soon.html", context, status_code=404
        )

    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
