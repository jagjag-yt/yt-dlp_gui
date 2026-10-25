#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║         yt-dlp GUI v1.4.1  –  完全版 動画ダウンローダー          ║
║  pip install yt-dlp                                          ║
╚══════════════════════════════════════════════════════════════╝
"""

# ─────────────────────────────────────────────────────────────
#  標準ライブラリ
# ─────────────────────────────────────────────────────────────
import sys, os, re, json, time, threading, queue, logging, shutil, subprocess
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

# ─────────────────────────────────────────────────────────────
#  tkinter
# ─────────────────────────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

# ─────────────────────────────────────────────────────────────
#  オプション依存
# ─────────────────────────────────────────────────────────────
try:
    import yt_dlp
    YT_DLP_OK = True
except ImportError:
    YT_DLP_OK = False

# Pillow（サムネイルプレビュー用・任意）
try:
    from PIL import Image, ImageTk
    import io as _io
    PIL_OK = True
except ImportError:
    PIL_OK = False

# pycryptodomex（暗号化保存用・任意）
try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Protocol.KDF import PBKDF2
    from Cryptodome.Hash import SHA256
    from Cryptodome.Random import get_random_bytes
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False

# tkinterdnd2 は Windows EXE ビルド時に .so (Linux用) が混入する問題があるため
# 依存を除去し、D&D は無効化（URL貼り付け・クリップボード監視で代替）
DND_OK = False

IS_WIN = sys.platform == "win32"

# ─────────────────────────────────────────────────────────────
#  定数
# ─────────────────────────────────────────────────────────────
APP_VERSION = "1.4.1"
APP_TITLE   = f"yt-dlp GUI v{APP_VERSION}"
CFG_PATH    = Path.home() / ".ytdlp_gui_config.json"

# ── FFmpeg / yt-dlp パス解決 ───────────────────────────────────────
def _get_app_dir() -> Path:
    """
    EXE として実行中なら ytdlp_gui.exe が置かれたフォルダを返す。
    通常の Python 実行時はスクリプトのフォルダを返す。

    ※ sys._MEIPASS は PyInstaller が一時展開する内部フォルダであり、
       ffmpeg/ や yt-dlp.exe はそこではなく EXE と同じフォルダに置かれる。
    """
    if getattr(sys, "frozen", False):       # PyInstaller EXE
        return Path(sys.executable).parent  # EXE と同じフォルダ
    return Path(__file__).resolve().parent  # 開発時はスクリプトの場所

# BUNDLE_DIR は後方互換のためエイリアスとして残す
BUNDLE_DIR = _get_app_dir()
APP_DIR    = BUNDLE_DIR

def _setup_ffmpeg_path():
    """ffmpeg/ フォルダを PATH の先頭に追加する"""
    ffmpeg_path = APP_DIR / "ffmpeg"
    if ffmpeg_path.exists():
        os.environ["PATH"] = (str(ffmpeg_path)
                              + os.pathsep
                              + os.environ.get("PATH", ""))
        os.environ["FFMPEG_LOCATION"] = str(ffmpeg_path)

_setup_ffmpeg_path()

VIDEO_AUTO  = "自動（最高画質）"
VIDEO_FMTS  = [VIDEO_AUTO, "mp4", "mkv", "webm"]
AUDIO_FMTS  = ["mp3", "m4a", "wav", "flac"]
QUALITY_MAP = {
    "最高品質":   "",
    "1080p":    "[height<=1080]",
    "720p":     "[height<=720]",
    "480p":     "[height<=480]",
    "360p":     "[height<=360]",
}
POST_ACTIONS = ["何もしない", "フォルダを開く", "PCをスリープ", "PCをシャットダウン"]
# yt-dlp がサムネイル埋め込みに対応している形式
THUMB_VIDEO_FMTS = ("mp4", "mkv")
THUMB_AUDIO_FMTS = ("mp3", "m4a", "flac")

# ══════════════════════════════════════════════════════════════
#  デザイントークン（design_handoff README 準拠）
# ══════════════════════════════════════════════════════════════

# 両テーマ共通の固定色
ACCENT    = "#0078d4"   # Windows 11 システムブルー
ACCENT_H  = "#1688e0"   # ホバー
ACCENT_P  = "#005ea6"   # 押下
SUCCESS_C = "#4ec9a0"
WARNING_C = "#f0b429"
ERROR_C   = "#e06b6b"

DARK_THEME = dict(
    bg1="#1c1c1c",      # ウィンドウ/ページ
    bg2="#252525",      # パネル/カード
    bg3="#2e2e2e",      # 入力欄
    bg4="#383838",      # ボーダー/トラック/ホバー
    border="#383838",
    text="#f0f0f0",
    text2="#a8a8a8",
    text3="#666666",
)
LIGHT_THEME = dict(
    bg1="#f3f3f3",
    bg2="#ffffff",
    bg3="#e9e9e9",
    bg4="#d9d9d9",
    border="#d9d9d9",
    text="#1b1b1b",
    text2="#5c5c5c",
    text3="#8a8a8a",
)

# ── フォント（Segoe UI / Yu Gothic UI / Meiryo スタック相当）────
FONT_FAMILY = "Yu Gothic UI"
MONO_FAMILY = "Consolas"
_UI_SCALE   = 1.0

def set_ui_scale(scale: float):
    global _UI_SCALE
    _UI_SCALE = max(0.5, scale)

def P(px: int) -> int:
    """デザイン上の px を実ピクセルへ（DPIスケール対応）"""
    return max(1, int(round(px * _UI_SCALE)))

def F(px: int, bold: bool = False):
    """px 指定フォント（tkinter は負値サイズ=ピクセル指定）"""
    size = -P(px)
    return (FONT_FAMILY, size, "bold") if bold else (FONT_FAMILY, size)

def FMONO(px: int):
    return (MONO_FAMILY, -P(px))

def blend(c1: str, c2: str, t: float) -> str:
    """c1 を c2 に割合 t で混ぜた色（0.0=c1, 1.0=c2）"""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return "#%02x%02x%02x" % (
        round(r1 + (r2 - r1) * t),
        round(g1 + (g2 - g1) * t),
        round(b1 + (b2 - b1) * t))

# ══════════════════════════════════════════════════════════════
#  ヘルパー関数
# ══════════════════════════════════════════════════════════════

def fmt_speed(bps: float) -> str:
    if not bps: return ""
    if bps >= 1024**3: return f"{bps/1024**3:.2f} GB/s"
    if bps >= 1024**2: return f"{bps/1024**2:.1f} MB/s"
    if bps >= 1024:    return f"{bps/1024:.1f} KB/s"
    return f"{bps:.0f} B/s"

def fmt_eta(sec: float) -> str:
    if not sec: return ""
    sec = int(sec)
    if sec >= 3600: return f"{sec//3600}h{sec%3600//60}m{sec%60}s"
    if sec >= 60:   return f"{sec//60}m{sec%60}s"
    return f"{sec}s"

def fmt_size(b: float) -> str:
    if not b: return ""
    if b >= 1024**3: return f"{b/1024**3:.2f} GB"
    if b >= 1024**2: return f"{b/1024**2:.1f} MB"
    if b >= 1024:    return f"{b/1024:.1f} KB"
    return f"{b:.0f} B"

def parse_speed_mbps(speed: str) -> float:
    """'1.23MiB/s' などの文字列を MB/s 数値へ"""
    m = re.search(r'([\d.]+)\s*([KMG])i?B/s', speed or "", re.IGNORECASE)
    if not m:
        return 0.0
    val, unit = float(m.group(1)), m.group(2).upper()
    if unit == "K": return val / 1024
    if unit == "G": return val * 1024
    return val

def parse_eta_sec(eta: str) -> int:
    """'01:23' '1:02:03' '45s' などを秒へ"""
    eta = (eta or "").strip()
    if not eta:
        return 0
    if re.match(r'^\d+s$', eta):
        return int(eta[:-1])
    parts = eta.split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return 0
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec

def fmt_eta_colon(sec: int) -> str:
    if sec <= 0:
        return "—"
    m, s = divmod(int(sec), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def extract_urls(text: str) -> List[str]:
    pat = r'https?://[^\s　「」（）『』【】［］]+'
    return list(dict.fromkeys(re.findall(pat, text)))

# ── サブプロセス出力のデコード ─────────────────────────────
# yt-dlp.exe（PyInstaller製）は PYTHONUTF8 等の環境変数を無視して
# コンソールのコードページ（日本語Windowsでは CP932）で出力することが
# あるため、UTF-8 固定でデコードすると日本語タイトルが文字化けする。
# バイト列のまま受け取り、UTF-8 → ロケール既定 → CP932 の順に判別する。
import locale as _locale
_CONSOLE_ENCODINGS: List[str] = ["utf-8"]
for _enc in (_locale.getpreferredencoding(False), "cp932"):
    try:
        _enc_norm = _enc.lower() if _enc else ""
        if _enc_norm and _enc_norm not in _CONSOLE_ENCODINGS:
            _CONSOLE_ENCODINGS.append(_enc_norm)
    except Exception:
        pass

def decode_console_bytes(b: bytes) -> str:
    """サブプロセス出力の1行をエンコーディング自動判別でデコードする"""
    for enc in _CONSOLE_ENCODINGS:
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", errors="replace")

def desktop_notify(title: str, msg: str):
    """OSデスクトップ通知（Windows/macOS/Linux）"""
    try:
        if IS_WIN:
            import ctypes
            ctypes.windll.user32.MessageBeep(0)
        elif sys.platform == "darwin":
            # 引数はシェルを通さず渡す（タイトル中の引用符で壊れないように）
            subprocess.Popen(
                ["osascript", "-e",
                 "on run argv\n"
                 "display notification (item 2 of argv) "
                 "with title (item 1 of argv)\nend run",
                 title, msg])
        else:
            subprocess.Popen(["notify-send", title, msg],
                             stderr=subprocess.DEVNULL)
    except Exception:
        pass

def get_ytdlp_version() -> str:
    try:
        if YT_DLP_OK:
            return yt_dlp.version.__version__
    except Exception:
        pass
    return ""

# ══════════════════════════════════════════════════════════════
#  yt-dlp アップデート
# ══════════════════════════════════════════════════════════════

def resolve_ytdlp_cmd() -> Optional[List[str]]:
    """実際のダウンロードに使われる yt-dlp の起動コマンド（_build_cmd と同じ解決順）"""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).parent / "yt-dlp.exe"
        return [str(exe)] if exe.exists() else None
    w = shutil.which("yt-dlp")
    if w:
        return [w]
    if YT_DLP_OK:
        return [sys.executable, "-m", "yt_dlp"]
    return None

def fetch_local_ytdlp_version() -> str:
    """ダウンロードに使われる yt-dlp 本体の実バージョン（subprocess で取得）"""
    cmd = resolve_ytdlp_cmd()
    if cmd:
        try:
            out = subprocess.run(
                cmd + ["--version"],
                capture_output=True, timeout=30,
                creationflags=(subprocess.CREATE_NO_WINDOW if IS_WIN else 0))
            stdout = decode_console_bytes(out.stdout or b"")
            for line in reversed(stdout.strip().splitlines()):
                line = line.strip()
                if re.match(r'^\d{4}\.\d{1,2}\.\d{1,2}', line):
                    return line
        except Exception:
            pass
    return get_ytdlp_version()

def fetch_latest_ytdlp_version() -> str:
    """GitHub API から yt-dlp の最新リリースタグを取得する"""
    import urllib.request
    req = urllib.request.Request(
        "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
        headers={"User-Agent": f"ytdlp-gui/{APP_VERSION}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    return (data.get("tag_name") or "").strip()

def ver_tuple(v: str) -> tuple:
    """'2026.03.17' などを比較用タプルへ（解釈不能は空タプル）"""
    return tuple(int(n) for n in re.findall(r'\d+', v or "")[:4])

def ytdlp_update_targets() -> List[tuple]:
    """(説明, コマンド) のリスト。実行環境に応じた更新対象を返す"""
    targets: List[tuple] = []
    exe = APP_DIR / "yt-dlp.exe"
    if exe.exists():
        targets.append(("yt-dlp.exe を自己更新", [str(exe), "-U"]))
    if not getattr(sys, "frozen", False) and YT_DLP_OK:
        targets.append(("pip パッケージを更新",
                        [sys.executable, "-m", "pip", "install",
                         "--upgrade", "yt-dlp"]))
    return targets

# ══════════════════════════════════════════════════════════════
#  暗号化保存（AES-256-GCM / PBKDF2）
# ══════════════════════════════════════════════════════════════

ENC_MAGIC = b"YTDLPGUI_ENC1\n"
ENC_EXT   = ".enc"
_ENC_CHUNK = 1024 * 1024

def _derive_key(password: str, salt: bytes) -> bytes:
    return PBKDF2(password, salt, dkLen=32, count=200_000,
                  hmac_hash_module=SHA256)

def encrypt_file(path: Path, password: str) -> Path:
    """path を AES-256-GCM で暗号化し .enc を生成、元ファイルを削除する"""
    if not CRYPTO_OK:
        raise RuntimeError("pycryptodomex がインストールされていません")
    salt  = get_random_bytes(16)
    nonce = get_random_bytes(16)
    key   = _derive_key(password, salt)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    out = path.with_name(path.name + ENC_EXT)
    with open(path, "rb") as src, open(out, "wb") as dst:
        dst.write(ENC_MAGIC)
        dst.write(salt)
        dst.write(nonce)
        while True:
            chunk = src.read(_ENC_CHUNK)
            if not chunk:
                break
            dst.write(cipher.encrypt(chunk))
        dst.write(cipher.digest())   # 末尾16バイト = 認証タグ
    path.unlink()
    return out

def decrypt_file(path: Path, password: str) -> Path:
    """encrypt_file() で作成した .enc を復号する（.enc は残す）"""
    if not CRYPTO_OK:
        raise RuntimeError("pycryptodomex がインストールされていません")
    total = path.stat().st_size
    header = len(ENC_MAGIC) + 16 + 16
    if total < header + 16:
        raise ValueError("ファイルが壊れています")
    with open(path, "rb") as src:
        if src.read(len(ENC_MAGIC)) != ENC_MAGIC:
            raise ValueError("このアプリで暗号化されたファイルではありません")
        salt  = src.read(16)
        nonce = src.read(16)
        key   = _derive_key(password, salt)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        body = total - header - 16
        name = path.name[:-len(ENC_EXT)] if path.name.endswith(ENC_EXT) \
               else path.name + ".dec"
        out = path.with_name(name)
        if out.exists():
            stem, suf = os.path.splitext(name)
            out = path.with_name(f"{stem} (復号){suf}")
            n = 2
            while out.exists():
                out = path.with_name(f"{stem} (復号 {n}){suf}")
                n += 1
        with open(out, "wb") as dst:
            remain = body
            while remain > 0:
                chunk = src.read(min(_ENC_CHUNK, remain))
                if not chunk:
                    break
                remain -= len(chunk)
                dst.write(cipher.decrypt(chunk))
            tag = src.read(16)
            try:
                cipher.verify(tag)
            except ValueError:
                dst.close()
                out.unlink(missing_ok=True)
                raise ValueError("パスワードが違うかファイルが破損しています")
    return out

# ══════════════════════════════════════════════════════════════
#  CONFIG MODEL
# ══════════════════════════════════════════════════════════════

class Config:
    DEFAULTS: Dict[str, Any] = {
        "save_dir":        str(Path.home() / "Downloads"),
        "mode":            "video",
        "video_fmt":       VIDEO_AUTO,
        "audio_fmt":       "mp3",
        "quality":         "最高品質",
        "playlist":        False,
        "embed_thumbnail": True,
        "embed_subtitles": False,
        "auto_subtitles":  False,
        "ignore_errors":   True,
        "skip_existing":   False,
        "time_start":      "",
        "time_end":        "",
        "concurrent":      2,
        "retries":         3,
        "rate_limit":      "",
        "cookie_file":     "",
        "post_action":     "何もしない",
        "schedule_enable": False,
        "schedule_time":   "00:00",
        "encrypt_enable":  False,     # 暗号化保存（パスワードは保存しない）
        "onboarding_done": False,     # 初回オンボーディングバナー
        "dark_mode":       True,
        "recent_dirs":     [],
        "history":         [],
        "presets":         {},
        "meta_title":      "",
        "meta_artist":     "",
        "meta_album":      "",
    }

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            if CFG_PATH.exists():
                with open(CFG_PATH, encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
        except Exception as e:
            logging.warning(f"Config load error: {e}")

    def save(self):
        try:
            with open(CFG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.warning(f"Config save error: {e}")

    def __getitem__(self, k):
        return self.data.get(k, self.DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.data[k] = v

    def get(self, k, default=None):
        return self.data.get(k, default)

    def add_recent_dir(self, d: str):
        lst = [x for x in self.data.get("recent_dirs", []) if x != d]
        self.data["recent_dirs"] = ([d] + lst)[:10]

    def add_history(self, entry: dict):
        h = self.data.get("history", [])
        h.insert(0, entry)
        self.data["history"] = h[:200]

# ══════════════════════════════════════════════════════════════
#  TASK MODEL
# ══════════════════════════════════════════════════════════════

class TaskState(Enum):
    PENDING     = ("待機中",        "#8a8a8a")
    DOWNLOADING = ("ダウンロード中", ACCENT)
    CONVERTING  = ("変換中",        WARNING_C)
    DONE        = ("完了",          SUCCESS_C)
    ERROR       = ("エラー",        ERROR_C)
    CANCELLED   = ("中断",          "#888888")
    RETRYING    = ("リトライ",      WARNING_C)
    PAUSED      = ("一時停止",      WARNING_C)

    def label(self): return self.value[0]
    def color(self): return self.value[1]

@dataclass
class DownloadTask:
    url:           str
    idx:           int
    state:         TaskState = TaskState.PENDING
    progress:      float     = 0.0
    speed:         str       = ""
    eta:           str       = ""
    title:         str       = ""
    error:         str       = ""
    retry:         int       = 0
    dl_bytes:      float     = 0.0
    tot_bytes:     float     = 0.0
    rename:        str       = ""
    thumbnail_url: str       = ""
    duration:      str       = ""
    formats:       str       = ""
    out_files:     List[str] = field(default_factory=list)  # 完成ファイル（暗号化用）
    last_error:    str       = ""      # yt-dlp が出した最後の ERROR 行
    removed:       bool      = False   # キューから削除された（未開始なら実行しない）
    started:       Optional[datetime] = None
    finished:      Optional[datetime] = None

    def short_url(self, n=60) -> str:
        return self.url if len(self.url) <= n else self.url[:n-3]+"..."

    def display_name(self) -> str:
        return self.title if self.title else self.short_url()

# ══════════════════════════════════════════════════════════════
#  DOWNLOADER MODEL
# ══════════════════════════════════════════════════════════════

class Downloader:
    def __init__(self, config: Config, msg_q: queue.Queue):
        self.cfg   = config
        self.q     = msg_q
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._ydls: Dict[int, Any] = {}
        self._sem  = threading.Semaphore(max(1, config["concurrent"]))
        self.encrypt_password = ""   # 暗号化保存パスワード（保存されない）

    # ── 停止 ─────────────────────────────────────────────────
    def stop(self):
        self._stop.set()
        with self._lock:
            for proc in list(self._ydls.values()):
                try:
                    proc.kill()
                except Exception:
                    pass

    def reset(self):
        # 停止イベントは clear せず作り直す。停止前に起動したスレッド
        # （リトライ待ち・セマフォ待ち）は古いイベントを見続けるので、
        # 停止→即再試行しても同じタスクが二重にダウンロードされない。
        # 実行中プロセスの登録（_ydls）は消さない（停止で kill できるように）。
        self._stop = threading.Event()
        self._sem = threading.Semaphore(max(1, self.cfg["concurrent"]))

    # ── yt-dlp コマンドライン引数生成 ──────────────────────
    def _build_cmd(self, task: DownloadTask) -> List[str]:
        """yt-dlp を subprocess で直接呼ぶためのコマンドを組み立てる"""
        cfg      = self.cfg
        save_dir = cfg["save_dir"]
        mode     = cfg["mode"]

        # ── yt-dlp 実行ファイルのパス解決 ────────────────────
        # PyInstaller EXE の場合 sys.executable は ytdlp_gui.exe 自身なので
        # sys.executable -m yt_dlp を呼ぶとアプリが2重起動してしまう。
        # そのため EXE 時は同梱の yt-dlp.exe を、開発時は python -m yt_dlp を使う。
        cmd_base: List[str] = []

        if getattr(sys, "frozen", False):
            exe_dir       = Path(sys.executable).parent
            ytdlp_bundled = exe_dir / "yt-dlp.exe"
            if ytdlp_bundled.exists():
                cmd_base = [str(ytdlp_bundled)]
            else:
                raise RuntimeError(
                    "yt-dlp.exe が見つかりません。\n"
                    f"{exe_dir} に yt-dlp.exe を配置してください。\n"
                    "https://github.com/yt-dlp/yt-dlp/releases から取得できます。")
        else:
            ytdlp_exe = shutil.which("yt-dlp")
            if ytdlp_exe:
                cmd_base = [ytdlp_exe]
            else:
                cmd_base = [sys.executable, "-m", "yt_dlp"]

        # ── FFmpeg パス解決 ───────────────────────────────
        ffmpeg_dir = APP_DIR / "ffmpeg"
        if not ffmpeg_dir.exists():
            ff = shutil.which("ffmpeg")
            if ff:
                ffmpeg_dir = Path(ff).parent

        cmd: List[str] = [*cmd_base]

        # ── 出力テンプレート ──────────────────────────────
        rename = (task.rename or "").strip()
        if rename:
            # 【セキュリティ】Windowsの予約デバイス名・先頭末尾スペース/ドットも除去
            safe = re.sub(r'[\\/:*?"<>|]', "_", rename)
            safe = safe.strip(". ")
            WIN_RESERVED = re.compile(
                r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', re.IGNORECASE)
            if WIN_RESERVED.match(safe):
                safe = "_" + safe
            if not safe:
                safe = "download"
            outtmpl = os.path.join(save_dir, f"{safe}.%(ext)s")
        else:
            outtmpl = os.path.join(save_dir, "%(title).200s.%(ext)s")
        cmd += ["-o", outtmpl]

        # ── FFmpeg パス ───────────────────────────────────
        if ffmpeg_dir.exists():
            cmd += ["--ffmpeg-location", str(ffmpeg_dir)]

        # サムネイル埋め込み可否（yt-dlp は webm / wav への埋め込みに
        # 対応しておらず、ファイルは保存できても終了コード 1 になる）
        embed_thumb = bool(cfg["embed_thumbnail"])

        # ── フォーマット・変換 ────────────────────────────
        if mode == "audio":
            afmt = cfg["audio_fmt"]
            cmd += [
                "-f", "bestaudio/best",
                "-x",
                "--audio-format", afmt,
                "--audio-quality", "0",
            ]
            if afmt not in THUMB_AUDIO_FMTS:
                embed_thumb = False
        else:
            vfmt    = cfg["video_fmt"]
            quality = cfg["quality"]
            hfilter = QUALITY_MAP.get(quality, "")

            if vfmt == VIDEO_AUTO or vfmt == "auto":
                # 自動: コンテナ変換なしで最高画質
                cmd += ["-f", f"bestvideo{hfilter}+bestaudio/best"]
                if embed_thumb:
                    # VP9+Opus は既定だと webm に結合され埋め込めないため、
                    # 結合時は mp4（不可なら mkv）を使う
                    cmd += ["--merge-output-format", "mp4/mkv"]
            else:
                if vfmt == "mp4":
                    fmt = (f"bestvideo{hfilter}[ext=mp4]+bestaudio[ext=m4a]"
                           f"/bestvideo{hfilter}+bestaudio/best")
                elif vfmt == "webm":
                    fmt = (f"bestvideo{hfilter}[ext=webm]+bestaudio[ext=webm]"
                           f"/bestvideo{hfilter}+bestaudio/best")
                else:
                    fmt = f"bestvideo{hfilter}+bestaudio/best"

                cmd += [
                    "-f", fmt,
                    "--merge-output-format", vfmt,
                    "--remux-video", vfmt,
                ]
                if vfmt not in THUMB_VIDEO_FMTS:
                    embed_thumb = False

        # ── プレイリスト ──────────────────────────────────
        if cfg["playlist"]:
            cmd += ["--yes-playlist"]
        else:
            cmd += ["--no-playlist"]

        # ── サムネイル ────────────────────────────────────
        if embed_thumb:
            cmd += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]

        # ── 字幕 ─────────────────────────────────────────
        if cfg["embed_subtitles"] and mode != "audio":
            cmd += ["--embed-subs", "--sub-langs", "ja,en"]
        if cfg["auto_subtitles"]:
            cmd += ["--write-auto-subs"]

        # ── メタデータ ────────────────────────────────────
        cmd += ["--add-metadata"]

        # ── エラー無視 ────────────────────────────────────
        if cfg["ignore_errors"]:
            cmd += ["--ignore-errors"]

        # ── ダウンロード済みスキップ ───────────────────────
        if cfg["skip_existing"]:
            cmd += ["--no-overwrites"]

        # ── 範囲ダウンロード ──────────────────────────────
        ts = (cfg["time_start"] or "").strip()
        te = (cfg["time_end"]   or "").strip()
        if ts or te:
            section = f"{ts or ''}-{te or ''}"
            cmd += ["--download-sections", f"*{section}",
                    "--force-keyframes-at-cuts"]

        # ── 帯域制限 ─────────────────────────────────────
        # 【セキュリティ】許可する形式のみ通す（数値+単位）
        rl = (cfg["rate_limit"] or "").strip()
        if rl and re.match(r'^\d+(\.\d+)?[KMGkmg]?$', rl):
            cmd += ["--rate-limit", rl]

        # ── Cookie ───────────────────────────────────────
        # 【セキュリティ】パスの存在確認と拡張子チェック
        cf = (cfg["cookie_file"] or "").strip()
        if cf:
            cf_path = Path(cf)
            if (cf_path.exists()
                    and cf_path.is_file()
                    and cf_path.suffix.lower() in (".txt", "")
                    and cf_path.stat().st_size < 10 * 1024 * 1024):
                cmd += ["--cookies", str(cf_path)]

        # ── リトライ・並列フラグメント ─────────────────────
        cmd += [
            "--retries", "0",
            "--concurrent-fragments", "4",
            "--progress",
            "--newline",
        ]

        cmd += [task.url]
        return cmd

    # ── yt-dlp オプション生成（Python API 用・情報取得専用）──
    def _build_info_opts(self) -> dict:
        ffmpeg_dir = APP_DIR / "ffmpeg"
        opts: Dict[str, Any] = {
            "quiet":    True,
            "no_color": True,
        }
        if ffmpeg_dir.exists():
            opts["ffmpeg_location"] = str(ffmpeg_dir)
        return opts

    # ── 進捗行パース ─────────────────────────────────────
    _PROG_PATTERN = re.compile(
        r'\[download\]\s+([\d.]+)%'
        r'(?:\s+of\s+~?\s*[\d.]+\s*[KMGT]?i?B)?'
        r'(?:\s+at\s+(?:([\d.]+\s*[KMGT]?i?B/s)|Unknown\s+B/s))?'
        r'(?:\s+ETA\s+([\d:]+))?')
    _ERROR_PATTERN = re.compile(r'^ERROR:\s*(.+)$')

    @staticmethod
    def _parse_progress(line: str, task: DownloadTask) -> bool:
        """yt-dlp --newline の出力をパースして task を更新。更新あり→True"""
        # [download]  42.3% of  123.45MiB at  1.23MiB/s ETA 00:12
        # [download]  12.0% of ~  50.00MiB at  2.00MiB/s ETA 00:20 (frag 3/40)
        # [download]   5.0% of  10.00MiB at  Unknown B/s ETA Unknown
        m = Downloader._PROG_PATTERN.search(line)
        if m:
            task.progress = float(m.group(1))
            task.speed    = m.group(2) or ""
            task.eta      = m.group(3) or ""
            task.state    = TaskState.DOWNLOADING
            return True
        if "[download] 100%" in line:
            task.progress = 100.0
            return True
        if any(kw in line for kw in (
            "[Merger]", "[ffmpeg]", "[VideoRemuxer]",
            "[ExtractAudio]", "[ThumbnailsConvertor]", "[EmbedThumbnail]",
        )):
            task.state = TaskState.CONVERTING
            return True
        return False

    # ── 出力ファイルパス収集（暗号化保存用）──────────────────
    _OUT_PATTERNS = [
        re.compile(r'\[Merger\] Merging formats into "(.+)"'),
        re.compile(r'\[VideoRemuxer\][^"]*"(.+)"'),
        re.compile(r'\[ExtractAudio\] Destination: (.+)$'),
        re.compile(r'\[MoveFiles\] Moving file ".+" to "(.+)"'),
        re.compile(r'\[download\] (.+) has already been downloaded'),
    ]
    _DEST_PATTERN = re.compile(r'Destination:\s*(.+)$')
    _PART_PATTERN = re.compile(r'\.f\d+\.\w+$')

    def _collect_out_file(self, line: str, task: DownloadTask):
        for pat in self._OUT_PATTERNS:
            m = pat.search(line)
            if m:
                p = m.group(1).strip()
                if p and p not in task.out_files:
                    task.out_files.append(p)
                return
        m = self._DEST_PATTERN.search(line)
        if m:
            p = m.group(1).strip()
            # 中間ファイル（.fXXX.ext）は除外
            if p and not self._PART_PATTERN.search(p) \
                    and p not in task.out_files:
                task.out_files.append(p)

    # ── 暗号化保存 ────────────────────────────────────────
    def _encrypt_outputs(self, task: DownloadTask):
        pw = self.encrypt_password
        if not pw:
            return
        if not CRYPTO_OK:
            self.q.put(("log",
                "[WARN] 暗号化保存には pycryptodomex が必要です"
                "（pip install pycryptodomex）"))
            return
        targets = [Path(p) for p in task.out_files]
        targets = [p for p in targets
                   if p.exists() and p.suffix.lower() != ENC_EXT]
        if not targets:
            self.q.put(("log", "[WARN] 暗号化対象ファイルが見つかりませんでした"))
            return
        task.state = TaskState.CONVERTING
        self.q.put(("task_update", task))
        for p in targets:
            try:
                out = encrypt_file(p, pw)
                self.q.put(("log", f"[INFO] 🔒 暗号化しました: {out.name}"))
            except Exception as e:
                self.q.put(("log", f"[WARN] 暗号化に失敗: {p.name} — {e}"))

    # ── タスク実行 ────────────────────────────────────────
    def run_task(self, task: DownloadTask):
        """セマフォ制御付き。スレッドから呼ぶ。"""
        # 起動時点の停止イベント・セマフォを握る（reset() で差し替わっても
        # このスレッドは自分の世代の停止指示に従う）
        stop = self._stop
        with self._sem:
            if task.removed:
                return
            if stop.is_set():
                task.state = TaskState.PAUSED
                self.q.put(("task_update", task))
                return

            task.started  = datetime.now()
            max_retry     = self.cfg["retries"]

            for attempt in range(max_retry + 1):
                if stop.is_set():
                    task.state = TaskState.PAUSED
                    self.q.put(("task_update", task))
                    return

                if attempt > 0:
                    wait = min(2 ** attempt, 30)
                    task.state = TaskState.RETRYING
                    task.retry = attempt
                    self.q.put(("task_update", task))
                    self.q.put(("log",
                        f"[リトライ {attempt}/{max_retry}] {task.short_url()} — {wait}秒後"))
                    # 待機中でも停止ボタンにすぐ反応する
                    if stop.wait(wait):
                        task.state = TaskState.PAUSED
                        self.q.put(("task_update", task))
                        return

                task.last_error = ""
                try:
                    cmd = self._build_cmd(task)
                    self.q.put(("log", f"[CMD] {' '.join(str(c) for c in cmd[:8])} ..."))

                    # Windows では PYTHONUTF8=1 を渡して yt-dlp の出力を UTF-8 に強制
                    env = os.environ.copy()
                    env["PYTHONUTF8"]        = "1"
                    env["PYTHONIOENCODING"]  = "utf-8:replace"
                    env["PYTHONLEGACYWINDOWSSTDIO"] = "0"

                    # 文字化け対策: バイナリで受け取り、行ごとに
                    # エンコーディングを自動判別してデコードする
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        env=env,
                        creationflags=(subprocess.CREATE_NO_WINDOW
                                       if IS_WIN else 0),
                    )

                    with self._lock:
                        self._ydls[id(task)] = proc  # type: ignore[assignment]
                    if stop.is_set():
                        proc.kill()

                    for raw_line in proc.stdout:  # type: ignore[union-attr]
                        if stop.is_set():
                            proc.kill()
                            break
                        line = decode_console_bytes(raw_line).rstrip()
                        if not line:
                            continue

                        # yt-dlp の出力からタイトルを拾う
                        if not task.title or task.title == task.url:
                            m = re.search(
                                r'Destination:\s*.+[\\/](.+?)(?:\.f\d+)?\.\w+\s*$',
                                line)
                            if m:
                                task.title = m.group(1)
                                self.q.put(("task_update", task))

                        self._collect_out_file(line, task)

                        em = self._ERROR_PATTERN.match(line)
                        if em:
                            task.last_error = em.group(1).strip()

                        if self._parse_progress(line, task):
                            self.q.put(("task_update", task))
                        if "ERROR" in line or "WARNING" in line:
                            self.q.put(("log", f"[WARN] {line}"))
                        else:
                            self.q.put(("log", f"[DBG] {line}"))

                    proc.wait()

                    if stop.is_set():
                        task.state = TaskState.PAUSED
                        self.q.put(("task_update", task))
                        return

                    if proc.returncode == 0:
                        self._encrypt_outputs(task)
                        task.state    = TaskState.DONE
                        task.progress = 100.0
                        task.finished = datetime.now()
                        self.q.put(("task_update", task))
                        self.q.put(("task_done",   task))
                        return
                    else:
                        raise RuntimeError(
                            task.last_error
                            or f"yt-dlp 終了コード {proc.returncode}")

                except Exception as e:
                    msg = str(e)
                    if "cancelled" in msg.lower() or stop.is_set():
                        task.state = TaskState.PAUSED
                        self.q.put(("task_update", task))
                        return
                    if attempt < max_retry:
                        continue
                    task.state    = TaskState.ERROR
                    task.error    = msg[:400]
                    task.finished = datetime.now()
                    self.q.put(("task_update", task))
                    self.q.put(("task_error",  task))
                    return
                finally:
                    with self._lock:
                        self._ydls.pop(id(task), None)

# ══════════════════════════════════════════════════════════════
#  テーマ管理
# ══════════════════════════════════════════════════════════════

class ThemeManager:
    def __init__(self, dark: bool = True):
        self._dark = dark
        self.c = DARK_THEME if dark else LIGHT_THEME

    @property
    def dark(self): return self._dark

    def toggle(self):
        self._dark = not self._dark
        self.c = DARK_THEME if self._dark else LIGHT_THEME

    def accent_tint(self, base_key: str = "bg1") -> str:
        """アクセント色の淡い背景（CSS #0078d418 相当）"""
        return blend(self.c[base_key], ACCENT, 0.10)

    def apply_ttk(self, root: tk.Tk, style: ttk.Style):
        c = self.c
        style.theme_use("clam")

        style.configure(".", background=c["bg1"], foreground=c["text"],
                        font=F(13),
                        fieldbackground=c["bg3"], bordercolor=c["border"],
                        troughcolor=c["bg4"], selectbackground=ACCENT,
                        selectforeground="#ffffff")

        # TEntry（入力欄: bg3 / 枠 border / フォーカス時 accent）
        style.configure("TEntry",
                        fieldbackground=c["bg3"], foreground=c["text"],
                        insertcolor=c["text"], bordercolor=c["border"],
                        lightcolor=c["border"], darkcolor=c["border"],
                        padding=(P(8), P(6)))
        style.map("TEntry",
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)],
                  fieldbackground=[("disabled", c["bg2"])],
                  foreground=[("disabled", c["text3"])])

        # TCombobox
        style.configure("TCombobox",
                        fieldbackground=c["bg3"], background=c["bg3"],
                        foreground=c["text"],
                        selectbackground=c["bg3"], selectforeground=c["text"],
                        bordercolor=c["border"], arrowcolor=c["text2"],
                        lightcolor=c["border"], darkcolor=c["border"],
                        padding=(P(8), P(6)))
        style.map("TCombobox",
                  fieldbackground=[("readonly", c["bg3"])],
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])
        root.option_add("*TCombobox*Listbox.background", c["bg2"])
        root.option_add("*TCombobox*Listbox.foreground", c["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        root.option_add("*TCombobox*Listbox.font", F(12))

        # TSpinbox
        style.configure("TSpinbox",
                        fieldbackground=c["bg3"], foreground=c["text"],
                        insertcolor=c["text"],
                        bordercolor=c["border"], arrowcolor=c["text2"],
                        lightcolor=c["border"], darkcolor=c["border"],
                        padding=(P(8), P(5)))
        style.map("TSpinbox",
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])

        # Scrollbar
        style.configure("Vertical.TScrollbar",
                        background=c["bg4"], troughcolor=c["bg2"],
                        arrowcolor=c["text2"], borderwidth=0,
                        gripcount=0, width=P(8))
        style.map("Vertical.TScrollbar",
                  background=[("active", c["text3"])])
        style.configure("Horizontal.TScrollbar",
                        background=c["bg4"], troughcolor=c["bg2"],
                        arrowcolor=c["text2"], borderwidth=0, width=P(8))

# ══════════════════════════════════════════════════════════════
#  カスタムウィジェット
# ══════════════════════════════════════════════════════════════

def _rounded_rect_ids(cv: tk.Canvas, x0, y0, x1, y1, r, fill, outline=""):
    """角丸長方形を描く（arc + rect の組み合わせ）"""
    ids = []
    ol = outline or fill
    ids.append(cv.create_arc(x0, y0, x0+2*r, y0+2*r, start=90,  extent=90,
                             fill=fill, outline=ol))
    ids.append(cv.create_arc(x1-2*r, y0, x1, y0+2*r, start=0,   extent=90,
                             fill=fill, outline=ol))
    ids.append(cv.create_arc(x0, y1-2*r, x0+2*r, y1, start=180, extent=90,
                             fill=fill, outline=ol))
    ids.append(cv.create_arc(x1-2*r, y1-2*r, x1, y1, start=270, extent=90,
                             fill=fill, outline=ol))
    ids.append(cv.create_rectangle(x0+r, y0, x1-r, y1, fill=fill, outline=fill))
    ids.append(cv.create_rectangle(x0, y0+r, x1, y1-r, fill=fill, outline=fill))
    return ids


class PillButton(tk.Canvas):
    """角丸6pxのフラットボタン（accent / outline / danger-outline）"""
    def __init__(self, master, text="", command=None, kind="accent",
                 theme: dict = None, bg="#000000",
                 height=None, hpad=None, font=None, bold=False,
                 outline_color=None, text_color=None, **kw):
        self._t       = theme or DARK_THEME
        self._text    = text
        self._cmd     = command
        self._kind    = kind
        self._bold    = bold
        self._enabled = True
        self._hover   = False
        self._font    = font or F(13, bold)
        self._hpad    = hpad if hpad is not None else P(22)
        self._radius  = P(6)
        self._outline_color = outline_color
        self._text_color    = text_color
        h = height if height is not None else P(38)
        fo = tkfont.Font(font=self._font)
        w = fo.measure(text) + self._hpad * 2
        super().__init__(master, width=w, height=h,
                         highlightthickness=0, bd=0, bg=bg, **kw)
        self._wd, self._ht = w, h
        self._draw()
        self.bind("<Enter>",           self._on_enter)
        self.bind("<Leave>",           self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_enabled(self, enabled: bool):
        if self._enabled != enabled:
            self._enabled = enabled
            self._draw()

    def _colors(self):
        t = self._t
        if self._kind == "accent":
            if not self._enabled:
                return t["bg4"], "", t["text2"]
            return (ACCENT_H if self._hover else ACCENT), "", "#ffffff"
        # outline系: 塗り=パネル背景, 枠, 文字
        oc = self._outline_color or t["border"]
        tc = self._text_color or t["text"]
        if not self._enabled:
            bg = self["bg"]
            return bg, blend(oc, bg, 0.6), blend(tc, bg, 0.6)
        fill = blend(self["bg"], self._t["bg4"], 0.4) if self._hover else self["bg"]
        return fill, oc, tc

    def _draw(self):
        self.delete("all")
        fill, outline, txt = self._colors()
        r = self._radius
        if outline:
            _rounded_rect_ids(self, 0, 0, self._wd-1, self._ht-1, r,
                              fill=outline)
            _rounded_rect_ids(self, 1, 1, self._wd-2, self._ht-2, r,
                              fill=fill)
        else:
            _rounded_rect_ids(self, 0, 0, self._wd-1, self._ht-1, r, fill=fill)
        self.create_text(self._wd//2, self._ht//2, text=self._text,
                         fill=txt, font=self._font)
        # "no"（禁止カーソル）は Windows 専用。他 OS では起動時に TclError になる
        self.configure(cursor="hand2" if self._enabled
                       else ("no" if IS_WIN else "arrow"))

    def _on_enter(self, _):
        self._hover = True
        self._draw()

    def _on_leave(self, _):
        self._hover = False
        self._draw()

    def _on_release(self, e):
        if (self._enabled and self._cmd
                and 0 <= e.x <= self._wd and 0 <= e.y <= self._ht):
            self._cmd()


class SmoothToggle(tk.Canvas):
    """トグルスイッチ（トラック36x20・サム16px円 / ON=accent, OFF=bg4）"""
    def __init__(self, master, variable: tk.BooleanVar,
                 theme: dict = None,
                 width=None, height=None, command=None, **kw):
        w = width  if width  is not None else P(36)
        h = height if height is not None else P(20)
        super().__init__(master, width=w, height=h,
                         highlightthickness=0, bd=0, cursor="hand2", **kw)
        self._t   = theme or DARK_THEME
        self._var = variable
        self._wd, self._ht = w, h
        self._cmd = command
        self._pos = 1.0 if variable.get() else 0.0
        self._animating = False
        self._draw()
        self.bind("<Button-1>", self._toggle)
        self._trace = variable.trace_add("write", lambda *_: self._start_anim())

    def _start_anim(self):
        if not self._animating and self.winfo_exists():
            self._animating = True
            self._anim()

    def _anim(self):
        if not self.winfo_exists():
            self._animating = False
            return
        target = 1.0 if self._var.get() else 0.0
        diff   = target - self._pos
        if abs(diff) < 0.05:
            self._pos = target
            self._draw()
            self._animating = False
            return
        self._pos += diff * 0.25
        self._draw()
        self.after(16, self._anim)

    def _draw(self):
        self.delete("all")
        w, h = self._wd, self._ht
        c = ACCENT if self._var.get() else self._t["bg4"]
        # track（丸ピル）
        self.create_oval(0, 0, h, h, fill=c, outline=c)
        self.create_oval(w-h, 0, w, h, fill=c, outline=c)
        self.create_rectangle(h//2, 0, w-h//2, h, fill=c, outline=c)
        # thumb 16px 円
        pad  = P(2)
        d    = h - pad*2
        x    = pad + self._pos * (w - d - pad*2)
        self.create_oval(x, pad, x+d, pad+d, fill="#ffffff", outline="#ffffff")

    def _toggle(self, _):
        self._var.set(not self._var.get())
        if self._cmd:
            self._cmd()


class Dot(tk.Canvas):
    """色付きステータスドット"""
    def __init__(self, master, size, color, bg, **kw):
        super().__init__(master, width=size, height=size,
                         highlightthickness=0, bd=0, bg=bg, **kw)
        self._size = size
        self._color = color
        self._draw()

    def set_color(self, color):
        if color != self._color:
            self._color = color
            self._draw()

    def _draw(self):
        self.delete("all")
        self.create_oval(0, 0, self._size-1, self._size-1,
                         fill=self._color, outline=self._color)


class SlimProgressBar(tk.Canvas):
    """角丸スリムプログレスバー（色変更可・軽いアニメーション付き）"""
    def __init__(self, master, height=None, trough="#383838",
                 color=ACCENT, **kw):
        h = height if height is not None else P(6)
        super().__init__(master, height=h, highlightthickness=0,
                         bd=0, **kw)
        self._trough = trough
        self._color  = color
        self._ht     = h
        self._val    = 0.0
        self._anim_val = 0.0
        self._running  = False
        self.bind("<Configure>", lambda _: self._draw())

    def set(self, val: float, color: str = None):
        if color and color != self._color:
            self._color = color
        self._val = max(0.0, min(100.0, val))
        if not self._running:
            self._running = True
            self._animate()

    def set_color(self, color: str):
        if color != self._color:
            self._color = color
            self._draw()

    def _animate(self):
        if not self.winfo_exists():
            self._running = False
            return
        diff = self._val - self._anim_val
        if abs(diff) < 0.5:
            self._anim_val = self._val
            self._draw()
            self._running = False
            return
        self._anim_val += diff * 0.2
        self._draw()
        self.after(16, self._animate)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self._ht
        if w < 4:
            return
        r = h // 2
        # trough
        self.create_oval(0, 0, h, h, fill=self._trough, outline=self._trough)
        self.create_oval(w-h, 0, w, h, fill=self._trough, outline=self._trough)
        self.create_rectangle(r, 0, w-r, h, fill=self._trough,
                              outline=self._trough)
        # fill
        fw = int(w * self._anim_val / 100)
        if fw >= h:
            self.create_oval(0, 0, h, h, fill=self._color, outline=self._color)
            self.create_oval(fw-h, 0, fw, h, fill=self._color,
                             outline=self._color)
            self.create_rectangle(r, 0, fw-r, h, fill=self._color,
                                  outline=self._color)
        elif fw > 0:
            self.create_oval(0, 0, max(fw, 2), h, fill=self._color,
                             outline=self._color)


class TabBar(tk.Frame):
    """フラットタブバー（アクティブ: accent文字 + 2px下線）"""
    def __init__(self, master, items, active, command,
                 theme: dict, bg, font_px=13,
                 padx=None, pady=None, **kw):
        super().__init__(master, bg=bg, **kw)
        self._t      = theme
        self._items  = items
        self._cmd    = command
        self._active = active
        self._bg     = bg
        self._font_px = font_px
        self._labels: Dict[str, tk.Label] = {}
        self._unders: Dict[str, tk.Frame] = {}
        px = padx if padx is not None else P(16)
        py = pady if pady is not None else P(11)
        for key, label in items:
            holder = tk.Frame(self, bg=bg)
            holder.pack(side="left")
            lbl = tk.Label(holder, text=label, bg=bg, cursor="hand2",
                           padx=px, pady=py)
            lbl.pack()
            under = tk.Frame(holder, bg=bg, height=P(2))
            under.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, k=key: self._on_click(k))
            self._labels[key] = lbl
            self._unders[key] = under
        self._refresh()

    def _on_click(self, key):
        if key != self._active:
            self._active = key
            self._refresh()
            self._cmd(key)

    def set_active(self, key):
        self._active = key
        self._refresh()

    def _refresh(self):
        for key in self._labels:
            on = key == self._active
            self._labels[key].configure(
                fg=ACCENT if on else self._t["text2"],
                font=F(self._font_px, bold=on))
            self._unders[key].configure(bg=ACCENT if on else self._bg)


class ScrollFrame(tk.Frame):
    """縦スクロール可能フレーム（マウスホイール対応）"""
    def __init__(self, master, bg, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical",
                                 command=self.canvas.yview,
                                 style="Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        # ホイール: カーソルが乗っている間だけ全体バインド
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_inner(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _bind_wheel(self, _):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e):
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")


class AutoScrollText(tk.Text):
    """自動スクロール付きテキストウィジェット"""
    MAX_LINES = 2000

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._auto_scroll = True
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>",   self._on_wheel)
        self.bind("<Button-5>",   self._on_wheel)

    def _on_wheel(self, _):
        self.after(50, self._check_bottom)

    def _check_bottom(self):
        pos = self.yview()
        self._auto_scroll = pos[1] >= 0.99

    def append_line(self, line: str, tag: str = ""):
        self.config(state="normal")
        lines = int(self.index("end-1c").split(".")[0])
        if lines > self.MAX_LINES:
            self.delete("1.0", f"{lines - self.MAX_LINES}.0")
        if tag:
            self.insert("end", line + "\n", tag)
        else:
            self.insert("end", line + "\n")
        if self._auto_scroll:
            self.see("end")
        self.config(state="disabled")


def draw_app_icon(cv: tk.Canvas, size: int):
    """アプリアイコン（角丸青タイル+白再生三角）をキャンバスに描く"""
    r = max(2, round(size * 0.23))
    _rounded_rect_ids(cv, 0, 0, size-1, size-1, r, fill=ACCENT)
    # 白い再生三角
    tw = size * 0.34
    th = size * 0.42
    cx = size * 0.55
    cy = size * 0.5
    cv.create_polygon(
        cx - tw/2, cy - th/2,
        cx - tw/2, cy + th/2,
        cx + tw/2, cy,
        fill="#ffffff", outline="#ffffff")

# ══════════════════════════════════════════════════════════════
#  メインアプリケーション (View + Controller)
# ══════════════════════════════════════════════════════════════

class App:
    # ── 初期化 ────────────────────────────────────────────
    def __init__(self):
        self.cfg    = Config()
        self.theme  = ThemeManager(self.cfg["dark_mode"])
        self.msg_q  = queue.Queue()
        self.dl     = Downloader(self.cfg, self.msg_q)

        self.tasks:   List[DownloadTask] = []
        self.threads: List[threading.Thread] = []
        self._running = False

        self._left_tab  = "basic"     # 基本 / 詳細設定
        self._right_tab = "queue"     # キュー / 速度グラフ / ログ / 履歴
        self._url_content = ""        # URL欄の内容（タブ・テーマ再構築対応）
        self._log_lines: List[tuple] = []    # (text, tag)
        self._speed_history: List[float] = []
        self._cur_speed_mbps = 0.0
        self._selected: set  = set()  # 選択中タスク idx
        self._queue_rows: Dict[int, "QueueRow"] = {}
        self._ytdlp_ver  = ""         # yt-dlp 実効バージョン（非同期取得）
        self._updating   = False      # yt-dlp 更新実行中フラグ

        self.root = tk.Tk()
        self.root.withdraw()

        self._setup_scale()
        self._setup_root()
        self._init_vars()
        self.style = ttk.Style(self.root)
        self.theme.apply_ttk(self.root, self.style)
        self._build_all()
        self.root.deiconify()

        self._start_queue_poll()
        self.root.after(500,  self._watch_clipboard)
        self.root.after(1000, self._graph_tick)
        self.root.after(1000, self._schedule_tick)
        threading.Thread(target=self._refresh_ytdlp_version,
                         daemon=True).start()

    # ── DPIスケール ───────────────────────────────────────
    def _setup_scale(self):
        if IS_WIN:
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        try:
            set_ui_scale(self.root.winfo_fpixels("1i") / 96.0)
        except Exception:
            set_ui_scale(1.0)

    # ── Root 設定 ─────────────────────────────────────────
    def _setup_root(self):
        r = self.root
        r.title(APP_TITLE)
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        w = min(P(1440), sw - P(60))
        h = min(P(900),  sh - P(100))
        r.geometry(f"{w}x{h}+{(sw-w)//2}+{max(0,(sh-h)//2-P(20))}")
        r.minsize(P(1024), P(640))
        r.configure(bg=self.theme.c["bg1"])
        ico = APP_DIR / "icon.ico"
        if IS_WIN and ico.exists():
            try:
                r.iconbitmap(str(ico))
            except Exception:
                pass
        r.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── tk 変数 ───────────────────────────────────────────
    def _init_vars(self):
        cfg = self.cfg
        self._dark_var        = tk.BooleanVar(value=self.theme.dark)
        self._mode_var        = tk.StringVar(value=cfg["mode"])
        vfmt = cfg["video_fmt"]
        if vfmt in ("auto", ""):
            vfmt = VIDEO_AUTO
        self._vfmt_var        = tk.StringVar(value=vfmt)
        self._afmt_var        = tk.StringVar(value=cfg["audio_fmt"])
        self._quality_var     = tk.StringVar(value=cfg["quality"])
        self._save_var        = tk.StringVar(value=cfg["save_dir"])
        self._opts_vars: Dict[str, tk.BooleanVar] = {
            k: tk.BooleanVar(value=cfg[k]) for k in (
                "playlist", "embed_thumbnail", "embed_subtitles",
                "auto_subtitles", "ignore_errors", "skip_existing")}
        self._ts_var          = tk.StringVar(value=cfg["time_start"])
        self._te_var          = tk.StringVar(value=cfg["time_end"])
        self._concurrent_var  = tk.IntVar(value=cfg["concurrent"])
        self._retries_var     = tk.IntVar(value=cfg["retries"])
        self._rate_var        = tk.StringVar(value=cfg["rate_limit"])
        self._cookie_var      = tk.StringVar(value=cfg["cookie_file"])
        self._post_action_var = tk.StringVar(value=cfg["post_action"])
        self._rename_var      = tk.StringVar(value="")
        self._encrypt_var     = tk.BooleanVar(value=cfg["encrypt_enable"])
        self._encrypt_pw_var  = tk.StringVar(value="")   # 保存しない
        self._sched_enable_var = tk.BooleanVar(value=cfg["schedule_enable"])
        self._sched_time_var   = tk.StringVar(value=cfg["schedule_time"])
        self._preset_select_var = tk.StringVar()
        self._preset_name_var   = tk.StringVar()

        self._ts_var.trace_add("write", lambda *_: self._save_opts())
        self._te_var.trace_add("write", lambda *_: self._save_opts())
        self._opts_vars["playlist"].trace_add(
            "write", lambda *_: self._update_rename_state())

    # ══════════════════════════════════════════════════════
    #  UI 全構築（テーマ切替時も丸ごと再構築する）
    # ══════════════════════════════════════════════════════

    def _build_all(self):
        c = self.theme.c
        self.root.configure(bg=c["bg1"])
        for w in self.root.winfo_children():
            w.destroy()
        self._queue_rows.clear()

        self._build_header()
        self._build_onboarding()
        self._build_statusbar()   # side=bottom を先に確保

        main = tk.Frame(self.root, bg=c["bg1"])
        main.pack(fill="both", expand=True)

        # 左パネル 380px 固定
        self.left_frame = tk.Frame(main, bg=c["bg2"], width=P(380))
        self.left_frame.pack(side="left", fill="y")
        self.left_frame.pack_propagate(False)
        tk.Frame(main, bg=c["border"], width=1).pack(side="left", fill="y")

        # 右パネル
        self.right_frame = tk.Frame(main, bg=c["bg1"])
        self.right_frame.pack(side="left", fill="both", expand=True)

        self._build_left_panel()
        self._build_right_panel()
        self._update_overall()
        self._update_action_states()

    # ── タイトルバー（44px） ──────────────────────────────
    def _build_header(self):
        c = self.theme.c
        hdr = tk.Frame(self.root, bg=c["bg2"], height=P(44))
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Frame(self.root, bg=c["border"], height=1).pack(fill="x")

        left = tk.Frame(hdr, bg=c["bg2"])
        left.pack(side="left", padx=(P(16), 0))
        icon = tk.Canvas(left, width=P(22), height=P(22),
                         bg=c["bg2"], highlightthickness=0, bd=0)
        draw_app_icon(icon, P(22))
        icon.pack(side="left", pady=P(11))
        tk.Label(left, text="yt-dlp GUI", bg=c["bg2"], fg=c["text"],
                 font=F(14, True)).pack(side="left", padx=(P(10), 0))
        tk.Label(left, text=f"v{APP_VERSION}",
                 bg=c["bg3"], fg=c["text2"],
                 font=F(11), padx=P(8), pady=P(2)).pack(
            side="left", padx=(P(10), 0))

        right = tk.Frame(hdr, bg=c["bg2"])
        right.pack(side="right", padx=(0, P(16)))

        # テーマ切替（ラベル + トグル）
        self._theme_lbl = tk.Label(
            right, text="ダーク" if self.theme.dark else "ライト",
            bg=c["bg2"], fg=c["text2"], font=F(12), cursor="hand2")
        self._theme_lbl.pack(side="left", padx=(0, P(8)))
        self._theme_switch = tk.Canvas(
            right, width=P(40), height=P(22),
            bg=c["bg2"], highlightthickness=0, bd=0, cursor="hand2")
        self._theme_switch.pack(side="left")
        self._draw_theme_switch()
        for w in (self._theme_lbl, self._theme_switch):
            w.bind("<Button-1>", lambda _e: self._toggle_theme())

    def _draw_theme_switch(self):
        cv = self._theme_switch
        c  = self.theme.c
        cv.delete("all")
        w, h = P(40), P(22)
        # トラック bg4
        cv.create_oval(0, 0, h, h, fill=c["bg4"], outline=c["bg4"])
        cv.create_oval(w-h, 0, w, h, fill=c["bg4"], outline=c["bg4"])
        cv.create_rectangle(h//2, 0, w-h//2, h, fill=c["bg4"],
                            outline=c["bg4"])
        # サム 18px accent（ダーク=右 / ライト=左）
        pad = P(2)
        d   = h - pad*2
        x   = (w - d - pad) if self.theme.dark else pad
        cv.create_oval(x, pad, x+d, pad+d, fill=ACCENT, outline=ACCENT)

    # ── オンボーディングバナー ────────────────────────────
    def _build_onboarding(self):
        self._onboarding_frame = None
        if self.cfg["onboarding_done"]:
            return
        c = self.theme.c
        tint = self.theme.accent_tint("bg1")
        f = tk.Frame(self.root, bg=tint, height=P(40))
        f.pack(fill="x")
        f.pack_propagate(False)
        self._onboarding_frame = f
        tk.Frame(self.root, bg=ACCENT, height=1).pack(fill="x")
        self._onboarding_border = self.root.winfo_children()[-1]

        inner = tk.Frame(f, bg=tint)
        inner.pack(fill="both", expand=True, padx=P(20))

        def step(n, text):
            sf = tk.Frame(inner, bg=tint)
            sf.pack(side="left", pady=P(9))
            cv = tk.Canvas(sf, width=P(18), height=P(18),
                           bg=tint, highlightthickness=0, bd=0)
            cv.create_oval(0, 0, P(18)-1, P(18)-1, fill=ACCENT, outline=ACCENT)
            cv.create_text(P(9), P(9), text=str(n), fill="#ffffff",
                           font=F(11, True))
            cv.pack(side="left")
            tk.Label(sf, text=text, bg=tint, fg=c["text"],
                     font=F(12)).pack(side="left", padx=(P(8), 0))

        step(1, "URLを貼り付け")
        tk.Label(inner, text="→", bg=tint, fg=c["text3"],
                 font=F(12)).pack(side="left", padx=P(14))
        step(2, "モードを選択")
        tk.Label(inner, text="→", bg=tint, fg=c["text3"],
                 font=F(12)).pack(side="left", padx=P(14))
        step(3, "ダウンロード開始をクリック")

        close = tk.Label(inner, text="✕ 閉じる", bg=tint, fg=c["text2"],
                         font=F(12), cursor="hand2", padx=P(6))
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self._dismiss_onboarding())

    def _dismiss_onboarding(self):
        if not self.cfg["onboarding_done"]:
            self.cfg["onboarding_done"] = True
            self.cfg.save()
        if self._onboarding_frame and self._onboarding_frame.winfo_exists():
            self._onboarding_frame.destroy()
            self._onboarding_frame = None
            if hasattr(self, "_onboarding_border") \
                    and self._onboarding_border.winfo_exists():
                self._onboarding_border.destroy()

    # ══════════════════════════════════════════════════════
    #  左パネル（基本 / 詳細設定）
    # ══════════════════════════════════════════════════════

    def _build_left_panel(self):
        c = self.theme.c
        p = self.left_frame

        tabbar_holder = tk.Frame(p, bg=c["bg2"])
        tabbar_holder.pack(fill="x")
        self._left_tabbar = TabBar(
            tabbar_holder,
            items=[("basic", "基本"), ("adv", "詳細設定")],
            active=self._left_tab,
            command=self._on_left_tab,
            theme=c, bg=c["bg2"], font_px=13)
        self._left_tabbar.pack(side="left", padx=P(8))
        tk.Frame(p, bg=c["border"], height=1).pack(fill="x")

        self._left_scroll = ScrollFrame(p, bg=c["bg2"])
        self._left_scroll.pack(fill="both", expand=True)
        self._build_left_content()

    def _on_left_tab(self, key):
        self._sync_url_content()
        self._left_tab = key
        self._build_left_content()

    def _sync_url_content(self):
        if hasattr(self, "url_text") and self.url_text.winfo_exists():
            self._url_content = self.url_text.get("1.0", "end-1c")

    def _build_left_content(self):
        c = self.theme.c
        self._sync_url_content()
        inner = self._left_scroll.inner
        for w in inner.winfo_children():
            w.destroy()
        body = tk.Frame(inner, bg=c["bg2"])
        body.pack(fill="x", padx=P(16), pady=P(16))
        if self._left_tab == "basic":
            self._build_basic_tab(body)
        else:
            self._build_adv_tab(body)

    # ── セクション見出し（3x13 アクセントバー + ラベル）─────
    def _section(self, parent, title, gap_top=0):
        c = self.theme.c
        sec = tk.Frame(parent, bg=c["bg2"])
        sec.pack(fill="x", pady=(gap_top, 0))
        head = tk.Frame(sec, bg=c["bg2"])
        head.pack(fill="x")
        bar = tk.Frame(head, bg=ACCENT, width=P(3), height=P(13))
        bar.pack(side="left")
        bar.pack_propagate(False)
        tk.Label(head, text=title, bg=c["bg2"], fg=c["text2"],
                 font=F(12, True)).pack(side="left", padx=(P(6), 0))
        return sec, head

    def _entry(self, parent, var, width=None, show=None, **kw):
        e = ttk.Entry(parent, textvariable=var, font=F(12), **kw)
        if width:
            e.configure(width=width)
        if show:
            e.configure(show=show)
        e.bind("<FocusOut>", lambda _e: self._save_opts())
        return e

    def _ghost_btn(self, parent, text, command, accent=False):
        c = self.theme.c
        return PillButton(
            parent, text=text, command=command,
            kind="accent" if accent else "outline",
            theme=c, bg=c["bg2"], height=P(29), hpad=P(10),
            font=F(12) if not accent else F(12, False))

    # ══ 基本タブ ══════════════════════════════════════════
    def _build_basic_tab(self, body):
        c = self.theme.c
        onboarding = not self.cfg["onboarding_done"]

        # ── URL入力 ───────────────────────────────────────
        sec, head = self._section(body, "URL入力")
        paste_badge = PillButton(
            head, text="貼り付けで追加", command=self._paste_clipboard,
            kind="accent", theme=c, bg=c["bg2"],
            height=P(26), hpad=P(10), font=F(11))
        paste_badge.pack(side="right")

        txt_holder = tk.Frame(
            sec, bg=c["bg3"],
            highlightthickness=1,
            highlightbackground=(ACCENT if onboarding else c["border"]),
            highlightcolor=ACCENT)
        txt_holder.pack(fill="x", pady=(P(8), 0))
        self.url_text = tk.Text(
            txt_holder, height=5, wrap="none",
            bg=c["bg3"], fg=c["text"],
            insertbackground=c["text"],
            selectbackground=ACCENT, selectforeground="#ffffff",
            font=F(13), relief="flat", bd=0,
            padx=P(10), pady=P(8))
        self.url_text.pack(fill="x")
        if self._url_content:
            self.url_text.insert("1.0", self._url_content)
        self.url_text.bind("<KeyRelease>", lambda _e: self._on_url_edited())

        foot = tk.Frame(sec, bg=c["bg2"])
        foot.pack(fill="x", pady=(P(8), 0))
        self._url_count_lbl = tk.Label(
            foot, text="0 URL", bg=c["bg2"], fg=c["text3"], font=F(11))
        self._url_count_lbl.pack(side="left")
        self._ghost_btn(foot, "クリア", self._clear_urls).pack(
            side="right")
        self._ghost_btn(foot, "クリップボードから貼り付け",
                        self._paste_clipboard).pack(
            side="right", padx=(0, P(8)))
        self._update_url_count()

        # ── ダウンロードモード ─────────────────────────────
        sec, _ = self._section(body, "ダウンロードモード", gap_top=P(20))
        cards = tk.Frame(sec, bg=c["bg2"])
        cards.pack(fill="x", pady=(P(8), 0))
        self._mode_cards = {}
        for i, (val, lbl) in enumerate([("video", "動画"),
                                        ("audio", "音声のみ")]):
            card = self._make_mode_card(cards, val, lbl)
            card.grid(row=0, column=i, sticky="ew",
                      padx=(0, P(8)) if i == 0 else 0)
            cards.columnconfigure(i, weight=1)

        # 形式・画質行（動画）
        self._video_fmt_frame = tk.Frame(sec, bg=c["bg2"])
        row = tk.Frame(self._video_fmt_frame, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        tk.Label(row, text="形式", bg=c["bg2"], fg=c["text2"],
                 font=F(12), width=5, anchor="w").pack(side="left")
        cb = ttk.Combobox(row, textvariable=self._vfmt_var,
                          values=VIDEO_FMTS, state="readonly",
                          font=F(12))
        cb.pack(side="left", fill="x", expand=True)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._save_opts())
        row2 = tk.Frame(self._video_fmt_frame, bg=c["bg2"])
        row2.pack(fill="x", pady=(P(8), 0))
        tk.Label(row2, text="画質", bg=c["bg2"], fg=c["text2"],
                 font=F(12), width=5, anchor="w").pack(side="left")
        cb2 = ttk.Combobox(row2, textvariable=self._quality_var,
                           values=list(QUALITY_MAP.keys()),
                           state="readonly", font=F(12))
        cb2.pack(side="left", fill="x", expand=True)
        cb2.bind("<<ComboboxSelected>>", lambda _e: self._save_opts())

        # 形式行（音声）
        self._audio_fmt_frame = tk.Frame(sec, bg=c["bg2"])
        row3 = tk.Frame(self._audio_fmt_frame, bg=c["bg2"])
        row3.pack(fill="x", pady=(P(8), 0))
        tk.Label(row3, text="形式", bg=c["bg2"], fg=c["text2"],
                 font=F(12), width=5, anchor="w").pack(side="left")
        cb3 = ttk.Combobox(row3, textvariable=self._afmt_var,
                           values=AUDIO_FMTS, state="readonly",
                           font=F(12))
        cb3.pack(side="left", fill="x", expand=True)
        cb3.bind("<<ComboboxSelected>>", lambda _e: self._save_opts())

        self._apply_mode_visuals()

        # ── 保存先 ────────────────────────────────────────
        sec, _ = self._section(body, "保存先", gap_top=P(20))
        row = tk.Frame(sec, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        ent = self._entry(row, self._save_var)
        ent.pack(side="left", fill="x", expand=True)
        self._ghost_btn(row, "参照…", self._browse_dir).pack(
            side="right", padx=(P(8), 0))

        recent = self.cfg["recent_dirs"]
        if recent:
            tk.Label(sec, text="最近使ったフォルダ",
                     bg=c["bg2"], fg=c["text3"],
                     font=F(10)).pack(anchor="w", pady=(P(8), 0))
            for d in recent[:3]:
                lbl = tk.Label(sec, text=Path(d).name or d,
                               bg=c["bg2"], fg=ACCENT,
                               font=F(12), cursor="hand2")
                lbl.pack(anchor="w", pady=(P(2), 0))
                lbl.bind("<Button-1>", lambda _e, p=d: self._set_save_dir(p))

        # ── よく使うオプション ─────────────────────────────
        sec, _ = self._section(body, "よく使うオプション", gap_top=P(20))
        for key, lbl in [("playlist",        "プレイリスト全体をDL"),
                         ("embed_thumbnail", "サムネイル埋め込み"),
                         ("embed_subtitles", "字幕をDL・埋め込み")]:
            self._toggle_row(sec, lbl, self._opts_vars[key])

    def _make_mode_card(self, parent, val, label):
        c  = self.theme.c
        on = self._mode_var.get() == val
        tint = self.theme.accent_tint("bg2")
        card = tk.Frame(
            parent, bg=(tint if on else c["bg3"]),
            highlightthickness=P(2) if on else 1,
            highlightbackground=(ACCENT if on else c["border"]),
            cursor="hand2")
        inner = tk.Frame(card, bg=card["bg"])
        inner.pack(padx=P(12), pady=P(10), anchor="w")
        dot = tk.Canvas(inner, width=P(15), height=P(15),
                        bg=card["bg"], highlightthickness=0, bd=0)
        oc = ACCENT if on else c["text3"]
        dot.create_oval(1, 1, P(15)-2, P(15)-2, outline=oc, width=2)
        if on:
            pad = P(4)
            dot.create_oval(pad, pad, P(15)-pad-1, P(15)-pad-1,
                            fill=ACCENT, outline=ACCENT)
        dot.pack(side="left")
        txt = tk.Label(inner, text=label, bg=card["bg"], fg=c["text"],
                       font=F(13))
        txt.pack(side="left", padx=(P(8), 0))
        for w in (card, inner, dot, txt):
            w.bind("<Button-1>", lambda _e, v=val: self._set_mode(v))
        self._mode_cards[val] = card
        return card

    def _set_mode(self, val):
        if self._mode_var.get() == val:
            return
        self._mode_var.set(val)
        self._save_opts()
        # カードを再描画（左タブ再構築で簡潔に反映）
        self._build_left_content()

    def _apply_mode_visuals(self):
        if self._mode_var.get() == "video":
            self._audio_fmt_frame.pack_forget()
            self._video_fmt_frame.pack(fill="x")
        else:
            self._video_fmt_frame.pack_forget()
            self._audio_fmt_frame.pack(fill="x")

    def _toggle_row(self, parent, label, var, command=None):
        c = self.theme.c
        row = tk.Frame(parent, bg=c["bg2"])
        row.pack(fill="x", pady=(P(10), 0))
        tk.Label(row, text=label, bg=c["bg2"], fg=c["text"],
                 font=F(13)).pack(side="left")
        SmoothToggle(row, variable=var, theme=c, bg=c["bg2"],
                     command=command or self._save_opts).pack(side="right")
        return row

    # ══ 詳細設定タブ ══════════════════════════════════════
    def _build_adv_tab(self, body):
        c = self.theme.c

        # ── 字幕・スキップ ─────────────────────────────────
        sec, _ = self._section(body, "字幕・スキップ")
        for key, lbl in [("auto_subtitles", "自動生成字幕もDL"),
                         ("ignore_errors",  "エラーを無視して続行"),
                         ("skip_existing",  "ダウンロード済みをスキップ")]:
            self._toggle_row(sec, lbl, self._opts_vars[key])

        # ── 範囲ダウンロード ───────────────────────────────
        sec, _ = self._section(body, "範囲ダウンロード", gap_top=P(20))
        row = tk.Frame(sec, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        for i, (lbl, var, ph) in enumerate([
                ("開始", self._ts_var, "00:00:00"),
                ("終了", self._te_var, "00:01:30")]):
            col = tk.Frame(row, bg=c["bg2"])
            col.grid(row=0, column=i, sticky="ew",
                     padx=(0, P(10)) if i == 0 else 0)
            row.columnconfigure(i, weight=1)
            tk.Label(col, text=lbl, bg=c["bg2"], fg=c["text3"],
                     font=F(11)).pack(anchor="w")
            self._entry(col, var).pack(fill="x", pady=(P(3), 0))
        tk.Label(sec, text="空白のままなら全体をダウンロード",
                 bg=c["bg2"], fg=c["text3"],
                 font=F(10)).pack(anchor="w", pady=(P(6), 0))

        # ── 暗号化保存 ─────────────────────────────────────
        sec, _ = self._section(body, "暗号化保存", gap_top=P(20))
        self._toggle_row(sec, "ダウンロード後に暗号化",
                         self._encrypt_var,
                         command=self._on_encrypt_change)
        self._encrypt_pw_frame = tk.Frame(sec, bg=c["bg2"])
        self._entry(self._encrypt_pw_frame, self._encrypt_pw_var,
                    show="●").pack(fill="x")
        tk.Label(self._encrypt_pw_frame,
                 text="AES-256で暗号化して .enc 保存（パスワードは保存されません）",
                 bg=c["bg2"], fg=c["text3"],
                 font=F(10)).pack(anchor="w", pady=(P(4), 0))
        dec_row = tk.Frame(self._encrypt_pw_frame, bg=c["bg2"])
        dec_row.pack(fill="x", pady=(P(6), 0))
        self._ghost_btn(dec_row, ".enc ファイルを復号…",
                        self._decrypt_tool).pack(side="left")
        if self._encrypt_var.get():
            self._encrypt_pw_frame.pack(fill="x", pady=(P(8), 0))
        if not CRYPTO_OK:
            tk.Label(sec,
                     text="⚠ pycryptodomex 未導入のため暗号化は利用できません",
                     bg=c["bg2"], fg=WARNING_C,
                     font=F(10)).pack(anchor="w", pady=(P(4), 0))

        # ── ファイル名変更 ─────────────────────────────────
        sec, _ = self._section(body, "ファイル名変更（単体動画のみ）",
                               gap_top=P(20))
        row = tk.Frame(sec, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        self._rename_entry = self._entry(row, self._rename_var)
        self._rename_entry.pack(side="left", fill="x", expand=True)
        self._ghost_btn(row, "クリア",
                        lambda: self._rename_var.set("")).pack(
            side="right", padx=(P(8), 0))
        tk.Label(sec, text="プレイリストまたは複数URL入力時は無効",
                 bg=c["bg2"], fg=c["text3"],
                 font=F(10)).pack(anchor="w", pady=(P(6), 0))
        self._update_rename_state()

        # ── 高度な設定 ─────────────────────────────────────
        sec, _ = self._section(body, "高度な設定", gap_top=P(20))

        def num_row(label, var, lo, hi, unit):
            row = tk.Frame(sec, bg=c["bg2"])
            row.pack(fill="x", pady=(P(8), 0))
            tk.Label(row, text=label, bg=c["bg2"], fg=c["text"],
                     font=F(12), width=10, anchor="w").pack(side="left")
            sb = ttk.Spinbox(row, from_=lo, to=hi, width=5,
                             textvariable=var, font=F(12))
            sb.pack(side="left")
            sb.bind("<FocusOut>", lambda _e: self._save_opts())
            tk.Label(row, text=unit, bg=c["bg2"], fg=c["text3"],
                     font=F(11)).pack(side="left", padx=(P(6), 0))

        num_row("並列DL数",   self._concurrent_var, 1, 8,  "本 (1-8)")
        num_row("自動リトライ", self._retries_var,   0, 10, "回")

        row = tk.Frame(sec, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        tk.Label(row, text="帯域制限", bg=c["bg2"], fg=c["text"],
                 font=F(12), width=10, anchor="w").pack(side="left")
        ent = self._entry(row, self._rate_var)
        ent.pack(side="left", fill="x", expand=True)

        row = tk.Frame(sec, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        ent = self._entry(row, self._cookie_var)
        ent.pack(side="left", fill="x", expand=True)
        self._ghost_btn(row, "…", self._browse_cookie).pack(
            side="right", padx=(P(8), 0))
        tk.Label(sec,
                 text="Cookieファイル → 会員限定・年齢制限コンテンツ等に使用",
                 bg=c["bg2"], fg=c["text3"],
                 font=F(10)).pack(anchor="w", pady=(P(4), 0))

        row = tk.Frame(sec, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        tk.Label(row, text="完了後", bg=c["bg2"], fg=c["text"],
                 font=F(12), width=10, anchor="w").pack(side="left")
        cb = ttk.Combobox(row, textvariable=self._post_action_var,
                          values=POST_ACTIONS, state="readonly",
                          font=F(12))
        cb.pack(side="left", fill="x", expand=True)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._save_opts())

        # ── 設定プリセット ─────────────────────────────────
        sec, _ = self._section(body, "設定プリセット", gap_top=P(20))
        row = tk.Frame(sec, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        self._preset_cb = ttk.Combobox(
            row, textvariable=self._preset_select_var,
            state="readonly", font=F(12))
        self._preset_cb.pack(side="left", fill="x", expand=True)
        self._ghost_btn(row, "読込", self._load_preset).pack(
            side="left", padx=(P(8), 0))
        self._ghost_btn(row, "削除", self._delete_preset).pack(
            side="left", padx=(P(8), 0))
        row = tk.Frame(sec, bg=c["bg2"])
        row.pack(fill="x", pady=(P(8), 0))
        self._entry(row, self._preset_name_var).pack(
            side="left", fill="x", expand=True)
        PillButton(row, text="現在の設定を保存", command=self._save_preset,
                   kind="accent", theme=c, bg=c["bg2"],
                   height=P(29), hpad=P(12), font=F(12)).pack(
            side="left", padx=(P(8), 0))
        self._refresh_preset_list()

        # ── スケジュール実行 ───────────────────────────────
        sec, _ = self._section(body, "スケジュール実行", gap_top=P(20))
        self._toggle_row(sec, "指定時刻に自動開始",
                         self._sched_enable_var,
                         command=self._on_schedule_change)
        self._sched_time_frame = tk.Frame(sec, bg=c["bg2"])
        self._sched_entry = self._entry(
            self._sched_time_frame, self._sched_time_var, width=8)
        self._sched_entry.pack(side="left")
        tk.Label(self._sched_time_frame, text="実行時刻 (HH:MM) 例: 02:30",
                 bg=c["bg2"], fg=c["text3"],
                 font=F(10)).pack(side="left", padx=(P(8), 0))
        self._sched_status_lbl = tk.Label(
            sec, text="", bg=c["bg2"], fg=ACCENT, font=F(10))
        self._sched_status_lbl.pack(anchor="w", pady=(P(4), 0))
        if self._sched_enable_var.get():
            self._sched_time_frame.pack(fill="x", pady=(P(8), 0))

    def _on_encrypt_change(self):
        self._save_opts()
        if not hasattr(self, "_encrypt_pw_frame") \
                or not self._encrypt_pw_frame.winfo_exists():
            return
        if self._encrypt_var.get():
            self._encrypt_pw_frame.pack(fill="x", pady=(P(8), 0))
        else:
            self._encrypt_pw_frame.pack_forget()

    # ══════════════════════════════════════════════════════
    #  右パネル
    # ══════════════════════════════════════════════════════

    def _build_right_panel(self):
        c = self.theme.c
        p = self.right_frame
        pad = tk.Frame(p, bg=c["bg1"])
        pad.pack(fill="both", expand=True, padx=P(20), pady=P(16))

        # ── アクションバー（常時表示） ──────────────────────
        bar = tk.Frame(pad, bg=c["bg1"])
        bar.pack(fill="x")
        onboarding = not self.cfg["onboarding_done"]
        self._dl_btn = PillButton(
            bar, text="▶  ダウンロード開始", command=self._start_download,
            kind="accent", theme=c, bg=c["bg1"],
            height=P(38), hpad=P(22), font=F(13, True))
        self._dl_btn.pack(side="left")
        self._stop_btn = PillButton(
            bar, text="■ 停止", command=self._stop_download,
            kind="outline", theme=c, bg=c["bg1"],
            height=P(38), hpad=P(18), font=F(13),
            outline_color=ERROR_C, text_color=ERROR_C)
        self._stop_btn.pack(side="left", padx=(P(10), 0))
        self._retry_btn = PillButton(
            bar, text="↻ 再試行", command=self._retry_failed,
            kind="outline", theme=c, bg=c["bg1"],
            height=P(38), hpad=P(18), font=F(13))
        self._retry_btn.pack(side="left", padx=(P(10), 0))
        clear = tk.Label(bar, text="🗑 クリア", bg=c["bg1"], fg=c["text2"],
                         font=F(13), cursor="hand2", padx=P(16))
        clear.pack(side="right")
        clear.bind("<Button-1>", lambda _e: self._clear_queue())

        # ── ステータスカード ────────────────────────────────
        card = tk.Frame(pad, bg=c["bg2"],
                        highlightthickness=1,
                        highlightbackground=c["border"])
        card.pack(fill="x", pady=(P(12), 0))
        ci = tk.Frame(card, bg=c["bg2"])
        ci.pack(fill="x", padx=P(16), pady=P(14))
        head = tk.Frame(ci, bg=c["bg2"])
        head.pack(fill="x")
        self._overall_dot = Dot(head, P(8), c["text3"], c["bg2"])
        self._overall_dot.pack(side="left", pady=P(4))
        self._overall_lbl = tk.Label(
            head, text="待機中", bg=c["bg2"], fg=c["text"],
            font=F(14, True))
        self._overall_lbl.pack(side="left", padx=(P(10), 0))
        self._overall_bar = SlimProgressBar(
            ci, height=P(8), trough=c["bg4"], color=c["text3"], bg=c["bg2"])
        self._overall_bar.pack(fill="x", pady=(P(8), 0))
        meta = tk.Frame(ci, bg=c["bg2"])
        meta.pack(fill="x", pady=(P(8), 0))
        self._overall_speed_lbl = tk.Label(
            meta, text="速度: —", bg=c["bg2"], fg=c["text2"], font=F(12))
        self._overall_speed_lbl.pack(side="left")
        self._overall_eta_lbl = tk.Label(
            meta, text="残り時間: —", bg=c["bg2"], fg=c["text2"], font=F(12))
        self._overall_eta_lbl.pack(side="left", padx=(P(20), 0))

        # ── 右タブバー ─────────────────────────────────────
        tab_holder = tk.Frame(pad, bg=c["bg1"])
        tab_holder.pack(fill="x", pady=(P(12), 0))
        self._right_tabbar = TabBar(
            tab_holder,
            items=[("queue",   "キュー"),
                   ("graph",   "速度グラフ"),
                   ("log",     "ログ"),
                   ("history", "ダウンロード履歴")],
            active=self._right_tab,
            command=self._on_right_tab,
            theme=c, bg=c["bg1"], font_px=12,
            padx=P(14), pady=P(9))
        self._right_tabbar.pack(side="left")
        tk.Frame(pad, bg=c["border"], height=1).pack(fill="x")

        # ── コンテンツカード ────────────────────────────────
        self._right_card = tk.Frame(
            pad, bg=c["bg2"],
            highlightthickness=1, highlightbackground=c["border"])
        self._right_card.pack(fill="both", expand=True, pady=(P(12), 0))
        self._build_right_content()

    def _on_right_tab(self, key):
        self._right_tab = key
        self._build_right_content()

    def _build_right_content(self):
        for w in self._right_card.winfo_children():
            w.destroy()
        self._queue_rows.clear()
        if self._right_tab == "queue":
            self._build_queue_view(self._right_card)
        elif self._right_tab == "graph":
            self._build_graph_view(self._right_card)
        elif self._right_tab == "log":
            self._build_log_view(self._right_card)
        else:
            self._build_history_view(self._right_card)

    # ── キュービュー ───────────────────────────────────────
    QUEUE_COLS = (20, 110, 130, 80, 60)   # #, 状態, 進捗, 速度, 残り

    def _build_queue_view(self, parent):
        c = self.theme.c
        if not self.tasks:
            empty = tk.Frame(parent, bg=c["bg2"])
            empty.pack(fill="both", expand=True)
            box = tk.Frame(empty, bg=c["bg2"])
            box.place(relx=0.5, rely=0.5, anchor="center")
            cv = tk.Canvas(box, width=P(48), height=P(48),
                           bg=c["bg2"], highlightthickness=0, bd=0)
            cv.create_oval(P(2), P(2), P(46), P(46),
                           outline=c["border"], width=2)
            # 下向き矢印（シェブロン）
            cx, cy, s = P(24), P(22), P(6)
            cv.create_line(cx-s, cy, cx, cy+s, cx+s, cy,
                           fill=c["text3"], width=2)
            cv.pack()
            tk.Label(box, text="URLを貼り付けてダウンロードを開始してください",
                     bg=c["bg2"], fg=c["text3"],
                     font=F(13)).pack(pady=(P(10), 0))
            return

        # ヘッダー行
        hdr = tk.Frame(parent, bg=c["bg2"])
        hdr.pack(fill="x")
        hi = tk.Frame(hdr, bg=c["bg2"])
        hi.pack(fill="x", padx=P(16), pady=(P(9), P(9)))
        widths = self.QUEUE_COLS
        cols = [("#", widths[0]), (None, 0), ("状態", widths[1]),
                ("進捗", widths[2]), ("速度", widths[3]), ("残り", widths[4])]
        for text, wpx in cols:
            if text is None:
                tk.Label(hi, text="タイトル / URL", bg=c["bg2"],
                         fg=c["text3"], font=F(10, True),
                         anchor="w").pack(side="left", fill="x",
                                          expand=True, padx=(P(12), P(12)))
            else:
                f = tk.Frame(hi, bg=c["bg2"], width=P(wpx))
                f.pack(side="left")
                f.pack_propagate(False)
                f.configure(height=P(14))
                tk.Label(f, text=text, bg=c["bg2"], fg=c["text3"],
                         font=F(10, True), anchor="w").pack(fill="x")
        tk.Frame(parent, bg=c["border"], height=1).pack(fill="x")

        self._queue_scroll = ScrollFrame(parent, bg=c["bg2"])
        self._queue_scroll.pack(fill="both", expand=True)
        for task in self.tasks:
            self._add_queue_row(task)

    def _add_queue_row(self, task: DownloadTask):
        if not hasattr(self, "_queue_scroll") \
                or not self._queue_scroll.winfo_exists():
            return
        row = QueueRow(self._queue_scroll.inner, self, task)
        row.pack(fill="x")
        self._queue_rows[task.idx] = row

    def _update_queue_row(self, task: DownloadTask):
        row = self._queue_rows.get(task.idx)
        if row and row.winfo_exists():
            row.update_view(task)

    def _refresh_queue_view(self):
        """タスク一覧が変わったときにキュービューを再構築"""
        if self._right_tab == "queue":
            self._build_right_content()

    # ── 速度グラフビュー ───────────────────────────────────
    def _build_graph_view(self, parent):
        c = self.theme.c
        holder = tk.Frame(parent, bg=c["bg2"])
        holder.pack(fill="both", expand=True, padx=P(20), pady=P(20))
        tk.Label(holder, text="現在の合計速度",
                 bg=c["bg2"], fg=c["text2"], font=F(12)).pack(anchor="w")
        self._graph_big_lbl = tk.Label(
            holder, text="—", bg=c["bg2"], fg=c["text"], font=F(28, True))
        self._graph_big_lbl.pack(anchor="w")
        self._graph_canvas = tk.Canvas(
            holder, bg=c["bg2"], highlightthickness=0, bd=0)
        self._graph_canvas.pack(fill="both", expand=True, pady=(P(14), 0))
        self._graph_canvas.bind("<Configure>", lambda _e: self._draw_graph())
        self._draw_graph()

    def _graph_tick(self):
        """1秒ごとに合計速度を記録してグラフ更新"""
        self._speed_history.append(self._cur_speed_mbps)
        if len(self._speed_history) > 120:
            self._speed_history.pop(0)
        if hasattr(self, "_graph_canvas") \
                and self._graph_canvas.winfo_exists():
            self._draw_graph()
            spd = self._cur_speed_mbps
            self._graph_big_lbl.config(
                text=f"{spd:.1f} MB/s" if spd > 0 else "—")
        self.root.after(1000, self._graph_tick)

    def _draw_graph(self):
        if not hasattr(self, "_graph_canvas") \
                or not self._graph_canvas.winfo_exists():
            return
        cv = self._graph_canvas
        cv.delete("all")
        w = cv.winfo_width()
        h = cv.winfo_height()
        if w < 40 or h < 30:
            return
        pts = self._speed_history[-24:]
        n_bars = 24
        gap = P(5)
        bw  = max(2, (w - gap * (n_bars - 1)) // n_bars)
        max_v = max(6.0, max(pts) if pts else 0.0)
        for i in range(n_bars):
            idx = len(pts) - n_bars + i
            v = pts[idx] if idx >= 0 else 0.0
            bh = max(P(2), int(h * (v / max_v))) if v > 0 else P(2)
            x0 = i * (bw + gap)
            cv.create_rectangle(x0, h - bh, x0 + bw, h,
                                fill=ACCENT, outline=ACCENT)

    # ── ログビュー ─────────────────────────────────────────
    def _build_log_view(self, parent):
        c = self.theme.c
        holder = tk.Frame(parent, bg=c["bg2"])
        holder.pack(fill="both", expand=True, padx=P(16), pady=P(16))
        head = tk.Frame(holder, bg=c["bg2"])
        head.pack(fill="x")
        tk.Label(head, text="yt-dlp 出力ログ", bg=c["bg2"], fg=c["text2"],
                 font=F(12)).pack(side="left")
        self._ghost_btn(head, "クリア", self._clear_log).pack(side="right")
        self._ghost_btn(head, "保存", self._export_log).pack(
            side="right", padx=(0, P(8)))

        txt_holder = tk.Frame(holder, bg=c["bg3"])
        txt_holder.pack(fill="both", expand=True, pady=(P(10), 0))
        self._log_text = AutoScrollText(
            txt_holder,
            bg=c["bg3"], fg=c["text2"],
            font=FMONO(12),
            insertbackground=c["text"],
            selectbackground=ACCENT,
            relief="flat", bd=0,
            padx=P(12), pady=P(10),
            state="disabled", wrap="word")
        vsb = ttk.Scrollbar(txt_holder, orient="vertical",
                            command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True)
        for tag, color in [("info", ACCENT), ("warn", WARNING_C),
                           ("error", ERROR_C), ("done", SUCCESS_C),
                           ("dim", c["text3"])]:
            self._log_text.tag_configure(tag, foreground=color)
        # 既存ログを復元
        self._log_text.config(state="normal")
        for text, tag in self._log_lines[-500:]:
            self._log_text.insert("end", text + "\n", tag or ())
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    # ── 履歴ビュー ─────────────────────────────────────────
    def _build_history_view(self, parent):
        c = self.theme.c
        holder = tk.Frame(parent, bg=c["bg2"])
        holder.pack(fill="both", expand=True, padx=P(16), pady=(P(10), P(16)))
        head = tk.Frame(holder, bg=c["bg2"])
        head.pack(fill="x")
        tk.Label(head, text="ダブルクリックでURLをコピー",
                 bg=c["bg2"], fg=c["text3"], font=F(10)).pack(side="left")
        self._ghost_btn(head, "履歴クリア", self._clear_history).pack(
            side="right")

        sc = ScrollFrame(holder, bg=c["bg2"])
        sc.pack(fill="both", expand=True, pady=(P(6), 0))
        hist = self.cfg["history"]
        if not hist:
            tk.Label(sc.inner, text="履歴はまだありません",
                     bg=c["bg2"], fg=c["text3"], font=F(12)).pack(
                pady=P(24))
            return
        for entry in hist:
            self._add_history_row(sc.inner, entry)

    def _add_history_row(self, parent, entry: dict):
        c = self.theme.c
        row = tk.Frame(parent, bg=c["bg2"])
        row.pack(fill="x")
        ri = tk.Frame(row, bg=c["bg2"])
        ri.pack(fill="x", padx=P(4), pady=P(10))
        left = tk.Frame(ri, bg=c["bg2"])
        left.pack(side="left", fill="x", expand=True)
        title = entry.get("title", "") or entry.get("url", "")
        tk.Label(left, text=title[:80], bg=c["bg2"], fg=c["text"],
                 font=F(13), anchor="w").pack(fill="x")
        sub = f'{entry.get("date","")}   {entry.get("url","")[:70]}'
        tk.Label(left, text=sub, bg=c["bg2"], fg=c["text3"],
                 font=F(11), anchor="w").pack(fill="x")
        status = entry.get("status", "")
        ok = "完了" in status
        tk.Label(ri, text=status, bg=c["bg2"],
                 fg=SUCCESS_C if ok else ERROR_C,
                 font=F(12)).pack(side="right")
        tk.Frame(parent, bg=c["border"], height=1).pack(fill="x")
        url = entry.get("url", "")
        for w in (row, ri, left):
            w.bind("<Double-1>", lambda _e, u=url: self._copy_url(u))

    def _copy_url(self, url: str):
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self._set_status(f"URLをコピーしました: {url[:60]}")

    # ── ステータスバー（26px） ─────────────────────────────
    def _build_statusbar(self):
        c = self.theme.c
        sb = tk.Frame(self.root, bg=c["bg2"], height=P(26))
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        tk.Frame(self.root, bg=c["border"], height=1).pack(
            fill="x", side="bottom")

        left = tk.Frame(sb, bg=c["bg2"])
        left.pack(side="left", padx=P(16))
        self._status_dot = Dot(left, P(6), c["text3"], c["bg2"])
        self._status_dot.pack(side="left", pady=P(10))
        self._status_lbl = tk.Label(
            left, text="待機中", bg=c["bg2"], fg=c["text2"],
            font=F(11), anchor="w")
        self._status_lbl.pack(side="left", padx=(P(8), 0))

        right = tk.Frame(sb, bg=c["bg2"])
        right.pack(side="right", padx=P(16))
        available = resolve_ytdlp_cmd() is not None
        if available:
            ver = self._ytdlp_ver or get_ytdlp_version()
            tk.Label(right, text="✓", bg=c["bg2"], fg=SUCCESS_C,
                     font=F(11)).pack(side="right")
            self._ytdlp_ver_lbl = tk.Label(
                right,
                text=f"yt-dlp v{ver}" if ver else "yt-dlp",
                bg=c["bg2"], fg=c["text2"], font=F(11))
            self._ytdlp_ver_lbl.pack(side="right", padx=(0, P(4)))
            tk.Label(right, text="|", bg=c["bg2"], fg=c["border"],
                     font=F(11)).pack(side="right", padx=P(8))
            upd = tk.Label(right, text="更新確認", bg=c["bg2"], fg=ACCENT,
                           font=F(11), cursor="hand2")
            upd.pack(side="right")
            upd.bind("<Button-1>", lambda _e: self._show_update_dialog())
        else:
            tk.Label(right, text="yt-dlp ✗ 未インストール",
                     bg=c["bg2"], fg=ERROR_C,
                     font=F(11)).pack(side="right")

    def _set_status(self, text: str):
        if hasattr(self, "_status_lbl") and self._status_lbl.winfo_exists():
            self._status_lbl.config(text=text)

    # ══════════════════════════════════════════════════════
    #  設定保存・復元
    # ══════════════════════════════════════════════════════

    def _save_opts(self):
        if not hasattr(self, "_save_var"):
            return
        try:
            self.cfg["mode"]        = self._mode_var.get()
            self.cfg["video_fmt"]   = self._vfmt_var.get()
            self.cfg["audio_fmt"]   = self._afmt_var.get()
            self.cfg["quality"]     = self._quality_var.get()
            self.cfg["save_dir"]    = self._save_var.get()
            self.cfg["time_start"]  = self._ts_var.get()
            self.cfg["time_end"]    = self._te_var.get()
            self.cfg["rate_limit"]  = self._rate_var.get()
            self.cfg["cookie_file"] = self._cookie_var.get()
            self.cfg["post_action"] = self._post_action_var.get()
            self.cfg["encrypt_enable"]  = self._encrypt_var.get()
            self.cfg["schedule_enable"] = self._sched_enable_var.get()
            self.cfg["schedule_time"]   = self._sched_time_var.get()
            for k, v in self._opts_vars.items():
                self.cfg[k] = v.get()
        except tk.TclError:
            return
        # Spinbox は空欄・文字入力で TclError になるので個別に検証し、
        # 不正なら直前の値に戻す
        for key, var, lo, hi in (("concurrent", self._concurrent_var, 1, 8),
                                 ("retries",    self._retries_var,    0, 10)):
            try:
                val = max(lo, min(hi, int(var.get())))
            except (tk.TclError, ValueError):
                val = self.cfg[key]
            self.cfg[key] = val
            try:
                if var.get() != val:
                    var.set(val)
            except tk.TclError:
                var.set(val)
        self.cfg.save()

    # ══════════════════════════════════════════════════════
    #  URL 操作
    # ══════════════════════════════════════════════════════

    def _get_urls(self) -> List[str]:
        self._sync_url_content()
        return extract_urls(self._url_content)

    def _on_url_edited(self):
        self._sync_url_content()
        self._update_url_count()
        self._update_rename_state()
        self._update_action_states()

    def _update_url_count(self):
        if not hasattr(self, "_url_count_lbl") \
                or not self._url_count_lbl.winfo_exists():
            return
        c = self.theme.c
        n = len(extract_urls(self._url_content))
        if n == 0:
            self._url_count_lbl.config(text="0 URL", fg=c["text3"])
        else:
            self._url_count_lbl.config(text=f"{n} URL", fg=ACCENT)

    def _clear_urls(self):
        self._url_content = ""
        if hasattr(self, "url_text") and self.url_text.winfo_exists():
            self.url_text.delete("1.0", "end")
        self._on_url_edited()

    def _paste_clipboard(self):
        try:
            txt = self.root.clipboard_get()
            urls = extract_urls(txt)
            if urls:
                if hasattr(self, "url_text") and self.url_text.winfo_exists():
                    cur = self.url_text.get("1.0", "end-1c")
                    if cur and not cur.endswith("\n"):
                        self.url_text.insert("end", "\n")
                    self.url_text.insert("end", "\n".join(urls) + "\n")
                else:
                    if self._url_content and not self._url_content.endswith("\n"):
                        self._url_content += "\n"
                    self._url_content += "\n".join(urls) + "\n"
                self._on_url_edited()
                self._log(f"クリップボードから {len(urls)} URL を追加", "info")
        except Exception:
            pass

    _last_clip = ""

    def _watch_clipboard(self):
        try:
            clip = self.root.clipboard_get()
            if clip != self._last_clip:
                self._last_clip = clip
                urls = extract_urls(clip)
                if urls and not self._running:
                    self._set_status(
                        f"📋 クリップボード: {len(urls)} URLを検出")
        except Exception:
            pass
        self.root.after(1500, self._watch_clipboard)

    # ══════════════════════════════════════════════════════
    #  リネーム状態
    # ══════════════════════════════════════════════════════

    def _update_rename_state(self):
        if not hasattr(self, "_rename_entry"):
            return
        try:
            if not self._rename_entry.winfo_exists():
                return
        except Exception:
            return
        playlist_on = self._opts_vars["playlist"].get()
        url_count = len(extract_urls(self._url_content))
        if playlist_on or url_count > 1:
            self._rename_entry.config(state="disabled")
            self._rename_var.set("")
        else:
            self._rename_entry.config(state="normal")

    # ══════════════════════════════════════════════════════
    #  保存先
    # ══════════════════════════════════════════════════════

    def _browse_dir(self):
        d = filedialog.askdirectory(
            initialdir=self.cfg["save_dir"],
            title="保存先を選択")
        if d:
            self._set_save_dir(d)

    def _set_save_dir(self, path: str):
        self._save_var.set(path)
        self._save_opts()

    def _browse_cookie(self):
        p = filedialog.askopenfilename(
            title="Cookie ファイルを選択",
            filetypes=[("テキスト", "*.txt"), ("すべて", "*.*")])
        if p:
            self._cookie_var.set(p)
            self._save_opts()

    # ══════════════════════════════════════════════════════
    #  プリセット
    # ══════════════════════════════════════════════════════

    def _refresh_preset_list(self):
        if not hasattr(self, "_preset_cb") \
                or not self._preset_cb.winfo_exists():
            return
        names = list(self.cfg["presets"].keys())
        self._preset_cb["values"] = names
        if names and self._preset_select_var.get() not in names:
            self._preset_select_var.set(names[0])

    def _save_preset(self):
        name = self._preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("警告", "プリセット名を入力してください。")
            return
        self._save_opts()
        snapshot = {k: self.cfg[k] for k in (
            "mode", "video_fmt", "audio_fmt", "quality",
            "playlist", "embed_thumbnail", "embed_subtitles",
            "auto_subtitles", "ignore_errors", "skip_existing",
            "time_start", "time_end", "concurrent", "retries",
            "rate_limit", "post_action", "encrypt_enable")}
        presets = self.cfg["presets"]
        presets[name] = snapshot
        self.cfg["presets"] = presets
        self.cfg.save()
        self._refresh_preset_list()
        self._preset_select_var.set(name)
        self._log(f"プリセット「{name}」を保存しました", "info")

    def _load_preset(self):
        name = self._preset_select_var.get()
        if not name:
            return
        preset = self.cfg["presets"].get(name)
        if not preset:
            return
        self._mode_var.set(preset.get("mode", "video"))
        vfmt = preset.get("video_fmt", VIDEO_AUTO)
        self._vfmt_var.set(VIDEO_AUTO if vfmt in ("auto", "") else vfmt)
        self._afmt_var.set(preset.get("audio_fmt", "mp3"))
        self._quality_var.set(preset.get("quality", "最高品質"))
        self._ts_var.set(preset.get("time_start", ""))
        self._te_var.set(preset.get("time_end", ""))
        self._concurrent_var.set(preset.get("concurrent", 2))
        self._retries_var.set(preset.get("retries", 3))
        self._rate_var.set(preset.get("rate_limit", ""))
        self._post_action_var.set(preset.get("post_action", "何もしない"))
        self._encrypt_var.set(preset.get("encrypt_enable", False))
        for key in ("playlist", "embed_thumbnail", "embed_subtitles",
                    "auto_subtitles", "ignore_errors", "skip_existing"):
            if key in self._opts_vars:
                self._opts_vars[key].set(preset.get(key, False))
        self._save_opts()
        self._log(f"プリセット「{name}」を読み込みました", "info")

    def _delete_preset(self):
        name = self._preset_select_var.get()
        if not name:
            return
        if not messagebox.askyesno("確認", f"プリセット「{name}」を削除しますか？"):
            return
        presets = self.cfg["presets"]
        presets.pop(name, None)
        self.cfg["presets"] = presets
        self.cfg.save()
        self._refresh_preset_list()
        self._log(f"プリセット「{name}」を削除しました", "warn")

    # ══════════════════════════════════════════════════════
    #  スケジュール実行
    # ══════════════════════════════════════════════════════

    def _on_schedule_change(self):
        self._save_opts()
        if not hasattr(self, "_sched_time_frame") \
                or not self._sched_time_frame.winfo_exists():
            return
        if self._sched_enable_var.get():
            self._sched_time_frame.pack(fill="x", pady=(P(8), 0))
        else:
            self._sched_time_frame.pack_forget()
            if self._sched_status_lbl.winfo_exists():
                self._sched_status_lbl.config(text="")

    def _schedule_tick(self):
        """10秒ごとにチェックして指定時刻になったらDLを開始する"""
        if self._sched_enable_var.get():
            now_str = datetime.now().strftime("%H:%M")
            target  = self._sched_time_var.get().strip()
            lbl_ok = (hasattr(self, "_sched_status_lbl")
                      and self._sched_status_lbl.winfo_exists())
            if re.match(r'^\d{2}:\d{2}$', target):
                remaining = self._calc_schedule_remaining(target)
                if lbl_ok:
                    self._sched_status_lbl.config(
                        text=f"⏰ {target} に開始 (あと {remaining})")
                if now_str == target and not self._running:
                    self._log(f"⏰ スケジュール実行: {target}", "info")
                    self._sched_enable_var.set(False)
                    self._save_opts()
                    self.root.after(100, self._start_download)
            elif lbl_ok:
                self._sched_status_lbl.config(
                    text="⚠ 時刻形式が無効です（HH:MM）")
        self.root.after(10000, self._schedule_tick)

    @staticmethod
    def _calc_schedule_remaining(target: str) -> str:
        try:
            from datetime import timedelta
            now = datetime.now()
            h, m = map(int, target.split(":"))
            t = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if t <= now:
                t += timedelta(days=1)
            diff = int((t - now).total_seconds())
            return f"{diff//3600}h{diff%3600//60}m"
        except Exception:
            return "?"

    # ══════════════════════════════════════════════════════
    #  暗号化保存 復号ツール
    # ══════════════════════════════════════════════════════

    def _decrypt_tool(self):
        if not CRYPTO_OK:
            messagebox.showerror(
                "エラー",
                "pycryptodomex がインストールされていません。\n"
                "pip install pycryptodomex を実行してください。")
            return
        p = filedialog.askopenfilename(
            title="復号する .enc ファイルを選択",
            initialdir=self.cfg["save_dir"],
            filetypes=[("暗号化ファイル", "*.enc"), ("すべて", "*.*")])
        if not p:
            return
        c = self.theme.c
        win = tk.Toplevel(self.root)
        win.title("復号")
        win.configure(bg=c["bg1"])
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text=Path(p).name, bg=c["bg1"], fg=c["text"],
                 font=F(12)).pack(padx=P(20), pady=(P(16), P(4)))
        tk.Label(win, text="パスワードを入力", bg=c["bg1"], fg=c["text2"],
                 font=F(11)).pack(padx=P(20))
        pw_var = tk.StringVar()
        ent = ttk.Entry(win, textvariable=pw_var, show="●", font=F(12),
                        width=28)
        ent.pack(padx=P(20), pady=P(8))
        ent.focus_set()

        def do_decrypt():
            pw = pw_var.get()
            if not pw:
                return
            try:
                out = decrypt_file(Path(p), pw)
                self._log(f"🔓 復号しました: {out.name}", "done")
                messagebox.showinfo("復号完了",
                                    f"復号しました:\n{out}", parent=win)
                win.destroy()
            except Exception as e:
                messagebox.showerror("復号失敗", str(e), parent=win)

        btn_row = tk.Frame(win, bg=c["bg1"])
        btn_row.pack(pady=(P(4), P(16)))
        PillButton(btn_row, text="復号する", command=do_decrypt,
                   kind="accent", theme=c, bg=c["bg1"],
                   height=P(32), hpad=P(16), font=F(12)).pack()
        ent.bind("<Return>", lambda _e: do_decrypt())

    # ══════════════════════════════════════════════════════
    #  ダウンロード制御
    # ══════════════════════════════════════════════════════

    def _start_download(self):
        if resolve_ytdlp_cmd() is None:
            if getattr(sys, "frozen", False):
                msg = (f"yt-dlp.exe が見つかりません。\n"
                       f"{APP_DIR} に yt-dlp.exe を配置してください。")
            else:
                msg = ("yt-dlp がインストールされていません。\n"
                       "pip install yt-dlp を実行してください。")
            messagebox.showerror("エラー", msg)
            return

        if self._updating:
            messagebox.showwarning(
                "警告", "yt-dlp の更新中はダウンロードを開始できません。")
            return

        self._save_opts()
        urls = self._get_urls()
        if not urls:
            messagebox.showwarning("警告", "URLが入力されていません。")
            return

        # 暗号化保存が有効なのにパスワード未入力なら確認
        if self._encrypt_var.get() and not self._encrypt_pw_var.get():
            messagebox.showwarning(
                "暗号化保存",
                "暗号化保存が有効ですがパスワードが未入力です。\n"
                "詳細設定タブでパスワードを入力してください。")
            return

        # ③ URL 重複・無効チェック
        issues = self._check_urls(urls)
        if issues:
            msg = "\n".join(issues[:10])
            if len(issues) > 10:
                msg += f"\n…他 {len(issues)-10} 件"
            if not messagebox.askyesno(
                "URL の問題を検出",
                f"以下の問題が見つかりました。続行しますか？\n\n{msg}"):
                return

        save_dir = self.cfg["save_dir"]
        if not Path(save_dir).exists():
            try:
                Path(save_dir).mkdir(parents=True)
            except Exception as e:
                messagebox.showerror("エラー", f"保存先を作成できません:\n{e}")
                return

        self.cfg.add_recent_dir(save_dir)

        playlist_on = self.cfg["playlist"]

        # リネーム（単体かつプレイリストOFF時のみ有効）
        rename_name = ""
        if not playlist_on and len(urls) == 1:
            rename_name = self._rename_var.get()

        # 重複チェック：DL中・待機中のURLはスキップ、エラー・完了は再DL可
        active_urls = {
            t.url for t in self.tasks
            if t.state in (TaskState.DOWNLOADING, TaskState.CONVERTING,
                           TaskState.PENDING,     TaskState.RETRYING)
        }
        new_tasks = []
        for url in urls:
            if url in active_urls:
                self._log(f"スキップ（DL中/待機中）: {url[:60]}", "warn")
                continue
            task = DownloadTask(url=url, idx=len(self.tasks),
                                rename=rename_name)
            self.tasks.append(task)
            new_tasks.append(task)
            self._add_queue_row(task)

        if not new_tasks:
            self._log("追加するURLはすべて既にキューにあります", "warn")
            return

        # オンボーディングは初回DL開始で恒久的に非表示へ
        self._dismiss_onboarding()

        # キュービューが空表示のままなら再構築
        if self._right_tab == "queue" and not self._queue_rows:
            self._refresh_queue_view()

        self._log(f"▶ {len(new_tasks)} 件のダウンロードを開始", "info")
        self._running = True
        self.dl.encrypt_password = (
            self._encrypt_pw_var.get() if self._encrypt_var.get() else "")
        self.dl.reset()
        self._launch_tasks(new_tasks)
        self._update_overall()
        self._update_action_states()

    def _launch_tasks(self, tasks: List[DownloadTask]):
        for task in tasks:
            t = threading.Thread(
                target=self._run_and_check,
                args=(task,),
                daemon=True,
                name=f"dl-{task.idx}",
            )
            self.threads.append(t)
            t.start()

    def _run_and_check(self, task: DownloadTask):
        self.dl.run_task(task)
        self.root.after(0, self._check_all_done)

    # ── URL 重複・無効チェック ────────────────────────────
    def _check_urls(self, urls: List[str]) -> List[str]:
        issues: List[str] = []
        seen: set = set()
        # 【セキュリティ】http/https のみ許可（file:// ftp:// 等を明示拒否）
        allowed_schemes = ("http://", "https://")
        for url in urls:
            if not any(url.startswith(s) for s in allowed_schemes):
                issues.append(f"無効なURL形式（http/https のみ許可）: {url[:60]}")
            elif len(url) < 12:
                issues.append(f"URLが短すぎます: {url}")
            elif url in seen:
                issues.append(f"重複URL: {url[:60]}")
            seen.add(url)
        return issues

    def _check_all_done(self):
        if not self.tasks:
            return
        all_done = all(
            t.state in (TaskState.DONE, TaskState.ERROR,
                        TaskState.CANCELLED, TaskState.PAUSED)
            for t in self.tasks
        )
        if all_done and self._running:
            self._running = False
            done   = sum(1 for t in self.tasks if t.state == TaskState.DONE)
            errors = sum(1 for t in self.tasks if t.state == TaskState.ERROR)
            paused = sum(1 for t in self.tasks if t.state == TaskState.PAUSED)
            if not paused:
                self._log(
                    f"✓ 全ダウンロード完了 ({done}/{len(self.tasks)}件成功"
                    + (f", {errors}件エラー" if errors else "") + ")", "done")
                desktop_notify("yt-dlp GUI",
                    f"ダウンロード完了: {done}/{len(self.tasks)}件")
                self._run_post_action()
        self._update_overall()
        self._update_action_states()

    def _run_post_action(self):
        action = self.cfg.get("post_action", "何もしない") or ""
        if "フォルダ" in action:
            save_dir = self.cfg["save_dir"]
            try:
                if IS_WIN:
                    os.startfile(save_dir)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", save_dir])
                else:
                    subprocess.Popen(["xdg-open", save_dir])
            except Exception as e:
                self._log(f"フォルダを開けませんでした: {e}", "warn")
        elif "スリープ" in action:
            if messagebox.askyesno(
                "スリープ確認",
                "ダウンロードが完了しました。\nPCをスリープしますか？"):
                try:
                    if IS_WIN:
                        subprocess.Popen(
                            ["rundll32.exe", "powrprof.dll,SetSuspendState",
                             "0", "1", "0"])
                    elif sys.platform == "darwin":
                        subprocess.Popen(["pmset", "sleepnow"])
                    else:
                        subprocess.Popen(["systemctl", "suspend"])
                except Exception as e:
                    self._log(f"スリープに失敗しました: {e}", "error")
        elif "シャットダウン" in action:
            if messagebox.askyesno(
                "シャットダウン確認",
                "ダウンロードが完了しました。\nパソコンをシャットダウンしますか？"):
                try:
                    if IS_WIN:
                        subprocess.Popen(["shutdown", "/s", "/t", "30"])
                        messagebox.showinfo(
                            "シャットダウン",
                            "30秒後にシャットダウンします。\n"
                            "キャンセル: shutdown /a をコマンドプロンプトで実行")
                    elif sys.platform == "darwin":
                        subprocess.Popen(
                            ["osascript", "-e",
                             'tell application "System Events" to shut down'])
                    else:
                        subprocess.Popen(["shutdown", "-h", "+1"])
                except Exception as e:
                    self._log(f"シャットダウンに失敗しました: {e}", "error")

    # ── ログ書き出し ────────────────────────────────────
    def _export_log(self):
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"ytdlp_log_{ts}.txt"
        path = filedialog.asksaveasfilename(
            title="ログを保存",
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("テキスト", "*.txt"), ("すべて", "*.*")])
        if not path:
            return
        try:
            content = "\n".join(t for t, _ in self._log_lines)
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(content)
            self._log(f"ログを保存しました: {path}", "info")
        except Exception as e:
            messagebox.showerror("エラー", f"ログの保存に失敗しました:\n{e}")

    def _stop_download(self):
        """停止 = 進行中のタスクを一時停止（削除はしない）"""
        self.dl.stop()
        self._log("■ ダウンロードを停止しました（一時停止）", "warn")
        self._running = False
        for t in self.tasks:
            if t.state in (TaskState.DOWNLOADING, TaskState.CONVERTING,
                           TaskState.RETRYING, TaskState.PENDING):
                t.state = TaskState.PAUSED
                self._update_queue_row(t)
        self._update_overall()
        self._update_action_states()

    def _cleanup_partial_files(self):
        """中間ファイル（.fXXX.*）を削除する（キュークリア時）"""
        save_dir = Path(self.cfg["save_dir"])
        if not save_dir.exists():
            return
        partial_pat = re.compile(r'\.f\d+\.\w+$')
        count = 0
        for f in save_dir.iterdir():
            if f.is_file() and partial_pat.search(f.name):
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
        if count:
            self._log(f"🧹 中間ファイル {count} 件を削除しました", "info")

    def _retry_failed(self):
        """エラー・一時停止・中断のタスクをまとめて再試行"""
        failed = [t for t in self.tasks
                  if t.state in (TaskState.ERROR, TaskState.PAUSED,
                                 TaskState.CANCELLED)]
        if not failed:
            return
        self._restart_tasks(failed)
        self._log(f"↻ {len(failed)} 件を再試行", "info")

    def _retry_task(self, task: DownloadTask):
        """キュー行のインライン再試行（この1件のみ）"""
        if task.state not in (TaskState.ERROR, TaskState.PAUSED,
                              TaskState.CANCELLED):
            return
        self._restart_tasks([task])
        self._log(f"↻ 再試行: {task.display_name()}", "info")

    def _restart_tasks(self, tasks: List[DownloadTask]):
        for task in tasks:
            task.state    = TaskState.PENDING
            task.progress = 0.0
            task.error    = ""
            task.retry    = 0
            task.speed    = ""
            task.eta      = ""
            self._update_queue_row(task)
        if not self._running:
            self.dl.reset()
        self._running = True
        self.dl.encrypt_password = (
            self._encrypt_pw_var.get() if self._encrypt_var.get() else "")
        self._launch_tasks(tasks)
        self._update_overall()
        self._update_action_states()

    def _clear_queue(self):
        if self._running:
            messagebox.showwarning("警告", "ダウンロード中はキューをクリアできません。")
            return
        if not self.tasks:
            return
        for t in self.tasks:
            t.removed = True
        self.tasks.clear()
        self._selected.clear()
        self._cleanup_partial_files()
        self._refresh_queue_view()
        self._update_overall()
        self._update_action_states()

    # ══════════════════════════════════════════════════════
    #  キュー操作（選択・並び替え・削除・情報確認）
    # ══════════════════════════════════════════════════════

    def _on_row_click(self, idx: int, ctrl: bool):
        if ctrl:
            if idx in self._selected:
                self._selected.discard(idx)
            else:
                self._selected.add(idx)
        else:
            self._selected = {idx}
        for i, row in self._queue_rows.items():
            if row.winfo_exists():
                row.set_selected(i in self._selected)

    def _show_row_menu(self, idx: int, event):
        if idx not in self._selected:
            self._on_row_click(idx, ctrl=False)
        task = self.tasks[idx] if idx < len(self.tasks) else None
        if not task:
            return
        c = self.theme.c
        menu = tk.Menu(self.root, tearoff=0,
                       bg=c["bg2"], fg=c["text"],
                       activebackground=ACCENT,
                       activeforeground="#ffffff",
                       font=F(12))
        retryable = task.state in (TaskState.ERROR, TaskState.PAUSED,
                                   TaskState.CANCELLED)
        menu.add_command(label="再試行",
                         state="normal" if retryable else "disabled",
                         command=lambda: self._retry_task(task))
        menu.add_command(label="動画情報を確認",
                         command=lambda: self._show_video_info(task.url))
        menu.add_command(label="保存先フォルダを開く",
                         command=lambda: self._open_task_folder(task))
        menu.add_separator()
        movable = (task.state == TaskState.PENDING)
        menu.add_command(label="↑ 上へ移動",
                         state="normal" if movable else "disabled",
                         command=lambda: self._queue_move(idx, -1))
        menu.add_command(label="↓ 下へ移動",
                         state="normal" if movable else "disabled",
                         command=lambda: self._queue_move(idx, +1))
        menu.add_separator()
        menu.add_command(label="全選択", command=self._select_all_queue)
        menu.add_command(label="選択項目を削除",
                         command=self._remove_selected)
        menu.tk_popup(event.x_root, event.y_root)

    def _select_all_queue(self):
        self._selected = set(range(len(self.tasks)))
        for i, row in self._queue_rows.items():
            if row.winfo_exists():
                row.set_selected(True)

    def _remove_selected(self):
        if not self._selected:
            return
        keep = []
        for i, t in enumerate(self.tasks):
            if i in self._selected and t.state not in (
                    TaskState.DOWNLOADING, TaskState.CONVERTING,
                    TaskState.RETRYING):
                # 待機中のスレッドが後から実行しないよう印を付ける
                t.removed = True
                continue
            keep.append(t)
        self.tasks = keep
        for i, t in enumerate(self.tasks):
            t.idx = i
        self._selected.clear()
        self._refresh_queue_view()
        # 残りがすべて終わっていれば完了扱いにする
        self._check_all_done()
        self._update_overall()
        self._update_action_states()

    def _queue_move(self, idx: int, delta: int):
        j = idx + delta
        if not (0 <= idx < len(self.tasks) and 0 <= j < len(self.tasks)):
            return
        if self.tasks[idx].state != TaskState.PENDING:
            return
        self.tasks.insert(j, self.tasks.pop(idx))
        for i, t in enumerate(self.tasks):
            t.idx = i
        self._selected = {j}
        self._refresh_queue_view()

    def _open_task_folder(self, task: DownloadTask):
        save_dir = Path(self.cfg["save_dir"])
        # 完了タスク: タイトルに一致するファイルを探してハイライト
        if task.state == TaskState.DONE and task.title:
            candidates = list(save_dir.glob(f"{task.title[:30]}*"))
            if candidates and IS_WIN:
                try:
                    subprocess.Popen(
                        ["explorer", "/select,", str(candidates[0])])
                    return
                except Exception:
                    pass
        try:
            if IS_WIN:
                os.startfile(str(save_dir))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(save_dir)])
            else:
                subprocess.Popen(["xdg-open", str(save_dir)])
        except Exception as e:
            self._log(f"フォルダを開けませんでした: {e}", "warn")

    # ══════════════════════════════════════════════════════
    #  動画情報事前確認
    # ══════════════════════════════════════════════════════

    def _show_video_info(self, url: str = ""):
        if not url:
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning("警告", "URLを入力してください。")
                return
            url = urls[0]

        win = tk.Toplevel(self.root)
        win.title("動画情報確認")
        win.geometry(f"{P(520)}x{P(430)}")
        c = self.theme.c
        win.configure(bg=c["bg1"])

        head_lbl = tk.Label(win, text="動画情報を取得中...",
                            bg=c["bg1"], fg=c["text"],
                            font=F(13, True),
                            wraplength=P(480))
        head_lbl.pack(padx=P(16), pady=(P(16), P(4)))
        tk.Label(win, text=url[:70],
                 bg=c["bg1"], fg=c["text2"],
                 font=F(10)).pack(padx=P(16))

        # サムネイル枠（Pillow がある場合のみ）。Label の width/height は
        # 画像が無いと文字数単位になり巨大化するため、ピクセル固定の枠に入れる
        thumb_label = None
        if PIL_OK:
            thumb_box = tk.Frame(win, bg=c["bg3"],
                                 width=P(200), height=P(120))
            thumb_box.pack(pady=P(8))
            thumb_box.pack_propagate(False)
            thumb_label = tk.Label(thumb_box, bg=c["bg3"])
            thumb_label.pack(fill="both", expand=True)
        self._thumb_label = thumb_label

        info_txt = tk.Text(win, bg=c["bg2"], fg=c["text"],
                           font=F(12),
                           height=10, relief="flat", state="disabled",
                           padx=P(8), pady=P(4))
        info_txt.pack(fill="both", expand=True, padx=P(12),
                      pady=(P(8) if not PIL_OK else 0, P(12)))

        def set_text(text: str, head: str):
            if not info_txt.winfo_exists():
                return
            head_lbl.config(text=head)
            info_txt.config(state="normal")
            info_txt.delete("1.0", "end")
            info_txt.insert("end", text)
            info_txt.config(state="disabled")

        if not YT_DLP_OK:
            set_text("この環境では動画情報の取得（yt-dlp Python パッケージ）が"
                     "利用できません。", "動画情報を取得できません")
            return

        def fetch():
            try:
                opts = self.dl._build_info_opts()
                with yt_dlp.YoutubeDL(opts) as ydl:
                    meta = ydl.extract_info(url, download=False)
                if not meta:
                    return

                title     = meta.get("title") or "不明"
                duration  = int(meta.get("duration") or 0)
                uploader  = meta.get("uploader") or "不明"
                view_cnt  = meta.get("view_count")
                thumb_url = meta.get("thumbnail") or ""
                formats   = meta.get("formats") or []

                dur_str = (f"{duration//3600}h{duration%3600//60}m{duration%60}s"
                           if duration else "不明")
                view_str = f"{view_cnt:,}" if isinstance(view_cnt, int) \
                    else "不明"
                fmt_summary = "\n".join(
                    f"  {str(f.get('format_id') or '?'):8s} "
                    f"{str(f.get('ext') or '?'):6s} "
                    f"{f.get('height') or '?'}p "
                    f"{str(f.get('vcodec') or '?')[:12]:12s} "
                    f"{(f.get('filesize') or 0)//1024//1024}MB"
                    for f in reversed(formats)
                    if f.get("vcodec") and f.get("vcodec") != "none"
                )[:2000]

                lines = (
                    f"タイトル  : {title}\n"
                    f"投稿者    : {uploader}\n"
                    f"長さ      : {dur_str}\n"
                    f"再生数    : {view_str}\n\n"
                    f"--- 利用可能な動画フォーマット ---\n"
                    f"{fmt_summary or '取得できませんでした'}"
                )

                self.root.after(0, lambda: set_text(lines, title))

                if thumb_url and thumb_label is not None:
                    task_tmp = DownloadTask(url=url, idx=-1,
                                           thumbnail_url=thumb_url)
                    threading.Thread(
                        target=self._fetch_thumbnail,
                        args=(task_tmp,), daemon=True).start()

            except Exception as e:
                err = f"取得エラー: {e}"
                self.root.after(0, lambda: set_text(err, "動画情報を取得できません"))

        threading.Thread(target=fetch, daemon=True).start()

    def _fetch_thumbnail(self, task: DownloadTask):
        if not task.thumbnail_url or not PIL_OK:
            return
        try:
            import urllib.request as _ur
            with _ur.urlopen(task.thumbnail_url, timeout=10) as resp:
                data = resp.read()
            img  = Image.open(_io.BytesIO(data))
            img.thumbnail((P(200), P(120)))
            img.load()
            # PhotoImage（Tk オブジェクト）はメインスレッドで作る
            self.root.after(0, lambda: self._show_thumbnail(img))
        except Exception:
            pass

    def _show_thumbnail(self, img):
        lbl = getattr(self, "_thumb_label", None)
        if lbl is not None and lbl.winfo_exists():
            photo = ImageTk.PhotoImage(img)
            lbl.configure(image=photo)
            lbl.image = photo

    # ══════════════════════════════════════════════════════
    #  全体進捗・ボタン状態
    # ══════════════════════════════════════════════════════

    def _update_overall(self):
        if not hasattr(self, "_overall_lbl") \
                or not self._overall_lbl.winfo_exists():
            return
        c = self.theme.c
        total  = len(self.tasks)
        done   = sum(1 for t in self.tasks if t.state == TaskState.DONE)
        errors = sum(1 for t in self.tasks if t.state == TaskState.ERROR)
        paused = sum(1 for t in self.tasks if t.state == TaskState.PAUSED)
        active = [t for t in self.tasks
                  if t.state in (TaskState.DOWNLOADING,
                                 TaskState.CONVERTING,
                                 TaskState.RETRYING)]

        # 状態テキスト・ドット色（デザイン仕様）
        if total == 0:
            text, dot = "待機中", c["text3"]
        elif active:
            text, dot = f"ダウンロード中 ({done}/{total} 完了)", ACCENT
        elif errors:
            text, dot = "一部エラーが発生しました", ERROR_C
        elif paused:
            text, dot = f"一時停止中 ({done}/{total} 完了)", WARNING_C
        else:
            text, dot = "すべて完了しました", SUCCESS_C

        self._overall_lbl.config(text=text)
        self._overall_dot.set_color(dot)
        if total == 0:
            self._overall_bar.set(0, color=dot)
        else:
            pct = sum(
                100.0 if t.state == TaskState.DONE else (t.progress or 0.0)
                for t in self.tasks) / total
            self._overall_bar.set(pct, color=dot)

        # 合計速度・残り時間
        total_speed = sum(parse_speed_mbps(t.speed) for t in active
                          if t.state == TaskState.DOWNLOADING)
        max_eta = max((parse_eta_sec(t.eta) for t in active
                       if t.state == TaskState.DOWNLOADING), default=0)
        self._cur_speed_mbps = total_speed
        self._overall_speed_lbl.config(
            text=f"速度: {total_speed:.1f} MB/s" if total_speed > 0
                 else "速度: —")
        self._overall_eta_lbl.config(
            text=f"残り時間: {fmt_eta_colon(max_eta)}")

        # ステータスバーにも反映
        if hasattr(self, "_status_dot") and self._status_dot.winfo_exists():
            self._status_dot.set_color(dot)
        self._set_status(text)

    def _update_action_states(self):
        if not hasattr(self, "_dl_btn") or not self._dl_btn.winfo_exists():
            return
        has_url = len(extract_urls(self._url_content)) > 0
        self._dl_btn.set_enabled(has_url and not self._running)
        self._stop_btn.set_enabled(self._running)
        retryable = any(t.state in (TaskState.ERROR, TaskState.PAUSED,
                                    TaskState.CANCELLED)
                        for t in self.tasks)
        self._retry_btn.set_enabled(retryable and not self._running)

    # ══════════════════════════════════════════════════════
    #  ログ
    # ══════════════════════════════════════════════════════

    def _log(self, msg: str, tag: str = ""):
        # 【セキュリティ】Cookie・トークン・パスワード系の情報をマスク
        masked = re.sub(
            r'(token|cookie|password|authorization|secret)[^\s]*\s*[=:]\s*\S+',
            r'\1=***', msg, flags=re.IGNORECASE)
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {masked}"
        self._log_lines.append((line, tag))
        if len(self._log_lines) > 2000:
            self._log_lines = self._log_lines[-2000:]
        if hasattr(self, "_log_text") and self._log_text.winfo_exists():
            self._log_text.append_line(line, tag)

    def _clear_log(self):
        self._log_lines.clear()
        if hasattr(self, "_log_text") and self._log_text.winfo_exists():
            self._log_text.config(state="normal")
            self._log_text.delete("1.0", "end")
            self._log_text.config(state="disabled")

    # ══════════════════════════════════════════════════════
    #  履歴
    # ══════════════════════════════════════════════════════

    def _add_history_entry(self, task: DownloadTask):
        entry = {
            "date":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title":  task.title or task.short_url(),
            "url":    task.url,
            "status": task.state.label(),
        }
        self.cfg.add_history(entry)
        self.cfg.save()
        if self._right_tab == "history":
            self._build_right_content()

    def _clear_history(self):
        self.cfg["history"] = []
        self.cfg.save()
        if self._right_tab == "history":
            self._build_right_content()

    # ══════════════════════════════════════════════════════
    #  yt-dlp アップデート
    # ══════════════════════════════════════════════════════

    def _refresh_ytdlp_version(self):
        """ワーカースレッド: 実効バージョンを取得してステータスバーへ反映"""
        ver = fetch_local_ytdlp_version()
        if ver:
            def apply():
                self._ytdlp_ver = ver
                if hasattr(self, "_ytdlp_ver_lbl") \
                        and self._ytdlp_ver_lbl.winfo_exists():
                    self._ytdlp_ver_lbl.config(text=f"yt-dlp v{ver}")
            self.root.after(0, apply)

    def _show_update_dialog(self):
        if self._running:
            messagebox.showwarning(
                "yt-dlp の更新",
                "ダウンロード中は更新できません。\n"
                "完了または停止後にもう一度お試しください。")
            return
        if self._updating:
            return
        targets = ytdlp_update_targets()
        if not targets:
            messagebox.showerror(
                "yt-dlp の更新",
                "更新対象が見つかりません。\n"
                "yt-dlp.exe を配置するか pip install yt-dlp を実行してください。")
            return

        c = self.theme.c
        win = tk.Toplevel(self.root)
        win.title("yt-dlp の更新")
        win.geometry(f"{P(520)}x{P(380)}")
        win.configure(bg=c["bg1"])
        win.transient(self.root)

        body = tk.Frame(win, bg=c["bg1"])
        body.pack(fill="both", expand=True, padx=P(20), pady=P(16))

        tk.Label(body, text="yt-dlp の更新", bg=c["bg1"], fg=c["text"],
                 font=F(14, True)).pack(anchor="w")

        cur_lbl = tk.Label(
            body,
            text=f"現在のバージョン: v{self._ytdlp_ver}"
                 if self._ytdlp_ver else "現在のバージョン: 確認中...",
            bg=c["bg1"], fg=c["text2"], font=F(12))
        cur_lbl.pack(anchor="w", pady=(P(8), 0))
        latest_lbl = tk.Label(body, text="最新バージョン: 確認中...",
                              bg=c["bg1"], fg=c["text2"], font=F(12))
        latest_lbl.pack(anchor="w", pady=(P(2), 0))
        status_lbl = tk.Label(body, text="", bg=c["bg1"], fg=ACCENT,
                              font=F(12))
        status_lbl.pack(anchor="w", pady=(P(4), 0))

        btn_row = tk.Frame(body, bg=c["bg1"])
        btn_row.pack(side="bottom", fill="x", pady=(P(12), 0))

        out_holder = tk.Frame(body, bg=c["bg3"])
        out_holder.pack(fill="both", expand=True, pady=(P(10), 0))
        out_txt = tk.Text(out_holder, bg=c["bg3"], fg=c["text2"],
                          font=FMONO(11), height=6, relief="flat", bd=0,
                          padx=P(10), pady=P(8), state="disabled",
                          wrap="word")
        out_txt.pack(fill="both", expand=True)
        upd_btn = PillButton(btn_row, text="更新する", command=None,
                             kind="accent", theme=c, bg=c["bg1"],
                             height=P(34), hpad=P(18), font=F(12, True))
        upd_btn.pack(side="left")
        upd_btn.set_enabled(False)
        close_btn = PillButton(btn_row, text="閉じる",
                               command=win.destroy,
                               kind="outline", theme=c, bg=c["bg1"],
                               height=P(34), hpad=P(14), font=F(12))
        close_btn.pack(side="right")

        def out_append(line: str):
            def _do():
                if not out_txt.winfo_exists():
                    return
                out_txt.config(state="normal")
                out_txt.insert("end", line + "\n")
                out_txt.see("end")
                out_txt.config(state="disabled")
            self.root.after(0, _do)

        # ── 最新バージョン確認（バックグラウンド） ──────────
        def check_latest():
            cur = self._ytdlp_ver or fetch_local_ytdlp_version()
            def set_cur():
                if cur_lbl.winfo_exists():
                    cur_lbl.config(
                        text=f"現在のバージョン: v{cur}" if cur
                             else "現在のバージョン: 不明")
            self.root.after(0, set_cur)
            try:
                latest = fetch_latest_ytdlp_version()
            except Exception as e:
                latest = ""
                out_append(f"最新バージョンの取得に失敗: {e}")
            def apply():
                if not win.winfo_exists():
                    return
                if latest:
                    latest_lbl.config(text=f"最新バージョン: v{latest}")
                    if cur and ver_tuple(latest) <= ver_tuple(cur):
                        status_lbl.config(text="✓ すでに最新です",
                                          fg=SUCCESS_C)
                    else:
                        status_lbl.config(text="新しいバージョンがあります",
                                          fg=ACCENT)
                else:
                    latest_lbl.config(text="最新バージョン: 取得失敗")
                    status_lbl.config(
                        text="確認できませんでした（更新の実行は可能です）",
                        fg=WARNING_C)
                upd_btn.set_enabled(True)
            self.root.after(0, apply)

        threading.Thread(target=check_latest, daemon=True).start()

        # ── 更新実行 ────────────────────────────────────────
        def run_update():
            ok_all = True
            for desc, cmd in targets:
                out_append(f"── {desc} ──")
                self.msg_q.put(("log", f"[INFO] yt-dlp 更新: {desc}"))
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        creationflags=(subprocess.CREATE_NO_WINDOW
                                       if IS_WIN else 0))
                    for raw in proc.stdout:  # type: ignore[union-attr]
                        line = decode_console_bytes(raw).rstrip()
                        if line:
                            out_append(line)
                    proc.wait()
                    if proc.returncode != 0:
                        ok_all = False
                        out_append(f"✗ 失敗（終了コード {proc.returncode}）")
                except Exception as e:
                    ok_all = False
                    out_append(f"✗ 実行エラー: {e}")

            new_ver = fetch_local_ytdlp_version()

            def finish():
                self._updating = False
                if new_ver:
                    self._ytdlp_ver = new_ver
                    if hasattr(self, "_ytdlp_ver_lbl") \
                            and self._ytdlp_ver_lbl.winfo_exists():
                        self._ytdlp_ver_lbl.config(text=f"yt-dlp v{new_ver}")
                if win.winfo_exists():
                    cur_lbl.config(
                        text=f"現在のバージョン: v{new_ver}"
                             if new_ver else "現在のバージョン: 不明")
                    if ok_all:
                        status_lbl.config(text="✓ 更新が完了しました",
                                          fg=SUCCESS_C)
                    else:
                        status_lbl.config(
                            text="⚠ 一部の更新に失敗しました（ログ参照）",
                            fg=WARNING_C)
                    upd_btn.set_enabled(True)
                    close_btn.set_enabled(True)
                msg = (f"yt-dlp を更新しました (v{new_ver})" if ok_all
                       else "yt-dlp の更新に失敗した項目があります")
                self._log(msg, "done" if ok_all else "warn")
                self._update_action_states()

            self.root.after(0, finish)

        def on_update_click():
            if self._running:
                messagebox.showwarning(
                    "yt-dlp の更新", "ダウンロード中は更新できません。",
                    parent=win)
                return
            self._updating = True
            upd_btn.set_enabled(False)
            close_btn.set_enabled(False)
            status_lbl.config(text="更新中...", fg=ACCENT)
            threading.Thread(target=run_update, daemon=True).start()

        upd_btn._cmd = on_update_click

        def on_close():
            if self._updating:
                return   # 更新中は閉じない
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

    # ══════════════════════════════════════════════════════
    #  テーマ切替
    # ══════════════════════════════════════════════════════

    def _toggle_theme(self):
        self._sync_url_content()
        self.theme.toggle()
        self.cfg["dark_mode"] = self.theme.dark
        self.cfg.save()
        self.theme.apply_ttk(self.root, self.style)
        self._build_all()

    # ══════════════════════════════════════════════════════
    #  メッセージキュー処理
    # ══════════════════════════════════════════════════════

    def _start_queue_poll(self):
        self.root.after(50, self._poll)

    def _poll(self):
        try:
            while True:
                msg_type, payload = self.msg_q.get_nowait()
                self._handle_msg(msg_type, payload)
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _handle_msg(self, msg_type: str, payload: Any):
        if msg_type == "task_update":
            task: DownloadTask = payload
            self._update_queue_row(task)
            self._update_overall()

        elif msg_type == "task_done":
            task: DownloadTask = payload
            self._log(f"✓ 完了: {task.display_name()}", "done")
            self._add_history_entry(task)
            self._update_action_states()

        elif msg_type == "task_error":
            task: DownloadTask = payload
            self._log(f"✗ エラー: {task.display_name()}\n  {task.error}",
                      "error")
            self._add_history_entry(task)
            self._update_action_states()

        elif msg_type == "log":
            text: str = payload
            tag = ""
            lt  = text.lower()
            if "[err"    in lt: tag = "error"
            elif "[warn" in lt: tag = "warn"
            elif "[info" in lt: tag = "info"
            elif "[dbg"  in lt: tag = "dim"
            self._log(text, tag)

    # ══════════════════════════════════════════════════════
    #  終了処理
    # ══════════════════════════════════════════════════════

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno(
                "終了確認",
                "ダウンロード中です。終了しますか？\n"
                "（進行中のダウンロードは中断されます）"):
                return
            self.dl.stop()
        self._save_opts()
        self.root.destroy()

    # ══════════════════════════════════════════════════════
    #  メインループ
    # ══════════════════════════════════════════════════════

    def run(self):
        self.root.mainloop()


# ══════════════════════════════════════════════════════════════
#  キュー行ウィジェット
# ══════════════════════════════════════════════════════════════

class QueueRow(tk.Frame):
    """キュー1行: # / タイトル+URL / 状態ドット+ラベル(+再試行) / 進捗 / 速度 / 残り"""

    def __init__(self, parent, app: App, task: DownloadTask):
        c = app.theme.c
        super().__init__(parent, bg=c["bg2"])
        self.app  = app
        self.task = task
        self._c   = c
        self._selected = False
        self._build()
        self.update_view(task)

    def _build(self):
        c = self._c
        app = self.app
        w_num, w_state, w_prog, w_speed, w_eta = App.QUEUE_COLS

        self.inner = tk.Frame(self, bg=c["bg2"])
        self.inner.pack(fill="x", padx=P(16), pady=P(11))

        numf = tk.Frame(self.inner, bg=c["bg2"], width=P(w_num))
        numf.pack(side="left")
        numf.pack_propagate(False)
        numf.configure(height=P(32))
        self.num_lbl = tk.Label(numf, text="", bg=c["bg2"], fg=c["text3"],
                                font=F(12), anchor="w")
        self.num_lbl.pack(fill="both")

        mid = tk.Frame(self.inner, bg=c["bg2"])
        mid.pack(side="left", fill="x", expand=True, padx=(P(12), P(12)))
        self.title_lbl = tk.Label(mid, text="", bg=c["bg2"], fg=c["text"],
                                  font=F(13), anchor="w")
        self.title_lbl.pack(fill="x")
        self.url_lbl = tk.Label(mid, text="", bg=c["bg2"], fg=c["text3"],
                                font=F(11), anchor="w")
        self.url_lbl.pack(fill="x")

        statef = tk.Frame(self.inner, bg=c["bg2"], width=P(w_state))
        statef.pack(side="left")
        statef.pack_propagate(False)
        statef.configure(height=P(34))
        srow = tk.Frame(statef, bg=c["bg2"])
        srow.pack(anchor="w")
        self.dot = Dot(srow, P(7), c["text3"], c["bg2"])
        self.dot.pack(side="left", pady=P(4))
        self.state_lbl = tk.Label(srow, text="", bg=c["bg2"],
                                  fg=c["text2"], font=F(12))
        self.state_lbl.pack(side="left", padx=(P(6), 0))
        self.retry_link = tk.Label(statef, text="再試行", bg=c["bg2"],
                                   fg=ACCENT, font=(FONT_FAMILY, -P(11),
                                                    "underline"),
                                   cursor="hand2")
        self.retry_link.bind(
            "<Button-1>", lambda _e: app._retry_task(self.task))

        progf = tk.Frame(self.inner, bg=c["bg2"], width=P(w_prog))
        progf.pack(side="left")
        progf.pack_propagate(False)
        progf.configure(height=P(20))
        self.bar = SlimProgressBar(progf, height=P(6),
                                   trough=c["bg4"], color=ACCENT,
                                   bg=c["bg2"])
        self.bar.pack(fill="x", padx=(0, P(12)), pady=P(7))

        speedf = tk.Frame(self.inner, bg=c["bg2"], width=P(w_speed))
        speedf.pack(side="left")
        speedf.pack_propagate(False)
        speedf.configure(height=P(20))
        self.speed_lbl = tk.Label(speedf, text="—", bg=c["bg2"],
                                  fg=c["text2"], font=F(12), anchor="w")
        self.speed_lbl.pack(fill="both")

        etaf = tk.Frame(self.inner, bg=c["bg2"], width=P(w_eta))
        etaf.pack(side="left")
        etaf.pack_propagate(False)
        etaf.configure(height=P(20))
        self.eta_lbl = tk.Label(etaf, text="—", bg=c["bg2"],
                                fg=c["text2"], font=F(12), anchor="w")
        self.eta_lbl.pack(fill="both")

        self.sep = tk.Frame(self, bg=c["border"], height=1)
        self.sep.pack(fill="x", side="bottom")

        # クリック / 右クリック / ダブルクリック
        self._bg_widgets = [self, self.inner, numf, mid, statef, srow,
                            progf, speedf, etaf,
                            self.num_lbl, self.title_lbl, self.url_lbl,
                            self.state_lbl, self.speed_lbl, self.eta_lbl]
        for w in self._bg_widgets:
            w.bind("<Button-1>",
                   lambda e: app._on_row_click(
                       self.task.idx, bool(e.state & 0x4)))
            w.bind("<Button-3>",
                   lambda e: app._show_row_menu(self.task.idx, e))
            w.bind("<Double-1>",
                   lambda _e: app._open_task_folder(self.task))

    def set_selected(self, selected: bool):
        self._selected = selected
        bg = self._c["bg3"] if selected else self._c["bg2"]
        for w in self._bg_widgets:
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass
        for w in (self.dot, self.bar, self.retry_link):
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass

    def update_view(self, task: DownloadTask):
        self.task = task
        color = task.state.color()
        self.num_lbl.config(text=str(task.idx + 1))
        title = task.display_name()
        self.title_lbl.config(text=title[:70])
        self.url_lbl.config(text=task.short_url(80))
        self.dot.set_color(color)
        self.state_lbl.config(text=task.state.label(), fg=color)

        # インライン再試行リンク（エラー時のみ・デザイン仕様）
        if task.state == TaskState.ERROR:
            if not self.retry_link.winfo_ismapped():
                self.retry_link.pack(anchor="w", padx=(P(13), 0))
        else:
            if self.retry_link.winfo_ismapped():
                self.retry_link.pack_forget()

        prog = 100.0 if task.state == TaskState.DONE else (task.progress or 0)
        bar_color = color if task.state != TaskState.PENDING \
            else self._c["bg4"]
        self.bar.set(prog, color=bar_color)

        if task.state == TaskState.DOWNLOADING:
            spd = parse_speed_mbps(task.speed)
            self.speed_lbl.config(
                text=f"{spd:.1f} MB/s" if spd > 0 else (task.speed or "—"))
            self.eta_lbl.config(
                text=fmt_eta_colon(parse_eta_sec(task.eta)))
        else:
            self.speed_lbl.config(text="—")
            self.eta_lbl.config(text="—")


# ══════════════════════════════════════════════════════════════
#  エントリーポイント
# ══════════════════════════════════════════════════════════════

def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s")

    if not YT_DLP_OK:
        print("=" * 60)
        print("警告: yt-dlp が見つかりません。")
        print("インストール: pip install yt-dlp")
        print("=" * 60)

    app = App()
    app.run()


if __name__ == "__main__":
    main()
