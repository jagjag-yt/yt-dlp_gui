# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
#  ytdlp_gui.spec  –  PyInstaller ビルド設定
#  生成コマンド: pyinstaller ytdlp_gui.spec
# =============================================================================

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ── tkinterdnd2 は除外（Windows/.soビルド混入問題を回避）────────────────
tkdnd2_binaries = []
tkdnd2_datas    = []

# ── yt_dlp の全エクストラクタを収集 ──────────────────────────────────────
yt_dlp_hiddenimports = collect_submodules("yt_dlp")
yt_dlp_datas         = collect_data_files("yt_dlp")

# ── 全 hiddenimports ─────────────────────────────────────────────────────
hidden = [
    # yt-dlp
    *yt_dlp_hiddenimports,
    "yt_dlp.utils",
    "yt_dlp.extractor",
    "yt_dlp.postprocessor",
    # tkinter
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    # 標準ライブラリ（念のため明示）
    "logging",
    "json",
    "threading",
    "queue",
    "pathlib",
    "dataclasses",
    "enum",
    # ネットワーク関連（yt-dlp が内部で使用）
    "urllib",
    "urllib.request",
    "urllib.parse",
    "http.cookiejar",
    "http.client",
    "ssl",
    "certifi",
    "websockets",
    "mutagen",
    "mutagen.mp3",
    "mutagen.mp4",
    "mutagen.id3",
    "mutagen.flac",
    "mutagen.wave",
    "Crypto",
    "Crypto.Cipher",
    "Crypto.Cipher.AES",
]

# ── datas（データファイル）───────────────────────────────────────────────
datas = [
    *yt_dlp_datas,
    *tkdnd2_datas,
    # certifi の CA 証明書
    (str(Path(__import__("certifi").where())), "certifi"),
]

# ── binaries ─────────────────────────────────────────────────────────────
binaries = [
    *tkdnd2_binaries,
]

block_cipher = None

a = Analysis(
    ["ytdlp_gui.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "PyQt5",
        "PyQt6",
        "wx",
        "gi",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,           # onedir モード推奨（onefile は起動が遅い）
    name="ytdlp_gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # UPX 圧縮は誤検知の原因になるためオフ
    console=False,                   # コンソールウィンドウを非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",               # アイコンを用意する場合はコメントを外す
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ytdlp_gui",
)
