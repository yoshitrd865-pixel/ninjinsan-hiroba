"""
リアクションAPI（ひろば）

文字入力の代わりに、ワンタップで送れる4種類のポジティブなリアクション。
- "yabai"      : やばい！
- "omoshiroi"  : おもしろい！
- "sugoi"      : すごい！
- "suteki"     : すてき！

キッズが何度タップしても楽しいように「連打OK・カウントアップ方式」を
採用している（タップごとに新しいレコードを追加してカウントを増やす）。
"""

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import get_active_user
from app.database import get_db
from app.models import Post, Reaction, User
from app.models.reaction import REACTION_LABELS

router = APIRouter(prefix="/api/posts", tags=["reactions"])


@router.post("/{post_id}/react")
async def react_to_post(
    post_id: int,
    reaction_type: str = Form(...),
    user: User | None = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """投稿に4種類のリアクションのいずれかを送る（連打OK・カウントアップ方式）"""
    if user is None:
        raise HTTPException(status_code=401, detail="ログインしてください")

    if reaction_type not in REACTION_LABELS:
        raise HTTPException(status_code=400, detail="不正なリアクション種別です")

    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="投稿が見つかりません")

    reaction = Reaction(
        post_id=post_id, user_id=user.id, reaction_type=reaction_type
    )
    db.add(reaction)
    db.commit()

    counts = {
        rt: (
            db.query(Reaction)
            .filter(Reaction.post_id == post_id, Reaction.reaction_type == rt)
            .count()
        )
        for rt in REACTION_LABELS
    }

    return JSONResponse(
        {
            "success": True,
            "post_id": post_id,
            "reaction_type": reaction_type,
            "reaction_label": REACTION_LABELS[reaction_type],
            "reactions": counts,
            "reaction_total": sum(counts.values()),
        }
    )
