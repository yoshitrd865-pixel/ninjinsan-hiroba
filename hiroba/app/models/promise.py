"""
Promise / PromisePost モデル（ひろば）

キッズ同士の「あそぶ お約束」は、以下の2段構成で管理する。

- PromisePost : キッズが「いつ・いつごろ・どこで あそびたい」を
  タップ選択だけで投稿する「あそびたい」カード（文字入力は一切ない）。
  掲示板（おちゃのま）に表示されるが、【いいね数・応募人数・応募者一覧】
  など、誰が応募したか分かる情報は一切保持・公開しない。

- Promise : 誰か（B）が「いっしょにあそびたい！」をタップした瞬間に
  作成される、A・B間の実際のお約束レコード。双方の保護者がタップ選択
  だけで確認・承認するまで「成立」しない
  （sender側・receiver側それぞれの保護者が個別に承認する）。

第三者に人間関係を見せないための設計:
- PromisePost が成立(matched)すると、掲示板からは静かに非表示になる
  （Deleteではなく status="matched" にするのみ。第三者には
  「投稿が消えた」ようにしか見えない）。
- Promise の状態（確認中／成立／キャンセル）は、当事者
  （sender・receiver の家庭）以外には一切見せない
  （APIレスポンスの絞り込みで保証する。routers/promises.py 参照）。

status の遷移:
- "pending_parents" : 応募直後。両方またはどちらかの保護者がまだ未回答
- "approved"         : 両方の保護者が承認した（約束成立！）
- "cancelled"         : どちらかの保護者が「今回はむずかしい」を選んだ、
                         または成立後に保護者がキャンセルした
"""

import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base

# 時間帯: "morning"（🌞 ごぜん） / "afternoon"（🌤 ごご）
TIME_FRAMES = ("morning", "afternoon")

# 場所タイプ: 🏠 うち / 🏡 あいてのいえ / 🏫 がっこう・こうてい / 🎤 そのほか（ボイスメモ）
LOCATION_TYPES = ("home_my", "home_friend", "school", "other")

# PromisePost（あそびたい投稿）の状態
POST_STATUSES = ("open", "matched", "cancelled")

# Promise（お約束）の状態
PROMISE_STATUSES = ("pending_parents", "approved", "cancelled")


class PromisePost(Base):
    """キッズの「あそびたい」投稿カード（掲示板に匿名性を保って表示される）"""

    __tablename__ = "promise_posts"

    id = Column(Integer, primary_key=True, index=True)
    kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 📅 いつ？（必須・過去日は選択不可）
    date = Column(Date, nullable=False, index=True)
    # 🌞 ごぜん / 🌤 ごご（詳しい時間は入力させない）
    time_frame = Column(String(20), nullable=False)
    # 🏠 うち / 🏡 あいてのいえ / 🏫 がっこう・こうてい / 🎤 そのほか
    location_type = Column(String(20), nullable=False)
    # 「そのほか」選択時のみ使うボイスメモURL（既存の録音機能を活用）
    location_audio_url = Column(String(255), nullable=True)

    # "open" / "matched" / "cancelled"
    status = Column(String(20), nullable=False, default="open", index=True)

    # 成立(matched)した際に、どのPromiseで成立したかを記録する
    matched_promise_id = Column(Integer, ForeignKey("promises.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    kid = relationship("User", foreign_keys=[kid_id])
    applications = relationship(
        "Promise",
        back_populates="post",
        foreign_keys="Promise.post_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PromisePost id={self.id} kid_id={self.kid_id} status={self.status!r}>"


class Promise(Base):
    """キッズ同士の実際の「あそぶ お約束」（双方の保護者承認フロー）"""

    __tablename__ = "promises"

    id = Column(Integer, primary_key=True, index=True)

    post_id = Column(Integer, ForeignKey("promise_posts.id"), nullable=False, index=True)

    # 投稿した側（A） / 「いっしょにあそびたい！」をタップした側（B）
    sender_kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_kid_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 日付（必須）
    date = Column(Date, nullable=False, index=True)
    # 時間帯 "morning" / "afternoon"
    time_frame = Column(String(20), nullable=False)
    # 詳しい時間（例: "14:00〜16:00"）。保護者の「🕐 じかんを決める」で設定される
    detailed_time = Column(String(50), nullable=True)
    # 場所タイプ
    location_type = Column(String(20), nullable=False)
    # 「そのほか」時のボイスメモURL
    location_audio_url = Column(String(255), nullable=True)

    # "pending_parents" / "approved" / "cancelled"
    status = Column(String(20), nullable=False, default="pending_parents", index=True)

    # 双方の保護者それぞれの承認状態
    sender_parent_approved = Column(Boolean, nullable=False, default=False)
    receiver_parent_approved = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    post = relationship("PromisePost", back_populates="applications", foreign_keys=[post_id])
    sender_kid = relationship("User", foreign_keys=[sender_kid_id])
    receiver_kid = relationship("User", foreign_keys=[receiver_kid_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Promise id={self.id} status={self.status!r}>"
