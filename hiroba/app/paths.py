"""
共通パス設定（ひろば）

main.py / routers / services 全体で共有するディレクトリパスを定義する。
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# 写真・お絵描き画像・ボイスメモの保存先
UPLOAD_DIR = STATIC_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
