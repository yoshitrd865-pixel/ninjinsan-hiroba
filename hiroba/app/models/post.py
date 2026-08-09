"""
Post モデル（ひろば）

キッズが文字入力なしで投稿できるように、以下の要素で構成される。
- 写真 or お絵描きのURL
- ボイスメモのURL（音声で気持ちを伝える）
- 気分スタンプ（絵文字などの簡単な選択）
- whisper_text : ボイスメモを OpenAI Whisper 等で音声認識した
  テキスト（保護者向け表示や検索・モデレーション用。キッズには非表示）

削除について:
- 投稿本人（キッズ）またはその保護者は投稿を削除できる。
- 「理由を表示せず静かに消す」設計方針に従い、実際にレコードを
  Deleteするのではなく is_hidden=True にするだけで、タイムライン等の
  一覧クエリから除外する（第三者には「もともとなかった」ように見える）。
"""

import datetime

from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Post(Base):
    """写真/お絵描き・ボイスメモ・気分スタンプの投稿"""

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 写真アップロード or お絵描き機能で保存されたURL（どちらか、または両方）
    photo_url = Column(String(255), nullable=True)
    drawing_url = Column(String(255), nullable=True)

    # ボイスメモ（録音した音声ファイルのURL）
    voice_memo_url = Column(String(255), nullable=True)

    # 気分スタンプ（例: "😆", "happy" など。タップだけで選べる）
    mood_stamp = Column(String(20), nullable=True)

    # ひとことメッセージ（「おへや」の“つくる”タブなど、文字が書けるキッズ向けの任意入力）
    message = Column(Text, nullable=True)

    # 「おへや」内に投稿された場合の room_id（NULL=グローバルな「ひろば」への投稿）
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True, index=True)


    # Whisper（音声認識）でボイスメモをテキスト化した内容。
    # キッズ自身は文字を読み書きしないため、保護者確認・検索・モデレーション用途。
    whisper_text = Column(Text, nullable=True)

    # 本人またはその保護者が削除した投稿。Deleteではなくこのフラグを立てて
    # 静かに非表示にする（「削除されました」等の理由メッセージは一切出さない）。
    is_hidden = Column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", back_populates="posts")
    reactions = relationship(
        "Reaction", back_populates="post", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Post id={self.id} user_id={self.user_id} mood={self.mood_stamp!r}>"
