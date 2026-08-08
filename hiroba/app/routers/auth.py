"""
認証ルーター（ひろば）

- 保護者: 電話番号 + 開発用ダミーSMS認証コードでログイン／新規登録
- キッズ: 保護者アカウントに紐づく複数のキッズ（例:「たろう」「はなこ」）を
          追加・一覧取得・選択（切り替え）できる

キッズは文字入力ができないため、保護者がスマホでログインしたあと、
子ども自身はアイコンをタップして自分を選ぶだけでよい設計にしている。
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import (
    get_active_user,
    get_current_parent,
    login_parent,
    logout as session_logout,
    select_active_profile,
)
from app.database import get_db
from app.models import User
from app.services.sms_service import send_verification_code, verify_code

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _normalize_phone(phone_number: str) -> str:
    phone_number = phone_number.strip().replace("-", "")
    if len(phone_number) < 10:
        raise HTTPException(status_code=400, detail="正しい電話番号を入力してください")
    return phone_number


def _serialize_kid(kid: User) -> dict:
    return {
        "id": kid.id,
        "display_name": kid.display_name,
        "avatar_icon": kid.avatar_icon,
        "has_pin": bool(kid.pin_code),
    }


# ------------------------------------------------------------------
# 保護者ログイン（電話番号＋開発用ダミーSMS）
# ------------------------------------------------------------------
@router.post("/send-code")
async def send_code(phone_number: str = Form(...)):
    """保護者の電話番号に認証コードを送る（開発モード：実際には送信せず画面に表示）"""
    phone_number = _normalize_phone(phone_number)
    code = send_verification_code(phone_number)

    return JSONResponse(
        {
            "success": True,
            "message": "開発モードのため、下記のコードをそのまま入力してください。",
            "debug_code": code,
        }
    )


@router.post("/verify-code")
async def verify_code_endpoint(
    request: Request,
    phone_number: str = Form(...),
    code: str = Form(...),
    display_name: str = Form("保護者"),
    db: Session = Depends(get_db),
):
    """認証コードを確認し、保護者アカウントでログインする（未登録なら新規作成）"""
    phone_number = _normalize_phone(phone_number)

    if not verify_code(phone_number, code):
        raise HTTPException(
            status_code=400, detail="認証コードが正しくないか、期限切れです"
        )

    parent = (
        db.query(User)
        .filter(User.role == "parent", User.phone_number == phone_number)
        .first()
    )
    if not parent:
        parent = User(
            role="parent",
            phone_number=phone_number,
            display_name=display_name.strip() or "保護者",
        )
        db.add(parent)
        db.commit()
        db.refresh(parent)

    login_parent(request, parent)

    kids = (
        db.query(User)
        .filter(User.role == "kids", User.parent_id == parent.id)
        .order_by(User.created_at.asc())
        .all()
    )

    return JSONResponse(
        {
            "success": True,
            "parent": {"id": parent.id, "display_name": parent.display_name},
            "kids": [_serialize_kid(k) for k in kids],
        }
    )


# ------------------------------------------------------------------
# キッズアカウントの追加・一覧・選択
# ------------------------------------------------------------------
@router.get("/kids")
async def list_kids(
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """ログイン中の保護者に紐づくキッズ一覧を返す"""
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    kids = (
        db.query(User)
        .filter(User.role == "kids", User.parent_id == parent.id)
        .order_by(User.created_at.asc())
        .all()
    )
    return JSONResponse({"success": True, "kids": [_serialize_kid(k) for k in kids]})


@router.post("/kids/add")
async def add_kid(
    display_name: str = Form(...),
    avatar_icon: str = Form(""),
    pin_code: str = Form(""),
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """保護者がキッズアカウントを追加する（例:「たろう」「はなこ」）"""
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    display_name = display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="お名前を入力してください")

    if pin_code and (len(pin_code) != 4 or not pin_code.isdigit()):
        raise HTTPException(
            status_code=400, detail="PINコードは4桁の数字で入力してください"
        )

    kid = User(
        role="kids",
        display_name=display_name,
        avatar_icon=avatar_icon or None,
        pin_code=pin_code or None,
        parent_id=parent.id,
    )
    db.add(kid)
    db.commit()
    db.refresh(kid)

    return JSONResponse({"success": True, "kid": _serialize_kid(kid)})


@router.post("/kids/{kid_id}/select")
async def select_kid(
    kid_id: int,
    request: Request,
    pin_code: str = Form(""),
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """キッズを選んで、そのプロフィールをセッション上でアクティブにする

    文字入力不要にするため、基本はアイコンをタップするだけで選べる。
    保護者がPINコードを設定していた場合のみ、その入力を必須とする。
    """
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    kid = (
        db.query(User)
        .filter(User.id == kid_id, User.role == "kids", User.parent_id == parent.id)
        .first()
    )
    if kid is None:
        raise HTTPException(status_code=404, detail="キッズアカウントが見つかりません")

    if kid.pin_code and kid.pin_code != pin_code:
        raise HTTPException(status_code=400, detail="PINコードが正しくありません")

    select_active_profile(request, kid)

    return JSONResponse(
        {
            "success": True,
            "active_user": {
                "id": kid.id,
                "role": kid.role,
                "display_name": kid.display_name,
                "avatar_icon": kid.avatar_icon,
            },
        }
    )


@router.post("/select-parent")
async def select_parent_profile(
    request: Request,
    parent: User | None = Depends(get_current_parent),
):
    """アクティブプロフィールを保護者自身に戻す（キッズ選択の解除）"""
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")
    select_active_profile(request, parent)
    return JSONResponse({"success": True})


# ------------------------------------------------------------------
# 現在のログイン状態確認・ログアウト
# ------------------------------------------------------------------
@router.get("/me")
async def get_me(active_user: User | None = Depends(get_active_user)):
    """現在アクティブなプロフィール（保護者本人 or 選択中のキッズ）を返す"""
    if active_user is None:
        return JSONResponse({"success": True, "logged_in": False})

    return JSONResponse(
        {
            "success": True,
            "logged_in": True,
            "user": {
                "id": active_user.id,
                "role": active_user.role,
                "display_name": active_user.display_name,
                "avatar_icon": active_user.avatar_icon,
            },
        }
    )


@router.post("/logout")
async def logout_endpoint(request: Request):
    """完全にログアウトする"""
    session_logout(request)
    return JSONResponse({"success": True})
