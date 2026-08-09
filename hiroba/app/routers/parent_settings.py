"""
保護者向け設定APIルーター（ひろば）

- LINE通知のオン/オフ切り替え
- LINEアカウント連携状態の確認・（開発モード用の）簡易連携／連携解除

本番でLINE Messaging API等と連携する場合は、実際のOAuthコールバックで
line_user_id を保存する処理に置き換える想定。開発モードでは、実際の
LINE認証は行わず、ダミーのLINE IDを手動で入力して「連携ずみ」の状態を
再現できる簡易フローのみを提供する。

アクセス制御:
- すべてのエンドポイントは、ログイン中の保護者本人の情報のみを
  取得・更新できる（他の保護者のデータには一切アクセスできない）。
"""

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse

from app.auth import get_current_parent
from app.database import get_db
from app.models import User
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/parent", tags=["parent-settings"])


def _serialize_notification_settings(parent: User) -> dict:
    return {
        "line_notify_enabled": bool(parent.line_notify_enabled),
        "line_linked": bool(parent.line_user_id),
        # LINE IDはそのまま全部見せず、末尾のみ見せる（プライバシー配慮）
        "line_user_id_masked": (
            ("•" * 4) + parent.line_user_id[-4:]
            if parent.line_user_id and len(parent.line_user_id) >= 4
            else (parent.line_user_id or None)
        ),
    }


@router.get("/notifications")
async def get_notification_settings(
    parent: User | None = Depends(get_current_parent),
):
    """ログイン中の保護者本人のLINE通知設定・連携状態を取得する"""
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    return JSONResponse({"success": True, "settings": _serialize_notification_settings(parent)})


@router.post("/notifications/toggle")
async def toggle_notifications(
    enabled: str = Form(...),  # "true" / "false"
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """LINE通知のオン/オフを切り替える（保護者本人のみ操作可能）"""
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    parent.line_notify_enabled = str(enabled).strip().lower() in ("true", "1", "on", "yes")
    db.commit()
    db.refresh(parent)

    return JSONResponse({"success": True, "settings": _serialize_notification_settings(parent)})


@router.post("/notifications/link")
async def link_line_account(
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """LINEアカウントを連携する（開発モード：ダミーのLINE IDを発行するだけの簡易実装）

    本番では、ここでLINEログイン（OAuth）のコールバックを受け取り、
    実際のLINE user id を保存する処理に置き換える。
    """
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    if not parent.line_user_id:
        parent.line_user_id = f"dev-line-{uuid.uuid4().hex[:12]}"
        db.commit()
        db.refresh(parent)

    return JSONResponse({"success": True, "settings": _serialize_notification_settings(parent)})


@router.post("/notifications/unlink")
async def unlink_line_account(
    parent: User | None = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    """LINEアカウントの連携を解除する（保護者本人のみ操作可能）"""
    if parent is None:
        raise HTTPException(status_code=401, detail="保護者としてログインしてください")

    parent.line_user_id = None
    db.commit()
    db.refresh(parent)

    return JSONResponse({"success": True, "settings": _serialize_notification_settings(parent)})
