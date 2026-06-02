#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py  -  yt-dlp GUI build script
Usage:
  python build.py
  python build.py --skip-deps
  python build.py --skip-ffmpeg
  python build.py --skip-build
"""

import sys
import os
import shutil
import zipfile
import argparse
import subprocess
import urllib.request
import urllib.error
import ssl
import platform
import time
from pathlib import Path

# ── Settings ──────────────────────────────────────────────────────────────────
APP_NAME    = "ytdlp_gui"
APP_VERSION = "1.1.0"
SCRIPT_DIR  = Path(__file__).resolve().parent
DIST_DIR    = SCRIPT_DIR / "dist" / APP_NAME
BUILD_DIR   = SCRIPT_DIR / "build"
FFMPEG_DIR  = DIST_DIR / "ffmpeg"
IS_WIN      = platform.system() == "Windows"

# GitHub download URLs
# FFmpeg: gpl static build (単体 exe、DLL 不要)
FFMPEG_WIN_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)
FFMPEG_WIN_URL_FALLBACK = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-lgpl.zip"
)
YTDLP_WIN_URL = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
)

# ── Output helpers ────────────────────────────────────────────────────────────
def info(msg):  print(f"  [OK]  {msg}")
def warn(msg):  print(f"  [!!]  {msg}")
def err(msg):   print(f"  [ER]  {msg}")
def step(msg):  print(f"\n{'='*60}\n  >> {msg}\n{'='*60}")
def head(msg):  print(f"\n{'='*60}\n     {msg}\n{'='*60}")

# ── Subprocess helper ─────────────────────────────────────────────────────────
def run(cmd, check=True, **kw):
    print("  $", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=check, **kw)

# ── Robust downloader ─────────────────────────────────────────────────────────
def download_file(url: str, dest: Path, label: str = "",
                  retries: int = 3) -> bool:
    """
    GitHub リリースに対応したダウンロード関数。
    - User-Agent を設定（未設定だと GitHub に弾かれる）
    - リダイレクトを追跡
    - SSL エラー時は検証をスキップして再試行
    - 最大 retries 回リトライ
    """
    label = label or dest.name
    dest.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }

    for attempt in range(1, retries + 1):
        print(f"  Downloading: {label}  (attempt {attempt}/{retries})")
        print(f"  URL: {url}")
        try:
            # SSL コンテキスト（1回目は検証あり、2回目以降はスキップ）
            if attempt == 1:
                ctx = ssl.create_default_context()
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode    = ssl.CERT_NONE

            req  = urllib.request.Request(url, headers=headers)
            tmp  = Path(str(dest) + ".tmp")

            with urllib.request.urlopen(req, context=ctx,
                                        timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                done  = 0
                chunk = 1024 * 256  # 256 KB chunks

                with open(tmp, "wb") as f:
                    while True:
                        data = resp.read(chunk)
                        if not data:
                            break
                        f.write(data)
                        done += len(data)
                        if total:
                            pct = done / total * 100
                            mb  = done  / 1024 / 1024
                            tot = total / 1024 / 1024
                            print(f"\r  {pct:5.1f}%  {mb:.1f}/{tot:.1f} MB",
                                  end="", flush=True)

            print()  # newline after progress
            tmp.rename(dest)
            info(f"Downloaded: {dest.name}  ({done/1024/1024:.1f} MB)")
            return True

        except urllib.error.HTTPError as e:
            print()
            err(f"HTTP {e.code}: {e.reason}")
            if e.code in (403, 404):
                break  # retry won't help
        except Exception as e:
            print()
            err(f"Error (attempt {attempt}): {type(e).__name__}: {e}")

        if attempt < retries:
            wait = 3 * attempt
            print(f"  Waiting {wait}s before retry...")
            time.sleep(wait)
        # clean up partial file
        if Path(str(dest) + ".tmp").exists():
            Path(str(dest) + ".tmp").unlink(missing_ok=True)

    return False


def check_python_version():
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 9):
        err(f"Python 3.9+ required (current: {major}.{minor})")
        sys.exit(1)
    info(f"Python {major}.{minor} OK")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1: Install Python dependencies
# ══════════════════════════════════════════════════════════════════════════════

def install_deps():
    step("STEP 1: Install Python dependencies")
    req = SCRIPT_DIR / "requirements.txt"
    if not req.exists():
        warn("requirements.txt not found - skipping")
        return
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", str(req)])
    info("Dependencies installed")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2: Download FFmpeg
# ══════════════════════════════════════════════════════════════════════════════

def download_ffmpeg():
    step("STEP 2: Download FFmpeg")

    if not IS_WIN:
        _guide_ffmpeg_unix()
        return

    # すでに配置済みならスキップ
    if (FFMPEG_DIR / "ffmpeg.exe").exists():
        info("ffmpeg.exe already exists - skipping download")
        return

    zip_path = BUILD_DIR / "ffmpeg_tmp.zip"
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # まずメインURLを試し、失敗したらフォールバックURLを試す
    ok = download_file(FFMPEG_WIN_URL, zip_path, "FFmpeg (gpl static)")
    if not ok:
        warn("Primary URL failed. Trying fallback URL...")
        ok = download_file(FFMPEG_WIN_URL_FALLBACK, zip_path,
                           "FFmpeg (lgpl fallback)")

    if not ok:
        warn("FFmpeg download failed.")
        warn("Please manually place ffmpeg.exe and ffprobe.exe into:")
        warn(f"  {FFMPEG_DIR}")
        return

    _extract_ffmpeg(zip_path)


def _extract_ffmpeg(zip_path: Path):
    print("  Extracting FFmpeg...")
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    found = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                fname = Path(member).name
                if fname in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                    data = zf.read(member)
                    dest = FFMPEG_DIR / fname
                    dest.write_bytes(data)
                    found.append(fname)
                    info(f"Extracted: {fname} ({len(data)/1024/1024:.1f} MB)")
    finally:
        zip_path.unlink(missing_ok=True)

    if "ffmpeg.exe" in found:
        try:
            result = subprocess.run(
                [str(FFMPEG_DIR / "ffmpeg.exe"), "-version"],
                capture_output=True, text=True, timeout=10)
            ver = result.stdout.splitlines()[0] if result.stdout else "?"
            info(f"FFmpeg version: {ver[:70]}")
        except Exception:
            pass
    else:
        warn("ffmpeg.exe not found in archive.")
        warn(f"Please place it manually in: {FFMPEG_DIR}")


def _guide_ffmpeg_unix():
    if platform.system() == "Darwin":
        warn("macOS: install FFmpeg with:  brew install ffmpeg")
    else:
        warn("Linux: install FFmpeg with:  sudo apt install ffmpeg")
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("ffmpeg", "ffprobe"):
        src = shutil.which(name)
        if src:
            shutil.copy2(src, FFMPEG_DIR / name)
            info(f"Copied system {name} -> ffmpeg/{name}")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3: Build EXE with PyInstaller
# ══════════════════════════════════════════════════════════════════════════════

def build_exe():
    step("STEP 3: Build EXE with PyInstaller")

    spec = SCRIPT_DIR / "ytdlp_gui.spec"
    if not spec.exists():
        err("ytdlp_gui.spec not found")
        sys.exit(1)

    # Back up ffmpeg before clean build
    ffmpeg_backup = None
    if FFMPEG_DIR.exists():
        ffmpeg_backup = BUILD_DIR / "ffmpeg_backup"
        if ffmpeg_backup.exists():
            shutil.rmtree(ffmpeg_backup)
        shutil.copytree(FFMPEG_DIR, ffmpeg_backup)
        info("FFmpeg backed up")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
        info("Cleaned dist/ytdlp_gui")

    run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
         str(spec)])

    # Restore ffmpeg
    if ffmpeg_backup and ffmpeg_backup.exists():
        FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
        for f in ffmpeg_backup.iterdir():
            shutil.copy2(f, FFMPEG_DIR / f.name)
        shutil.rmtree(ffmpeg_backup)
        info("FFmpeg restored to dist/ytdlp_gui/ffmpeg/")

    info("PyInstaller build complete")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4: Download yt-dlp.exe and finalize
# ══════════════════════════════════════════════════════════════════════════════

def finalize():
    step("STEP 4: Download yt-dlp.exe and finalize")

    if not DIST_DIR.exists():
        err("dist/ytdlp_gui not found - build may have failed")
        return

    # EXE 確認
    exe_path = DIST_DIR / ("ytdlp_gui.exe" if IS_WIN else "ytdlp_gui")
    if exe_path.exists():
        size = exe_path.stat().st_size / 1024 / 1024
        info(f"Main EXE: {exe_path.name}  ({size:.1f} MB)")
    else:
        warn(f"Main EXE not found: {exe_path}")

    # yt-dlp.exe ダウンロード
    if IS_WIN:
        ytdlp_dest = DIST_DIR / "yt-dlp.exe"
        if ytdlp_dest.exists():
            size = ytdlp_dest.stat().st_size / 1024 / 1024
            info(f"yt-dlp.exe already exists ({size:.1f} MB) - skipping")
        else:
            ok = download_file(YTDLP_WIN_URL, ytdlp_dest, "yt-dlp.exe")
            if ok:
                info(f"yt-dlp.exe placed in {DIST_DIR.name}/")
            else:
                warn("yt-dlp.exe download failed.")
                warn("Download manually from:")
                warn("  https://github.com/yt-dlp/yt-dlp/releases")
                warn(f"  and place it in: {DIST_DIR}")

    # FFmpeg 確認
    ffmpeg_exe = FFMPEG_DIR / ("ffmpeg.exe" if IS_WIN else "ffmpeg")
    if ffmpeg_exe.exists():
        info(f"FFmpeg: OK ({ffmpeg_exe.relative_to(SCRIPT_DIR)})")
    else:
        warn(f"FFmpeg not found at: {ffmpeg_exe}")

    # README コピー
    for readme in ("README.md", "README_ytdlp_gui.md", "README.txt"):
        src = SCRIPT_DIR / readme
        if src.exists():
            shutil.copy2(src, DIST_DIR / readme)
            info(f"Copied: {readme}")
            break

    # 配布物の内容一覧
    print("\n  --- Distribution contents ---")
    if DIST_DIR.exists():
        total_size = 0
        for f in sorted(DIST_DIR.rglob("*")):
            if f.is_file() and f.parent == DIST_DIR:
                sz = f.stat().st_size / 1024 / 1024
                total_size += sz
                print(f"    {f.name:<30} {sz:6.1f} MB")
        print(f"    {'(total top-level)':<30} "
              f"{total_size:6.1f} MB")


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="yt-dlp GUI build script")
    parser.add_argument("--skip-deps",   action="store_true",
                        help="Skip pip install")
    parser.add_argument("--skip-ffmpeg", action="store_true",
                        help="Skip FFmpeg download")
    parser.add_argument("--skip-build",  action="store_true",
                        help="Skip PyInstaller build")
    args = parser.parse_args()

    head(f"yt-dlp GUI v{APP_VERSION}  -  Build Script")
    print(f"  OS    : {platform.system()} {platform.architecture()[0]}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Dir   : {SCRIPT_DIR}")

    t0 = time.time()
    check_python_version()

    if not args.skip_deps:
        install_deps()
    else:
        warn("--skip-deps: skipping pip install")

    if not args.skip_ffmpeg:
        download_ffmpeg()
    else:
        warn("--skip-ffmpeg: skipping FFmpeg download")

    if not args.skip_build:
        build_exe()
    else:
        warn("--skip-build: skipping PyInstaller")

    finalize()

    elapsed = time.time() - t0
    head(f"Build complete  ({elapsed:.0f}s)")
    print(f"\n  Output: dist/{APP_NAME}/\n")


if __name__ == "__main__":
    main()
