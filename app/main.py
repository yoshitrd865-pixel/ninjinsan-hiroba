"""
縁側（えんがわ） - 60歳以上向けSNS Webアプリ
FastAPI エントリーポイント

実際に動作する機能:
- SMS認証（開発モードでは画面にコードを表示。Twilio連携時は本物のSMSを送信）
- 電話番号ベースのログイン・セッション管理
- 写真＋気分スタンプのかんたん投稿（データベースに永続化）
- 「〇年前の今日」振り返り（実際の投稿履歴から検索）
- AIとのおしゃべり（OpenAI APIキーを設定すれば実際に会話できる）
- 家族に電話（tel:リンク）

将来的な拡張:
- 音声認識AI（Speech-to-Text）を使った文字入力不要の投稿・会話
"""

import os
import random
import shutil
import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import extract

from app.database import get_db, init_db
from app.models import User, SmsCode, Post, ChatMessage, PostReaction
from app.auth import get_current_user, login_user, logout_user
from app.services.sms_service import send_sms, SMS_LIVE_MODE
from app.services.ai_service import generate_reply, AI_ENABLED
from app.services import ochanoma_service

# ------------------------------------------------------------------
# パス設定
# ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = STATIC_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.environ.get("SECRET_KEY", "engawa-dev-secret-key-change-me")
SMS_CODE_TTL_MINUTES = 5

# ------------------------------------------------------------------
# アプリケーション初期化
# ------------------------------------------------------------------
app = FastAPI(
    title="縁側（えんがわ）",
    description="60歳以上向けSNS「縁側」",
    version="0.2.0",
)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# 静的ファイル（CSS / JS / 画像 / アップロード写真）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Jinja2テンプレート
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.on_event("startup")
def on_startup():
    init_db()


# ------------------------------------------------------------------
# 共通ヘルパー
# ------------------------------------------------------------------
def common_context(request: Request, active: str, user: User | None) -> dict:
    return {
        "request": request,
        "active": active,
        "app_name": "縁側",
        "current_user": user,
    }


def require_login(user: User | None):
    if user is None:
        raise HTTPException(status_code=401, detail="ログインが必要です")


STAMP_LABELS = {
    "😊": "嬉しかった",
    "😋": "美味しかった",
    "😲": "びっくりした",
    "😌": "のんびりした",
}

REACTION_TYPES = {"warm", "cheer"}


def humanize_time(dt: datetime.datetime) -> str:
    """投稿日時を『10分前』のような相対表現に変換する"""
    now = datetime.datetime.utcnow()
    seconds = (now - dt).total_seconds()
    if seconds < 60:
        return "たった今"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}分前"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours}時間前"
    days = int(hours // 24)
    if days < 7:
        return f"{days}日前"
    return dt.strftime("%Y年%m月%d日")


def _build_timeline_posts(db: Session, user: User, limit: int = 50) -> list[dict]:
    """全ユーザーの投稿を新着順に取得し、リアクション情報を付与して返す"""
    posts = (
        db.query(Post)
        .options(joinedload(Post.user), joinedload(Post.reactions))
        .order_by(Post.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for post in posts:
        warm_count = sum(1 for r in post.reactions if r.reaction_type == "warm")
        cheer_count = sum(1 for r in post.reactions if r.reaction_type == "cheer")
        my_reactions = {
            r.reaction_type for r in post.reactions if r.user_id == user.id
        }
        result.append(
            {
                "id": post.id,
                "image_path": post.image_path,
                "stamp": post.stamp,
                "stamp_label": post.stamp_label,
                "author_name": post.user.display_name if post.user else "ゲスト",
                "is_mine": post.user_id == user.id,
                "time_label": humanize_time(post.created_at),
                "warm_count": warm_count,
                "cheer_count": cheer_count,
                "reacted_warm": "warm" in my_reactions,
                "reacted_cheer": "cheer" in my_reactions,
            }
        )
    return result




# ==================================================================
# ページルーティング
# ==================================================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/", status_code=303)
    context = common_context(request, active="login", user=None)
    context["sms_live_mode"] = SMS_LIVE_MODE
    return templates.TemplateResponse("login.html", context)


@app.get("/", response_class=HTMLResponse)
async def mypage(
    request: Request,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    context = common_context(request, active="home", user=user)

    # 自分の投稿一覧（新しい順）
    posts = (
        db.query(Post)
        .filter(Post.user_id == user.id)
        .order_by(Post.created_at.desc())
        .limit(20)
        .all()
    )
    context["posts"] = posts

    # 「〇年前の今日」: 今日と同じ月日で、今年以外に投稿された最も古いもの
    today = datetime.date.today()
    memory_post = (
        db.query(Post)
        .filter(
            Post.user_id == user.id,
            extract("month", Post.created_at) == today.month,
            extract("day", Post.created_at) == today.day,
            extract("year", Post.created_at) != today.year,
        )
        .order_by(Post.created_at.asc())
        .first()
    )

    if memory_post:
        years_ago = today.year - memory_post.created_at.year
        context["memory"] = {
            "years_ago": years_ago,
            "image": memory_post.image_path,
            "stamp": memory_post.stamp,
            "stamp_label": memory_post.stamp_label,
            "date_label": memory_post.created_at.strftime("%Y年%m月%d日"),
        }
    else:
        context["memory"] = None

    return templates.TemplateResponse("index.html", context)


@app.get("/talk", response_class=HTMLResponse)
async def talk_page(
    request: Request,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    context = common_context(request, active="talk", user=user)
    context["ai_enabled"] = AI_ENABLED

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    context["chat_history"] = history
    return templates.TemplateResponse("talk.html", context)


@app.get("/ochanoma", response_class=HTMLResponse)
async def ochanoma_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    context = common_context(request, active="ochanoma", user=user)
    return templates.TemplateResponse("ochanoma.html", context)


@app.get("/timeline", response_class=HTMLResponse)
async def timeline_page(
    request: Request,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """みんなの縁側：全ユーザーの投稿を新着順に一覧表示するタイムライン"""
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    context = common_context(request, active="timeline", user=user)
    context["timeline_posts"] = _build_timeline_posts(db, user, limit=50)
    return templates.TemplateResponse("timeline.html", context)



@app.post("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/login", status_code=303)



# ==================================================================
# 認証API
# ==================================================================
@app.post("/api/auth/send-code")
async def send_code(
    request: Request,
    phone_number: str = Form(...),
    db: Session = Depends(get_db),
):
    phone_number = phone_number.strip().replace("-", "")
    if len(phone_number) < 10:
        raise HTTPException(status_code=400, detail="正しい携帯電話番号を入力してください")

    code = f"{random.randint(0, 9999):04d}"
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=SMS_CODE_TTL_MINUTES
    )

    sms_code = SmsCode(
        phone_number=phone_number,
        code=code,
        expires_at=expires_at,
        verified=False,
    )
    db.add(sms_code)
    db.commit()

    sent_live = send_sms(phone_number, code)

    response = {
        "success": True,
        "live_mode": sent_live,
        "message": "認証コードをSMSで送信しました。"
        if sent_live
        else "開発モードのため、下記のコードをそのまま入力してください。",
    }
    # 開発モード（Twilio未設定）の場合のみ、コードを画面に表示するために返す
    if not sent_live:
        response["debug_code"] = code

    return JSONResponse(response)


@app.post("/api/auth/verify-code")
async def verify_code(
    request: Request,
    phone_number: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db),
):
    phone_number = phone_number.strip().replace("-", "")

    sms_code = (
        db.query(SmsCode)
        .filter(SmsCode.phone_number == phone_number, SmsCode.verified == False)  # noqa: E712
        .order_by(SmsCode.created_at.desc())
        .first()
    )

    if not sms_code:
        raise HTTPException(status_code=400, detail="認証コードが見つかりません。もう一度送信してください。")

    if datetime.datetime.utcnow() > sms_code.expires_at:
        raise HTTPException(status_code=400, detail="認証コードの有効期限が切れました。もう一度送信してください。")

    if sms_code.code != code:
        raise HTTPException(status_code=400, detail="認証コードが正しくありません。")

    sms_code.verified = True
    db.add(sms_code)

    user = db.query(User).filter(User.phone_number == phone_number).first()
    if not user:
        user = User(phone_number=phone_number, display_name="ゲスト")
        db.add(user)

    db.commit()
    db.refresh(user)

    login_user(request, user)

    return JSONResponse({"success": True, "redirect": "/"})


# ==================================================================
# 投稿API
# ==================================================================
@app.post("/api/posts")
async def create_post(
    request: Request,
    stamp: str = Form(...),
    photo: UploadFile | None = File(None),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_login(user)

    if stamp not in STAMP_LABELS:
        raise HTTPException(status_code=400, detail="気分スタンプを選択してください")

    image_path = None
    if photo is not None and photo.filename:
        ext = Path(photo.filename).suffix or ".jpg"
        filename = f"{user.id}_{int(datetime.datetime.utcnow().timestamp() * 1000)}{ext}"
        dest_path = UPLOAD_DIR / filename
        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        image_path = f"/static/uploads/{filename}"

    post = Post(
        user_id=user.id,
        image_path=image_path,
        stamp=stamp,
        stamp_label=STAMP_LABELS[stamp],
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return JSONResponse(
        {
            "success": True,
            "post": {
                "id": post.id,
                "image_path": post.image_path,
                "stamp": post.stamp,
                "stamp_label": post.stamp_label,
                "created_at": post.created_at.strftime("%Y年%m月%d日 %H:%M"),
            },
        }
    )


@app.get("/api/timeline/posts")
async def timeline_posts_api(
    request: Request,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """みんなの投稿一覧をJSONで返す（新着順）"""
    require_login(user)
    return JSONResponse({"success": True, "posts": _build_timeline_posts(db, user, limit=50)})


@app.post("/api/posts/{post_id}/react")
async def react_to_post(
    post_id: int,
    request: Request,
    reaction_type: str = Form(...),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """他の人の投稿に「🌸 温かいね」「応援する」を送る（もう一度押すと取り消し）"""
    require_login(user)

    if reaction_type not in REACTION_TYPES:
        raise HTTPException(status_code=400, detail="不正なリアクション種別です")

    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="投稿が見つかりません")

    existing = (
        db.query(PostReaction)
        .filter(
            PostReaction.post_id == post_id,
            PostReaction.user_id == user.id,
            PostReaction.reaction_type == reaction_type,
        )
        .first()
    )

    if existing:
        db.delete(existing)
        db.commit()
        reacted = False
    else:
        reaction = PostReaction(
            post_id=post_id, user_id=user.id, reaction_type=reaction_type
        )
        db.add(reaction)
        db.commit()
        reacted = True

    warm_count = (
        db.query(PostReaction)
        .filter(PostReaction.post_id == post_id, PostReaction.reaction_type == "warm")
        .count()
    )
    cheer_count = (
        db.query(PostReaction)
        .filter(PostReaction.post_id == post_id, PostReaction.reaction_type == "cheer")
        .count()
    )

    return JSONResponse(
        {
            "success": True,
            "reacted": reacted,
            "reaction_type": reaction_type,
            "warm_count": warm_count,
            "cheer_count": cheer_count,
        }
    )


# ==================================================================
# AIおしゃべりAPI
# ==================================================================
@app.post("/api/talk/message")
async def talk_message(
    request: Request,

    message: str = Form(...),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_login(user)

    message = message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="メッセージを入力してください")

    user_msg = ChatMessage(user_id=user.id, role="user", content=message)
    db.add(user_msg)
    db.commit()

    # 直近の会話履歴（最大10件）をAPIに渡す
    recent = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history = [
        {"role": m.role, "content": m.content} for m in reversed(recent)
    ]

    reply_text = generate_reply(history)

    ai_msg = ChatMessage(user_id=user.id, role="assistant", content=reply_text)
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)

    return JSONResponse(
        {
            "success": True,
            "reply": reply_text,
            "ai_enabled": AI_ENABLED,
        }
    )


# ==================================================================
# お茶の間API（グループおしゃべり）
# ==================================================================
@app.post("/api/ochanoma/join")
async def ochanoma_join(
    request: Request,
    style: str = Form(...),
    topics: str = Form(""),
    user: User | None = Depends(get_current_user),
):
    require_login(user)
    topic_list = [t for t in (topics.split(",") if topics else []) if t]
    status = ochanoma_service.join_waiting(
        user.id, user.display_name, style, topic_list
    )
    return JSONResponse(status)


@app.get("/api/ochanoma/status")
async def ochanoma_status(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    require_login(user)
    status = ochanoma_service.get_status(user.id)
    return JSONResponse(status)


@app.post("/api/ochanoma/cancel")
async def ochanoma_cancel(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    require_login(user)
    ochanoma_service.leave_ochanoma(user.id)
    return JSONResponse({"success": True})


@app.post("/api/ochanoma/room/{room_id}/confirm")
async def ochanoma_confirm(
    room_id: str,
    request: Request,
    user: User | None = Depends(get_current_user),
):
    require_login(user)
    detail = ochanoma_service.confirm_room(user.id, room_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="お茶の間が見つかりません")
    return JSONResponse({"success": True, "room": detail})


@app.get("/api/ochanoma/room/{room_id}")
async def ochanoma_room_detail(
    room_id: str,
    request: Request,
    user: User | None = Depends(get_current_user),
):
    require_login(user)
    detail = ochanoma_service.get_room_detail(user.id, room_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="お茶の間が見つかりません")
    return JSONResponse({"success": True, "room": detail})


@app.get("/api/ochanoma/room/{room_id}/messages")
async def ochanoma_room_messages(
    room_id: str,
    request: Request,
    user: User | None = Depends(get_current_user),
):
    require_login(user)
    messages = ochanoma_service.get_messages(user.id, room_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="お茶の間が見つかりません")
    return JSONResponse({"success": True, "messages": messages})


@app.post("/api/ochanoma/room/{room_id}/messages")
async def ochanoma_post_message(
    room_id: str,
    request: Request,
    text: str = Form(...),
    user: User | None = Depends(get_current_user),
):
    require_login(user)
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="メッセージを入力してください")
    messages = ochanoma_service.post_message(user.id, room_id, text)
    if messages is None:
        raise HTTPException(status_code=404, detail="お茶の間が見つかりません")
    return JSONResponse({"success": True, "messages": messages})


@app.post("/api/ochanoma/room/{room_id}/leave")
async def ochanoma_leave_room(
    room_id: str,
    request: Request,
    user: User | None = Depends(get_current_user),
):
    require_login(user)
    ochanoma_service.leave_ochanoma(user.id)
    return JSONResponse({"success": True})


# ------------------------------------------------------------------
# ヘルスチェック（Render監視用）
# ------------------------------------------------------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


