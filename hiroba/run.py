"""
ひろば 起動スクリプト

注意：
ルートディレクトリ（Engawa）にも「縁側」用の `app` パッケージが存在するため、
Engawaのルートディレクトリで `uvicorn app.main:app` を実行すると、
Pythonが先に見つけた縁側側の `app` パッケージを読み込んでしまい、
「ひろば」ではなく「縁側」が起動してしまう場合がある。

このスクリプトは `hiroba/` ディレクトリを sys.path の先頭に明示的に
挿入してから起動するため、どのディレクトリから実行しても
確実に「ひろば」の app パッケージが読み込まれる。

使い方:
    cd hiroba
    python run.py
"""

import sys
from pathlib import Path

# hiroba/ ディレクトリ自体を sys.path の最優先に挿入する
HIROBA_DIR = Path(__file__).resolve().parent
if str(HIROBA_DIR) in sys.path:
    sys.path.remove(str(HIROBA_DIR))
sys.path.insert(0, str(HIROBA_DIR))

# すでに（誤って）縁側側の app / app.main 等がインポート済みの場合は
# キャッシュを破棄して、ひろば側を確実に再読み込みする
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
