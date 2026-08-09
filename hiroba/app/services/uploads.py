"""
アップロード共通ユーティリティ（ひろば）

写真・お絵描き（Base64データURL）・ボイスメモなど、キッズが投稿する
メディアファイルの保存処理をルーター間で共通化する。
（app/routers/kids.py・app/routers/rooms.py の両方から利用する）
"""

import base64
import binascii
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.paths import UPLOAD_DIR

_DATA_URL_RE = re.compile(
    r"^data:image/(?P<ext>png|jpeg|jpg|gif|webp);base64,(?P<data>.+)$", re.DOTALL
)


def save_upload_file(file: UploadFile, prefix: str) -> tuple[str, Path]:
    """アップロードファイルを保存し、(公開URL, 実ファイルパス) を返す"""
    ext = "bin"
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()

    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    dest_path = UPLOAD_DIR / filename
    with dest_path.open("wb") as buffer:
        buffer.write(file.file.read())

    return f"/static/uploads/{filename}", dest_path


def save_base64_image(data_url: str, prefix: str) -> tuple[str, Path]:
    """お絵描きCanvasのdata URL（Base64）を画像として保存する"""
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise HTTPException(
            status_code=400, detail="おえかきデータの形式が正しくありません"
        )

    ext = match.group("ext")
    raw = match.group("data")
    try:
        binary = base64.b64decode(raw)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=400, detail="おえかきデータの読み込みに失敗しました"
        )

    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    dest_path = UPLOAD_DIR / filename
    with dest_path.open("wb") as buffer:
        buffer.write(binary)

    return f"/static/uploads/{filename}", dest_path
