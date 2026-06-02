#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║         yt-dlp GUI v1.1.0  –  完全版 動画ダウンローダー          ║
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

# ─────────────────────────────────────────────────────────────
#  オプション依存
# ─────────────────────────────────────────────────────────────
try:
    import yt_dlp
    YT_DLP_OK = True
except ImportError:
    YT_DLP_OK = False

# tkinterdnd2 は Windows EXE ビルド時に .so (Linux用) が混入する問題があるため
# 依存を除去し、D&D は無効化（URL貼り付け・クリップボード監視で代替）
DND_OK = False

IS_WIN = sys.platform == "win32"

# ─────────────────────────────────────────────────────────────
#  定数
# ─────────────────────────────────────────────────────────────
APP_TITLE   = "yt-dlp GUI v1.1.0"
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
AUDIO_FMTS  = ["mp3", "wav", "flac", "m4a", "aac", "opus"]
VIDEO_FMTS  = ["mp4", "mkv", "webm", "mov", "avi"]
QUALITY_MAP = {
    "最高品質":   "",
    "1080p":    "[height<=1080]",
    "720p":     "[height<=720]",
    "480p":     "[height<=480]",
    "360p":     "[height<=360]",
}

# ── Win11 カラーテーマ ──────────────────────────────────────
DARK_THEME = dict(
    bg="#1c1c1c", bg2="#252525", bg3="#2e2e2e", bg4="#383838",
    accent="#0078d4", accent2="#1688e0", accent3="#005ea6",
    text="#f0f0f0", text2="#a8a8a8", text3="#666666",
    border="#3c3c3c", border2="#484848",
    success="#4ec9a0", warning="#f0b429", error="#e06b6b",
    bar_bg="#2e2e2e", bar_fg="#0078d4",
    btn="#0078d4", btn_h="#1688e0", btn_t="#ffffff",
    entry="#1c1c1c", entry_border="#3c3c3c",
    tag_done="#4ec9a0", tag_err="#e06b6b",
    tag_warn="#f0b429", tag_info="#0078d4",
    row_even="#252525", row_odd="#2a2a2a",
    scrollbar="#3c3c3c", scrollbar_h="#5c5c5c",
)
LIGHT_THEME = dict(
    bg="#f3f3f3", bg2="#ffffff", bg3="#e9e9e9", bg4="#d9d9d9",
    accent="#0078d4", accent2="#006cbe", accent3="#0063ab",
    text="#1a1a1a", text2="#4a4a4a", text3="#888888",
    border="#d0d0d0", border2="#b8b8b8",
    success="#0f7b0f", warning="#b55200", error="#c50f1f",
    bar_bg="#e0e0e0", bar_fg="#0078d4",
    btn="#0078d4", btn_h="#006cbe", btn_t="#ffffff",
    entry="#ffffff", entry_border="#c0c0c0",
    tag_done="#0f7b0f", tag_err="#c50f1f",
    tag_warn="#b55200", tag_info="#0078d4",
    row_even="#ffffff", row_odd="#f8f8f8",
    scrollbar="#c8c8c8", scrollbar_h="#a0a0a0",
)

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

def extract_urls(text: str) -> List[str]:
    pat = r'https?://[^\s\u3000\u300c\u300d\uff08\uff09\u300e\u300f\u3010\u3011\uff3b\uff3d]+'
    return list(dict.fromkeys(re.findall(pat, text)))

def desktop_notify(title: str, msg: str):
    """OSデスクトップ通知（Windows/macOS/Linux）"""
    try:
        if IS_WIN:
            from ctypes import windll
            import ctypes
            ctypes.windll.user32.MessageBeep(0)
        elif sys.platform == "darwin":
            os.system(f'osascript -e \'display notification "{msg}" with title "{title}"\'')
        else:
            os.system(f'notify-send "{title}" "{msg}" 2>/dev/null')
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════
#  CONFIG MODEL
# ══════════════════════════════════════════════════════════════

class Config:
    DEFAULTS: Dict[str, Any] = {
        "save_dir":        str(Path.home() / "Downloads"),
        "mode":            "video",
        "video_fmt":       "mp4",
        "audio_fmt":       "mp3",
        "quality":         "最高品質",
        "playlist":        False,
        "embed_thumbnail": True,
        "embed_subtitles": False,
        "auto_subtitles":  False,
        "ignore_errors":   True,
        "skip_existing":   False,   # ① ダウンロード済みスキップ
        "time_start":      "",
        "time_end":        "",
        "concurrent":      2,
        "retries":         3,
        "rate_limit":      "",
        "cookie_file":     "",
        "post_action":     "何もしない",  # ② 完了後アクション
        "dark_mode":       True,
        "recent_dirs":     [],
        "history":         [],
        "presets":         {},       # ④ 設定プリセット
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
    PENDING     = ("待機中",     "#a0a0a0")
    DOWNLOADING = ("DL中",      "#0078d4")
    CONVERTING  = ("変換中",    "#f0b429")
    DONE        = ("✓ 完了",    "#4ec9a0")
    ERROR       = ("✗ エラー",  "#e06b6b")
    CANCELLED   = ("中断",      "#888888")
    RETRYING    = ("リトライ",  "#f0b429")

    def label(self): return self.value[0]
    def color(self): return self.value[1]

@dataclass
class DownloadTask:
    url:         str
    idx:         int
    state:       TaskState = TaskState.PENDING
    progress:    float     = 0.0
    speed:       str       = ""
    eta:         str       = ""
    title:       str       = ""
    error:       str       = ""
    retry:       int       = 0
    dl_bytes:    float     = 0.0
    tot_bytes:   float     = 0.0
    rename:      str       = ""
    started:     Optional[datetime] = None
    finished:    Optional[datetime] = None

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
        self._stop.clear()
        with self._lock:
            self._ydls.clear()
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
            # ── EXE バンドル実行時 ────────────────────────
            # EXE と同じフォルダに置かれた yt-dlp.exe を使う
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
            # ── 開発環境（python ytdlp_gui.py で直接実行）──
            ytdlp_exe = shutil.which("yt-dlp")
            if ytdlp_exe:
                cmd_base = [ytdlp_exe]
            else:
                # pip install yt-dlp 済みなら python -m yt_dlp で呼べる
                cmd_base = [sys.executable, "-m", "yt_dlp"]

        # ── FFmpeg パス解決 ───────────────────────────────
        # APP_DIR (= EXEの隣のフォルダ) の ffmpeg/ を最優先で使う
        ffmpeg_dir = APP_DIR / "ffmpeg"
        if not ffmpeg_dir.exists():
            # システム PATH 上の ffmpeg にフォールバック
            ff = shutil.which("ffmpeg")
            if ff:
                ffmpeg_dir = Path(ff).parent

        cmd: List[str] = [*cmd_base]

        # ── 出力テンプレート ──────────────────────────────
        rename = (task.rename or "").strip()
        if rename:
            # リネーム指定あり：拡張子は yt-dlp が自動付与
            safe = re.sub(r'[\\/:*?"<>|]', "_", rename)  # 禁止文字を除去
            outtmpl = os.path.join(save_dir, f"{safe}.%(ext)s")
        else:
            outtmpl = os.path.join(save_dir, "%(title).200s.%(ext)s")
        cmd += ["-o", outtmpl]

        # ── FFmpeg パス ───────────────────────────────────
        if ffmpeg_dir.exists():
            cmd += ["--ffmpeg-location", str(ffmpeg_dir)]

        # ── フォーマット・変換 ────────────────────────────
        if mode == "audio":
            afmt = cfg["audio_fmt"]
            cmd += [
                "-f", "bestaudio/best",
                "-x",                           # 音声抽出
                "--audio-format", afmt,         # 変換先形式
                "--audio-quality", "0",         # 最高品質
            ]
        else:
            vfmt    = cfg["video_fmt"]
            quality = cfg["quality"]
            hfilter = QUALITY_MAP.get(quality, "")

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
                "--merge-output-format", vfmt,  # マージ後のコンテナ
                "--remux-video", vfmt,           # リマックス（再エンコードなし・高速）
            ]

        # ── プレイリスト ──────────────────────────────────
        if cfg["playlist"]:
            cmd += ["--yes-playlist"]
        else:
            cmd += ["--no-playlist"]

        # ── サムネイル ────────────────────────────────────
        if cfg["embed_thumbnail"]:
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
        rl = (cfg["rate_limit"] or "").strip()
        if rl:
            cmd += ["--rate-limit", rl]

        # ── Cookie ───────────────────────────────────────
        cf = (cfg["cookie_file"] or "").strip()
        if cf and Path(cf).exists():
            cmd += ["--cookies", cf]

        # ── リトライ・並列フラグメント ─────────────────────
        cmd += [
            "--retries", "0",           # 独自リトライ制御
            "--concurrent-fragments", "4",
            "--progress",               # 進捗を stderr に出す
            "--newline",                # 1行ごとに進捗を出す
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

    def _make_hook(self, task: DownloadTask):
        # subprocess 方式では progress_hook は使わない（_parse_progress で代替）
        def hook(d): pass
        return hook

    # ── 進捗行パース ─────────────────────────────────────
    @staticmethod
    def _parse_progress(line: str, task: DownloadTask) -> bool:
        """yt-dlp --newline の出力をパースして task を更新。更新あり→True"""
        # [download]  42.3% of  123.45MiB at  1.23MiB/s ETA 00:12
        m = re.search(
            r'\[download\]\s+([\d.]+)%\s+of\s+[\d.]+\s*\S+\s+at\s+([\d.]+\s*\S+/s)'
            r'(?:\s+ETA\s+(\S+))?',
            line)
        if m:
            task.progress = float(m.group(1))
            task.speed    = m.group(2)
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

    # ── タスク実行 ────────────────────────────────────────
    def run_task(self, task: DownloadTask):
        """セマフォ制御付き。スレッドから呼ぶ。"""
        with self._sem:
            if self._stop.is_set():
                task.state = TaskState.CANCELLED
                self.q.put(("task_update", task))
                return

            task.started  = datetime.now()
            max_retry     = self.cfg["retries"]

            for attempt in range(max_retry + 1):
                if self._stop.is_set():
                    task.state = TaskState.CANCELLED
                    self.q.put(("task_update", task))
                    return

                if attempt > 0:
                    wait = min(2 ** attempt, 30)
                    task.state = TaskState.RETRYING
                    task.retry = attempt
                    self.q.put(("task_update", task))
                    self.q.put(("log",
                        f"[リトライ {attempt}/{max_retry}] {task.short_url()} — {wait}秒後"))
                    time.sleep(wait)

                try:
                    cmd = self._build_cmd(task)
                    self.q.put(("log", f"[CMD] {' '.join(str(c) for c in cmd[:8])} ..."))

                    # Windows では PYTHONUTF8=1 を渡して yt-dlp の出力を UTF-8 に強制
                    env = os.environ.copy()
                    env["PYTHONUTF8"]        = "1"
                    env["PYTHONIOENCODING"]  = "utf-8:replace"
                    env["PYTHONLEGACYWINDOWSSTDIO"] = "0"

                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        env=env,
                        creationflags=(subprocess.CREATE_NO_WINDOW
                                       if IS_WIN else 0),
                    )

                    with self._lock:
                        self._ydls[task.idx] = proc  # type: ignore[assignment]

                    for raw_line in proc.stdout:  # type: ignore[union-attr]
                        if self._stop.is_set():
                            proc.kill()
                            break
                        line = raw_line.rstrip()
                        if not line:
                            continue

                        # yt-dlp の出力からタイトルを拾う
                        # 例: [info] xxxx: Downloading 1 format(s): 399+140
                        #     Destination: /path/タイトル.f399.mp4
                        if not task.title or task.title == task.url:
                            m = re.search(
                                r'Destination:\s*.+[\\/](.+?)(?:\.f\d+)?\.\w+\s*$',
                                line)
                            if m:
                                task.title = m.group(1)
                                self.q.put(("task_update", task))

                        if self._parse_progress(line, task):
                            self.q.put(("task_update", task))
                        if "ERROR" in line or "WARNING" in line:
                            self.q.put(("log", f"[WARN] {line}"))
                        else:
                            self.q.put(("log", f"[DBG] {line}"))

                    proc.wait()

                    if self._stop.is_set():
                        task.state = TaskState.CANCELLED
                        self.q.put(("task_update", task))
                        return

                    if proc.returncode == 0:
                        task.state    = TaskState.DONE
                        task.progress = 100.0
                        task.finished = datetime.now()
                        self.q.put(("task_update", task))
                        self.q.put(("task_done",   task))
                        return
                    else:
                        raise RuntimeError(
                            f"yt-dlp 終了コード {proc.returncode}")

                except Exception as e:
                    msg = str(e)
                    if "cancelled" in msg.lower() or self._stop.is_set():
                        task.state = TaskState.CANCELLED
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
                        self._ydls.pop(task.idx, None)

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

    def apply_ttk(self, style: ttk.Style):
        c = self.c
        bg, bg2, bg3, bg4 = c["bg"], c["bg2"], c["bg3"], c["bg4"]
        fg, fg2            = c["text"], c["text2"]
        acc                = c["accent"]
        brd                = c["border"]

        style.theme_use("clam")

        # ── 基本 ──────────────────────────────────────────
        style.configure(".", background=bg, foreground=fg,
                        font=("Yu Gothic UI", 10),
                        fieldbackground=c["entry"], bordercolor=brd,
                        troughcolor=c["bar_bg"], selectbackground=acc,
                        selectforeground="white")

        # TFrame
        style.configure("TFrame", background=bg)
        style.configure("Card.TFrame", background=bg2,
                        relief="flat", borderwidth=1)
        style.configure("Toolbar.TFrame", background=bg3)

        # TLabel
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("Sub.TLabel", background=bg, foreground=fg2,
                        font=("Yu Gothic UI", 9))
        style.configure("H1.TLabel", background=bg, foreground=fg,
                        font=("Yu Gothic UI", 14, "bold"))
        style.configure("H2.TLabel", background=bg2, foreground=fg,
                        font=("Yu Gothic UI", 11, "bold"))
        style.configure("Accent.TLabel", background=bg, foreground=acc,
                        font=("Yu Gothic UI", 10, "bold"))
        style.configure("Status.TLabel", background=bg3, foreground=fg2,
                        font=("Yu Gothic UI", 9))
        style.configure("Tag.Done.TLabel", background=c["tag_done"],
                        foreground="white", font=("Yu Gothic UI", 8, "bold"),
                        padding=(4, 1))
        style.configure("Tag.Err.TLabel", background=c["tag_err"],
                        foreground="white", font=("Yu Gothic UI", 8, "bold"),
                        padding=(4, 1))
        style.configure("Tag.Warn.TLabel", background=c["tag_warn"],
                        foreground="white", font=("Yu Gothic UI", 8, "bold"),
                        padding=(4, 1))
        style.configure("Tag.Info.TLabel", background=c["tag_info"],
                        foreground="white", font=("Yu Gothic UI", 8, "bold"),
                        padding=(4, 1))
        style.configure("Card.TLabel", background=bg2, foreground=fg)
        style.configure("Card.Sub.TLabel", background=bg2, foreground=fg2,
                        font=("Yu Gothic UI", 9))

        # TButton
        style.configure("TButton",
                        background=c["btn"], foreground=c["btn_t"],
                        borderwidth=0, focusthickness=0,
                        font=("Yu Gothic UI", 10),
                        padding=(12, 6))
        style.map("TButton",
                  background=[("active", c["btn_h"]), ("pressed", c["accent3"])],
                  foreground=[("disabled", fg2)])
        style.configure("Accent.TButton",
                        background=acc, foreground="white",
                        font=("Yu Gothic UI", 10, "bold"),
                        padding=(16, 7))
        style.map("Accent.TButton",
                  background=[("active", c["accent2"]), ("pressed", c["accent3"])])
        style.configure("Danger.TButton",
                        background=c["error"], foreground="white",
                        font=("Yu Gothic UI", 10),
                        padding=(12, 6))
        style.map("Danger.TButton",
                  background=[("active", "#d45555"), ("pressed", "#b04040")])
        style.configure("Ghost.TButton",
                        background=bg2, foreground=fg,
                        borderwidth=1, relief="solid",
                        font=("Yu Gothic UI", 10),
                        padding=(10, 5))
        style.map("Ghost.TButton",
                  background=[("active", bg3)])

        # TEntry
        style.configure("TEntry",
                        fieldbackground=c["entry"], foreground=fg,
                        insertcolor=fg, bordercolor=brd,
                        lightcolor=brd, darkcolor=brd,
                        padding=(6, 4))
        style.map("TEntry",
                  bordercolor=[("focus", acc)],
                  lightcolor=[("focus", acc)],
                  darkcolor=[("focus", acc)])

        # TCombobox
        style.configure("TCombobox",
                        fieldbackground=c["entry"], foreground=fg,
                        selectbackground=acc, selectforeground="white",
                        bordercolor=brd, arrowcolor=fg2,
                        padding=(6, 4))
        style.map("TCombobox",
                  fieldbackground=[("readonly", c["entry"])],
                  selectbackground=[("readonly", acc)],
                  bordercolor=[("focus", acc)])

        # TCheckbutton / TRadiobutton
        style.configure("TCheckbutton",
                        background=bg, foreground=fg, indicatorcolor=bg3,
                        indicatorrelief="flat")
        style.map("TCheckbutton",
                  indicatorcolor=[("selected", acc)])
        style.configure("TRadiobutton",
                        background=bg, foreground=fg, indicatorcolor=bg3)
        style.map("TRadiobutton",
                  indicatorcolor=[("selected", acc)])
        style.configure("Card.TCheckbutton", background=bg2, foreground=fg)
        style.configure("Card.TRadiobutton", background=bg2, foreground=fg)

        # TNotebook
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=bg3, foreground=fg2,
                        padding=(14, 6), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", bg2), ("active", bg3)],
                  foreground=[("selected", fg)])

        # TSeparator
        style.configure("TSeparator", background=brd)

        # TProgressbar
        style.configure("TProgressbar",
                        troughcolor=c["bar_bg"],
                        background=c["bar_fg"],
                        thickness=6, borderwidth=0)
        style.configure("Thin.TProgressbar",
                        troughcolor=c["bar_bg"],
                        background=c["bar_fg"],
                        thickness=4, borderwidth=0)

        # Treeview
        style.configure("Treeview",
                        background=bg2, foreground=fg,
                        fieldbackground=bg2, borderwidth=0,
                        rowheight=32, font=("Yu Gothic UI", 9))
        style.configure("Treeview.Heading",
                        background=bg3, foreground=fg2,
                        font=("Yu Gothic UI", 9, "bold"),
                        relief="flat", borderwidth=0)
        style.map("Treeview",
                  background=[("selected", acc)],
                  foreground=[("selected", "white")])
        style.map("Treeview.Heading",
                  background=[("active", bg4)])

        # TScale
        style.configure("TScale",
                        troughcolor=c["bar_bg"], background=acc,
                        borderwidth=0)

        # Scrollbar
        style.configure("Vertical.TScrollbar",
                        background=bg3, troughcolor=bg,
                        arrowcolor=fg2, borderwidth=0,
                        gripcount=0, width=8)
        style.map("Vertical.TScrollbar",
                  background=[("active", c["scrollbar_h"])])
        style.configure("Horizontal.TScrollbar",
                        background=bg3, troughcolor=bg,
                        arrowcolor=fg2, borderwidth=0, width=8)

        # TPanedwindow
        style.configure("TPanedwindow", background=bg)

        # TLabelframe
        style.configure("TLabelframe", background=bg2, bordercolor=brd)
        style.configure("TLabelframe.Label",
                        background=bg2, foreground=fg2,
                        font=("Yu Gothic UI", 9, "bold"))

# ══════════════════════════════════════════════════════════════
#  カスタムウィジェット
# ══════════════════════════════════════════════════════════════

class RoundedButton(tk.Canvas):
    """角丸ボタン（アニメーション付き）"""
    def __init__(self, master, text="", command=None,
                 bg="#0078d4", fg="white", hover_bg="#1688e0",
                 radius=8, width=120, height=34,
                 font=("Yu Gothic UI", 10), **kw):
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, **kw)
        self._text       = text
        self._cmd        = command
        self._bg         = bg
        self._fg         = fg
        self._hbg        = hover_bg
        self._r          = radius
        self._width_val  = width   # _w は tkinter 予約済みのため変更
        self._height_val = height  # _h は tkinter 予約済みのため変更
        self._font       = font
        self._hover      = False
        self._draw()
        self.bind("<Enter>",    self._on_enter)
        self.bind("<Leave>",    self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw(self, pressed=False):
        self.delete("all")
        c  = self._hbg if self._hover else self._bg
        if pressed: c = self._bg
        r, w, h = self._r, self._width_val, self._height_val
        self.create_arc(0,   0,   2*r, 2*r, start=90,  extent=90,  fill=c, outline=c)
        self.create_arc(w-2*r,0,  w,   2*r, start=0,   extent=90,  fill=c, outline=c)
        self.create_arc(0,   h-2*r, 2*r, h, start=180, extent=90,  fill=c, outline=c)
        self.create_arc(w-2*r,h-2*r,w,  h,  start=270, extent=90,  fill=c, outline=c)
        self.create_rectangle(r, 0, w-r, h, fill=c, outline=c)
        self.create_rectangle(0, r, w,   h-r, fill=c, outline=c)
        self.create_text(w//2, h//2, text=self._text,
                         fill=self._fg, font=self._font)

    def _on_enter(self, _):
        self._hover = True
        self._draw()

    def _on_leave(self, _):
        self._hover = False
        self._draw()

    def _on_click(self, _):
        self._draw(pressed=True)

    def _on_release(self, _):
        self._draw()
        if self._cmd:
            self._cmd()

    def config_state(self, state: str):
        if state == "disabled":
            self._bg  = "#555555"
            self._hbg = "#555555"
            self.unbind("<Button-1>")
            self.unbind("<ButtonRelease-1>")
        self._draw()


class AnimatedProgressBar(tk.Canvas):
    """アニメーション付きプログレスバー"""
    def __init__(self, master, height=6, bg="#2e2e2e", fg="#0078d4",
                 radius=3, **kw):
        super().__init__(master, height=height, highlightthickness=0,
                         bd=0, bg=bg, **kw)
        self._bg  = bg
        self._fg  = fg
        self._r   = radius
        self._val = 0.0
        self._anim_val = 0.0
        self._running  = False
        self.bind("<Configure>", lambda _: self._draw())

    def set(self, val: float):
        self._val = max(0.0, min(100.0, val))
        if not self._running:
            self._running = True
            self._animate()

    def _animate(self):
        diff = self._val - self._anim_val
        if abs(diff) < 0.5:
            self._anim_val = self._val
            self._draw()
            self._running = False
            return
        self._anim_val += diff * 0.15
        self._draw()
        self.after(16, self._animate)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 2: return
        r = self._r
        # trough
        self.create_rectangle(0, 0, w, h, fill=self._bg, outline="")
        # fill
        fw = int(w * self._anim_val / 100)
        if fw > 0:
            self.create_rectangle(0, 0, fw, h, fill=self._fg, outline="")


class SmoothToggle(tk.Canvas):
    """Win11風トグルスイッチ"""
    def __init__(self, master, variable: tk.BooleanVar,
                 on_color="#0078d4", off_color="#666666",
                 width=44, height=22, command=None, **kw):
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, **kw)
        self._var        = variable
        self._on_c       = on_color
        self._off_c      = off_color
        self._width_val  = width   # _w は tkinter 予約済みのため変更
        self._height_val = height  # _h は tkinter 予約済みのため変更
        self._cmd        = command
        self._pos        = 1.0 if variable.get() else 0.0
        self._animating  = False
        self._draw()
        self.bind("<Button-1>", self._toggle)
        variable.trace_add("write", lambda *_: self._start_anim())

    def _start_anim(self):
        if not self._animating:
            self._animating = True
            self._anim()

    def _anim(self):
        target = 1.0 if self._var.get() else 0.0
        diff   = target - self._pos
        if abs(diff) < 0.05:
            self._pos = target
            self._draw()
            self._animating = False
            return
        self._pos += diff * 0.2
        self._draw()
        self.after(16, self._anim)

    def _draw(self):
        self.delete("all")
        w, h = self._width_val, self._height_val
        r    = h // 2
        c    = self._on_c if self._var.get() else self._off_c
        # track
        self.create_oval(0, 0, h, h, fill=c, outline="")
        self.create_oval(w-h, 0, w, h, fill=c, outline="")
        self.create_rectangle(r, 0, w-r, h, fill=c, outline="")
        # knob
        pad   = 2
        knob_x = int(pad + self._pos * (w - h - pad*2) + r - pad)
        self.create_oval(knob_x-r+pad*2, pad,
                         knob_x+r-pad*2, h-pad,
                         fill="white", outline="")

    def _toggle(self, _):
        self._var.set(not self._var.get())
        if self._cmd:
            self._cmd()


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

    def append(self, text: str, tag: str = ""):
        self.config(state="normal")
        # 行数制限
        lines = int(self.index("end-1c").split(".")[0])
        if lines > self.MAX_LINES:
            self.delete("1.0", f"{lines - self.MAX_LINES}.0")
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}\n"
        if tag:
            self.insert("end", line, tag)
        else:
            self.insert("end", line)
        if self._auto_scroll:
            self.see("end")
        self.config(state="disabled")

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

        self.tasks:  List[DownloadTask] = []
        self.threads:List[threading.Thread] = []
        self._running = False

        # tkinter root（tkinterdnd2不使用・tk.Tk()に統一）
        self.root = tk.Tk()

        self._setup_root()
        self._setup_style()
        self._build_ui()
        self._restore_config()
        self._start_queue_poll()

        # URL 貼り付け監視
        self.root.after(500, self._watch_clipboard)

    # ── Root 設定 ─────────────────────────────────────────
    def _setup_root(self):
        r = self.root
        r.title(APP_TITLE)
        r.geometry("1200x820")
        r.minsize(900, 600)
        c = self.theme.c
        r.configure(bg=c["bg"])
        if IS_WIN:
            try:
                r.iconbitmap(default="")
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        r.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self):
        self.style = ttk.Style(self.root)
        self.theme.apply_ttk(self.style)

    # ══════════════════════════════════════════════════════
    #  UI 構築
    # ══════════════════════════════════════════════════════

    def _build_ui(self):
        c = self.theme.c
        r = self.root

        # ── タイトルバー代替ヘッダー ──────────────────────
        self._build_header()

        # ── メインペイン ──────────────────────────────────
        self.paned = tk.PanedWindow(
            r, orient="horizontal",
            bg=c["bg"], sashwidth=4,
            sashpad=0, relief="flat",
        )
        self.paned.pack(fill="both", expand=True, padx=0, pady=0)

        # 左パネル（設定）
        self.left_frame = ttk.Frame(self.paned)
        self.paned.add(self.left_frame, minsize=340, width=400)
        self._build_left_panel()

        # 右パネル（キュー＋ログ）
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, minsize=400)
        self._build_right_panel()

        # ── ステータスバー ────────────────────────────────
        self._build_statusbar()

    # ── ヘッダー ──────────────────────────────────────────
    def _build_header(self):
        c = self.theme.c
        hdr = tk.Frame(self.root, bg=c["bg3"], height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # ロゴ
        logo_f = tk.Frame(hdr, bg=c["bg3"])
        logo_f.pack(side="left", padx=16, pady=0)
        tk.Label(logo_f, text="▶", bg=c["bg3"], fg=c["accent"],
                 font=("Yu Gothic UI", 18)).pack(side="left", pady=12)
        tk.Label(logo_f, text="  yt-dlp GUI",
                 bg=c["bg3"], fg=c["text"],
                 font=("Yu Gothic UI", 13, "bold")).pack(side="left", pady=12)
        tk.Label(logo_f, text=" v1.1.0", bg=c["bg3"], fg=c["text2"],
                 font=("Yu Gothic UI", 9)).pack(side="left", pady=16)

        # 右側コントロール
        ctrl = tk.Frame(hdr, bg=c["bg3"])
        ctrl.pack(side="right", padx=12)

        # ダーク/ライトトグル
        tk.Label(ctrl, text="🌙" if self.theme.dark else "☀",
                 bg=c["bg3"], fg=c["text2"],
                 font=("Yu Gothic UI", 11)).pack(side="left", pady=14)
        self._dark_var = tk.BooleanVar(value=self.theme.dark)
        SmoothToggle(ctrl, variable=self._dark_var,
                     bg=c["bg3"],
                     command=self._toggle_theme).pack(
            side="left", padx=(4, 16), pady=14)
        tk.Label(ctrl, text="☀" if self.theme.dark else "🌙",
                 bg=c["bg3"], fg=c["text2"],
                 font=("Yu Gothic UI", 11)).pack(side="left", pady=14)

        # 区切り
        ttk.Separator(self.root, orient="horizontal").pack(fill="x")

    # ── 左パネル ──────────────────────────────────────────
    def _build_left_panel(self):
        c = self.theme.c
        p = self.left_frame
        p.configure()

        scroll_f = tk.Frame(p, bg=c["bg"])
        scroll_f.pack(fill="both", expand=True)

        canvas  = tk.Canvas(scroll_f, bg=c["bg"],
                            highlightthickness=0, bd=0)
        vsb     = ttk.Scrollbar(scroll_f, orient="vertical",
                                command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=c["bg"])
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_frame_conf(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_conf(e):
            canvas.itemconfigure(win_id, width=e.width)

        inner.bind("<Configure>", _on_frame_conf)
        canvas.bind("<Configure>", _on_canvas_conf)

        def _on_mw(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mw)
        inner.bind("<MouseWheel>", _on_mw)

        pad = dict(padx=12, pady=4)

        # ── URL 入力セクション ────────────────────────────
        self._build_section(inner, "🔗  URL 入力", pad)
        url_card = self._card(inner, pad)
        self._build_url_input(url_card)

        # ── モード選択 ────────────────────────────────────
        self._build_section(inner, "📂  ダウンロードモード", pad)
        mode_card = self._card(inner, pad)
        self._build_mode_panel(mode_card)

        # ── 保存先 ────────────────────────────────────────
        self._build_section(inner, "💾  保存先", pad)
        save_card = self._card(inner, pad)
        self._build_save_panel(save_card)

        # ── オプション ────────────────────────────────────
        self._build_section(inner, "⚙  オプション", pad)
        opt_card = self._card(inner, pad)
        self._build_options_panel(opt_card)

        # ── ファイル名変更（単体動画のみ） ────────────────
        self._build_section(inner, "✏  ファイル名変更（単体動画のみ）", pad)
        rename_card = self._card(inner, pad)
        self._build_rename_panel(rename_card)

        # ── 高度な設定 ────────────────────────────────────
        self._build_section(inner, "🔧  高度な設定", pad)
        adv_card = self._card(inner, pad)
        self._build_advanced_panel(adv_card)

        # ── プリセット ────────────────────────────────────
        self._build_section(inner, "💾  設定プリセット", pad)
        preset_card = self._card(inner, pad)
        self._build_preset_panel(preset_card)

        # ── アクションボタン ──────────────────────────────
        btn_f = tk.Frame(p, bg=c["bg3"], height=64)
        btn_f.pack(fill="x", side="bottom")
        btn_f.pack_propagate(False)
        ttk.Separator(p, orient="horizontal").pack(
            fill="x", side="bottom")
        self._build_action_buttons(btn_f)

    def _build_section(self, parent, title: str, pad: dict):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg"])
        f.pack(fill="x", padx=pad.get("padx", 12), pady=(10, 0))
        tk.Label(f, text=title, bg=c["bg"], fg=c["text2"],
                 font=("Yu Gothic UI", 9, "bold")).pack(
            side="left", pady=(2, 0))

    def _card(self, parent, pad: dict) -> tk.Frame:
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg2"],
                     highlightbackground=c["border"],
                     highlightthickness=1)
        f.pack(fill="x", padx=pad.get("padx", 12), pady=(2, 0))
        return f

    # ── URL 入力 ─────────────────────────────────────────
    def _build_url_input(self, parent):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg2"])
        f.pack(fill="x", padx=10, pady=8)

        top = tk.Frame(f, bg=c["bg2"])
        top.pack(fill="x")
        tk.Label(top, text="URLを入力 (複数可、1行1URL)",
                 bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9)).pack(side="left")
        tk.Label(top, text="貼り付けで追加",
                 bg=c["accent"], fg="white",
                 font=("Yu Gothic UI", 8),
                 padx=4).pack(side="right")

        txt_frame = tk.Frame(f, bg=c["border"], padx=1, pady=1)
        txt_frame.pack(fill="x", pady=(4, 0))

        self.url_text = tk.Text(
            txt_frame, height=6, wrap="none",
            bg=c["entry"], fg=c["text"],
            insertbackground=c["text"],
            selectbackground=c["accent"],
            font=("Consolas", 10),
            relief="flat", bd=0,
            padx=8, pady=6,
        )
        self.url_text.pack(fill="x")

        # ボタン行
        btn_row = tk.Frame(f, bg=c["bg2"])
        btn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_row, text="クリア",
                   style="Ghost.TButton",
                   command=self._clear_urls).pack(side="right", padx=(4, 0))
        ttk.Button(btn_row, text="クリップボードから貼り付け",
                   style="Ghost.TButton",
                   command=self._paste_clipboard).pack(side="right")
        self._url_count_lbl = tk.Label(
            btn_row, text="0 URL", bg=c["bg2"], fg=c["text2"],
            font=("Yu Gothic UI", 9))
        self._url_count_lbl.pack(side="left")
        self.url_text.bind("<KeyRelease>", lambda _: self._update_url_count())

    # ── モードパネル ─────────────────────────────────────
    def _build_mode_panel(self, parent):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg2"])
        f.pack(fill="x", padx=10, pady=8)

        self._mode_var = tk.StringVar(value=self.cfg["mode"])

        # モードタブ風ラジオ
        tab_f = tk.Frame(f, bg=c["bg3"],
                         highlightbackground=c["border"],
                         highlightthickness=1)
        tab_f.pack(fill="x", pady=(0, 8))

        for i, (val, lbl, ico) in enumerate([
            ("video", "動画", "🎬"),
            ("audio", "音声のみ", "🎵"),
        ]):
            rb = tk.Radiobutton(
                tab_f, text=f"{ico} {lbl}",
                variable=self._mode_var, value=val,
                bg=c["bg3"], fg=c["text"],
                selectcolor=c["bg3"],
                activebackground=c["bg3"],
                activeforeground=c["accent"],
                font=("Yu Gothic UI", 10),
                relief="flat", bd=0,
                command=self._on_mode_change,
                padx=16, pady=8,
                # indicatoron=False は variable へのセットが効かないため使用しない
            )
            rb.grid(row=0, column=i, sticky="ew", padx=1, pady=1)
            tab_f.columnconfigure(i, weight=1)

        # 動画設定
        self._video_frame = tk.Frame(f, bg=c["bg2"])
        self._video_frame.pack(fill="x")

        row1 = tk.Frame(self._video_frame, bg=c["bg2"])
        row1.pack(fill="x", pady=2)
        tk.Label(row1, text="形式", bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9), width=8,
                 anchor="w").pack(side="left")
        self._vfmt_var = tk.StringVar(value=self.cfg["video_fmt"])
        cb = ttk.Combobox(row1, textvariable=self._vfmt_var,
                          values=VIDEO_FMTS, state="readonly", width=10)
        cb.pack(side="left", padx=(0, 16))
        cb.bind("<<ComboboxSelected>>", lambda _: self._save_opts())

        tk.Label(row1, text="画質", bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9), width=6,
                 anchor="w").pack(side="left")
        self._quality_var = tk.StringVar(value=self.cfg["quality"])
        cb2 = ttk.Combobox(row1, textvariable=self._quality_var,
                            values=list(QUALITY_MAP.keys()),
                            state="readonly", width=10)
        cb2.pack(side="left")
        cb2.bind("<<ComboboxSelected>>", lambda _: self._save_opts())

        # 音声設定
        self._audio_frame = tk.Frame(f, bg=c["bg2"])
        # （モード変更時に表示切替）
        row2 = tk.Frame(self._audio_frame, bg=c["bg2"])
        row2.pack(fill="x", pady=2)
        tk.Label(row2, text="形式", bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9), width=8,
                 anchor="w").pack(side="left")
        self._afmt_var = tk.StringVar(value=self.cfg["audio_fmt"])
        cb3 = ttk.Combobox(row2, textvariable=self._afmt_var,
                            values=AUDIO_FMTS, state="readonly", width=10)
        cb3.pack(side="left")
        cb3.bind("<<ComboboxSelected>>", lambda _: self._save_opts())

        self._on_mode_change()

    def _on_mode_change(self):
        mode = self._mode_var.get()
        if mode == "video":
            self._audio_frame.pack_forget()
            self._video_frame.pack(fill="x")
        else:
            self._video_frame.pack_forget()
            self._audio_frame.pack(fill="x")
        self._save_opts()

    # ── 保存先パネル ─────────────────────────────────────
    def _build_save_panel(self, parent):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg2"])
        f.pack(fill="x", padx=10, pady=8)

        # パス入力
        row = tk.Frame(f, bg=c["bg2"])
        row.pack(fill="x")
        self._save_var = tk.StringVar(value=self.cfg["save_dir"])
        ent = ttk.Entry(row, textvariable=self._save_var)
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<FocusOut>", lambda _: self._save_opts())
        ttk.Button(row, text="参照…",
                   style="Ghost.TButton",
                   command=self._browse_dir).pack(side="right", padx=(4, 0))

        # 最近使ったフォルダ
        recent = self.cfg["recent_dirs"]
        if recent:
            tk.Label(f, text="最近使ったフォルダ:",
                     bg=c["bg2"], fg=c["text2"],
                     font=("Yu Gothic UI", 8)).pack(anchor="w", pady=(4, 0))
            for d in recent[:4]:
                lbl = tk.Label(f, text=f"  📁 {Path(d).name}",
                               bg=c["bg2"], fg=c["accent"],
                               font=("Yu Gothic UI", 9),
                               cursor="hand2")
                lbl.pack(anchor="w")
                lbl.bind("<Button-1>", lambda e, p=d: self._set_save_dir(p))

    def _browse_dir(self):
        d = filedialog.askdirectory(
            initialdir=self.cfg["save_dir"],
            title="保存先を選択")
        if d:
            self._set_save_dir(d)

    def _set_save_dir(self, path: str):
        self._save_var.set(path)
        self._save_opts()

    # ── オプションパネル ─────────────────────────────────
    def _build_options_panel(self, parent):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg2"])
        f.pack(fill="x", padx=10, pady=8)

        self._opts_vars: Dict[str, tk.BooleanVar] = {}

        opts = [
            ("playlist",        "プレイリスト全体をDL"),
            ("embed_thumbnail", "サムネイル埋め込み"),
            ("embed_subtitles", "字幕をDL・埋め込み"),
            ("auto_subtitles",  "自動生成字幕もDL"),
            ("ignore_errors",   "エラーを無視して続行"),
            ("skip_existing",   "ダウンロード済みをスキップ"),
        ]
        for key, lbl in opts:
            var = tk.BooleanVar(value=self.cfg[key])
            self._opts_vars[key] = var
            row = tk.Frame(f, bg=c["bg2"])
            row.pack(fill="x", pady=1)
            SmoothToggle(row, variable=var,
                         bg=c["bg2"],
                         command=self._save_opts).pack(side="left")
            tk.Label(row, text=f"  {lbl}",
                     bg=c["bg2"], fg=c["text"],
                     font=("Yu Gothic UI", 10)).pack(side="left")

        # 範囲ダウンロード
        ttk.Separator(f, orient="horizontal").pack(
            fill="x", pady=(8, 4))
        tk.Label(f, text="範囲ダウンロード（空白=全体）",
                 bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9)).pack(anchor="w")
        range_row = tk.Frame(f, bg=c["bg2"])
        range_row.pack(fill="x", pady=(2, 0))
        tk.Label(range_row, text="開始", bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9), width=4).pack(side="left")
        self._ts_var = tk.StringVar(value=self.cfg["time_start"])
        ttk.Entry(range_row, textvariable=self._ts_var,
                  width=10).pack(side="left", padx=(0, 8))
        tk.Label(range_row, text="終了", bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9), width=4).pack(side="left")
        self._te_var = tk.StringVar(value=self.cfg["time_end"])
        ttk.Entry(range_row, textvariable=self._te_var,
                  width=10).pack(side="left")
        tk.Label(range_row, text=" 例: 00:01:30",
                 bg=c["bg2"], fg=c["text3"],
                 font=("Yu Gothic UI", 8)).pack(side="left")

        for v in [self._ts_var, self._te_var]:
            v.trace_add("write", lambda *_: self._save_opts())

    # ── 高度な設定パネル ─────────────────────────────────
    def _build_advanced_panel(self, parent):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg2"])
        f.pack(fill="x", padx=10, pady=8)

        def _row(lbl: str, widget_factory, tip: str = ""):
            row = tk.Frame(f, bg=c["bg2"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=lbl, bg=c["bg2"], fg=c["text2"],
                     font=("Yu Gothic UI", 9),
                     width=14, anchor="w").pack(side="left")
            w = widget_factory(row)
            w.pack(side="left", fill="x", expand=True)
            if tip:
                tk.Label(row, text=tip, bg=c["bg2"], fg=c["text3"],
                         font=("Yu Gothic UI", 8)).pack(side="left", padx=(4, 0))
            return w

        # 並列数
        self._concurrent_var = tk.IntVar(value=self.cfg["concurrent"])
        def _spin_concurrent(p):
            sb = ttk.Spinbox(p, from_=1, to=8, width=5,
                             textvariable=self._concurrent_var)
            sb.bind("<FocusOut>", lambda _: self._save_opts())
            return sb
        _row("並列DL数", _spin_concurrent, "本 (1-8)")

        # リトライ数
        self._retries_var = tk.IntVar(value=self.cfg["retries"])
        def _spin_retry(p):
            sb = ttk.Spinbox(p, from_=0, to=10, width=5,
                             textvariable=self._retries_var)
            sb.bind("<FocusOut>", lambda _: self._save_opts())
            return sb
        _row("自動リトライ", _spin_retry, "回")

        # 帯域制限
        self._rate_var = tk.StringVar(value=self.cfg["rate_limit"])
        def _ent_rate(p):
            e = ttk.Entry(p, textvariable=self._rate_var, width=12)
            e.bind("<FocusOut>", lambda _: self._save_opts())
            return e
        _row("帯域制限", _ent_rate, "例: 5M, 500K")

        # Cookie ファイル
        self._cookie_var = tk.StringVar(value=self.cfg["cookie_file"])
        def _ent_cookie(p):
            fr = tk.Frame(p, bg=c["bg2"])
            e  = ttk.Entry(fr, textvariable=self._cookie_var)
            e.pack(side="left", fill="x", expand=True)
            e.bind("<FocusOut>", lambda _: self._save_opts())
            ttk.Button(
                fr, text="…", style="Ghost.TButton", width=2,
                command=self._browse_cookie
            ).pack(side="left", padx=(2, 0))
            return fr
        _row("Cookie ファイル", _ent_cookie)
        tk.Label(f,
                 text="  → YouTube会員・年齢制限・Twitchなどに使用",
                 bg=c["bg2"], fg=c["text3"],
                 font=("Yu Gothic UI", 8)).pack(anchor="w")

        # ② 完了後アクション
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(8, 4))
        self._post_action_var = tk.StringVar(value=self.cfg["post_action"])
        POST_ACTIONS = ["何もしない", "フォルダを開く", "シャットダウン"]
        def _cb_action(p):
            cb = ttk.Combobox(p, textvariable=self._post_action_var,
                              values=POST_ACTIONS, state="readonly", width=16)
            cb.bind("<<ComboboxSelected>>", lambda _: self._save_opts())
            return cb
        _row("完了後アクション", _cb_action)

    def _browse_cookie(self):
        p = filedialog.askopenfilename(
            title="Cookie ファイルを選択",
            filetypes=[("テキスト", "*.txt"), ("すべて", "*.*")])
        if p:
            self._cookie_var.set(p)
            self._save_opts()

    # ── プリセットパネル ─────────────────────────────────
    def _build_preset_panel(self, parent):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg2"])
        f.pack(fill="x", padx=10, pady=8)

        # プリセット選択
        load_row = tk.Frame(f, bg=c["bg2"])
        load_row.pack(fill="x", pady=(0, 4))
        tk.Label(load_row, text="読み込み", bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9), width=8, anchor="w").pack(side="left")
        self._preset_select_var = tk.StringVar()
        self._preset_cb = ttk.Combobox(
            load_row, textvariable=self._preset_select_var,
            state="readonly", width=16)
        self._preset_cb.pack(side="left", padx=(0, 4))
        ttk.Button(load_row, text="読み込む",
                   style="Ghost.TButton",
                   command=self._load_preset).pack(side="left", padx=(0, 4))
        ttk.Button(load_row, text="削除",
                   style="Ghost.TButton",
                   command=self._delete_preset).pack(side="left")

        # プリセット保存
        save_row = tk.Frame(f, bg=c["bg2"])
        save_row.pack(fill="x")
        tk.Label(save_row, text="保存名", bg=c["bg2"], fg=c["text2"],
                 font=("Yu Gothic UI", 9), width=8, anchor="w").pack(side="left")
        self._preset_name_var = tk.StringVar()
        ttk.Entry(save_row, textvariable=self._preset_name_var,
                  width=16).pack(side="left", padx=(0, 4))
        ttk.Button(save_row, text="現在の設定を保存",
                   style="Ghost.TButton",
                   command=self._save_preset).pack(side="left")

        self._refresh_preset_list()

    def _refresh_preset_list(self):
        if not hasattr(self, "_preset_cb"):
            return
        names = list(self.cfg["presets"].keys())
        self._preset_cb["values"] = names
        if names and self._preset_select_var.get() not in names:
            self._preset_select_var.set(names[0] if names else "")

    def _save_preset(self):
        name = self._preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("警告", "プリセット名を入力してください。")
            return
        self._save_opts()
        snapshot = {
            "mode":            self.cfg["mode"],
            "video_fmt":       self.cfg["video_fmt"],
            "audio_fmt":       self.cfg["audio_fmt"],
            "quality":         self.cfg["quality"],
            "playlist":        self.cfg["playlist"],
            "embed_thumbnail": self.cfg["embed_thumbnail"],
            "embed_subtitles": self.cfg["embed_subtitles"],
            "auto_subtitles":  self.cfg["auto_subtitles"],
            "ignore_errors":   self.cfg["ignore_errors"],
            "skip_existing":   self.cfg["skip_existing"],
            "time_start":      self.cfg["time_start"],
            "time_end":        self.cfg["time_end"],
            "concurrent":      self.cfg["concurrent"],
            "retries":         self.cfg["retries"],
            "rate_limit":      self.cfg["rate_limit"],
            "post_action":     self.cfg["post_action"],
        }
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
        # UI に反映
        self._mode_var.set(preset.get("mode", "video"))
        self._vfmt_var.set(preset.get("video_fmt", "mp4"))
        self._afmt_var.set(preset.get("audio_fmt", "mp3"))
        self._quality_var.set(preset.get("quality", "最高品質"))
        self._ts_var.set(preset.get("time_start", ""))
        self._te_var.set(preset.get("time_end", ""))
        self._concurrent_var.set(preset.get("concurrent", 2))
        self._retries_var.set(preset.get("retries", 3))
        self._rate_var.set(preset.get("rate_limit", ""))
        if hasattr(self, "_post_action_var"):
            self._post_action_var.set(preset.get("post_action", "何もしない"))
        for key in ("playlist", "embed_thumbnail", "embed_subtitles",
                    "auto_subtitles", "ignore_errors", "skip_existing"):
            if key in self._opts_vars:
                self._opts_vars[key].set(preset.get(key, False))
        self._on_mode_change()
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

    # ── リネームパネル（単体動画のみ・プレイリストOFF時） ──
    def _build_rename_panel(self, parent):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg2"])
        f.pack(fill="x", padx=10, pady=8)

        self._rename_var = tk.StringVar(value="")
        self._meta_vars: Dict[str, tk.StringVar] = {}  # _save_opts互換用

        row = tk.Frame(f, bg=c["bg2"])
        row.pack(fill="x")
        self._rename_entry = ttk.Entry(row, textvariable=self._rename_var)
        self._rename_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="クリア", style="Ghost.TButton",
                   command=lambda: self._rename_var.set("")).pack(
            side="left", padx=(4, 0))

        tk.Label(f,
                 text="  ※ 入力した名前でファイルを保存します（拡張子は自動付与）\n"
                      "  ※ プレイリストON または URL複数入力時は無効",
                 bg=c["bg2"], fg=c["text3"],
                 font=("Yu Gothic UI", 8),
                 justify="left").pack(anchor="w", pady=(4, 0))

        # プレイリストONまたはURL複数のとき入力欄をグレーアウト
        self._playlist_var = self._opts_vars.get("playlist")
        if self._playlist_var:
            self._playlist_var.trace_add(
                "write", lambda *_: self._update_rename_state())
        self.url_text.bind(
            "<KeyRelease>",
            lambda e: (self._update_url_count(), self._update_rename_state()))

        self._update_rename_state()

    def _update_rename_state(self):
        """プレイリストON or URL複数のとき、リネーム欄を無効化する"""
        if not hasattr(self, "_rename_entry"):
            return
        playlist_on = self._opts_vars.get("playlist",
                                          tk.BooleanVar()).get()
        url_count   = len(self._get_urls())
        if playlist_on or url_count > 1:
            self._rename_entry.config(state="disabled")
            self._rename_var.set("")
        else:
            self._rename_entry.config(state="normal")

    # ── アクションボタン ──────────────────────────────────
    def _build_action_buttons(self, parent):
        c = self.theme.c
        f = tk.Frame(parent, bg=c["bg3"])
        f.pack(fill="both", expand=True, padx=12, pady=10)

        self._dl_btn = ttk.Button(
            f, text="▶  ダウンロード開始",
            style="Accent.TButton",
            command=self._start_download)
        self._dl_btn.pack(side="left", fill="y")

        self._stop_btn = ttk.Button(
            f, text="■  停止",
            style="Danger.TButton",
            command=self._stop_download,
            state="disabled")
        self._stop_btn.pack(side="left", padx=(6, 0), fill="y")

        self._retry_btn = ttk.Button(
            f, text="↺  失敗を再試行",
            style="Ghost.TButton",
            command=self._retry_failed,
            state="disabled")
        self._retry_btn.pack(side="left", padx=(6, 0), fill="y")

        ttk.Button(
            f, text="🗑  キュークリア",
            style="Ghost.TButton",
            command=self._clear_queue).pack(side="right")

    # ── 右パネル ──────────────────────────────────────────
    def _build_right_panel(self):
        c = self.theme.c
        p = self.right_frame

        # 全体進捗
        prog_f = tk.Frame(p, bg=c["bg3"], height=56)
        prog_f.pack(fill="x")
        prog_f.pack_propagate(False)
        prog_inner = tk.Frame(prog_f, bg=c["bg3"])
        prog_inner.pack(fill="both", expand=True, padx=14, pady=6)

        top_row = tk.Frame(prog_inner, bg=c["bg3"])
        top_row.pack(fill="x")
        self._overall_lbl = tk.Label(
            top_row, text="待機中", bg=c["bg3"], fg=c["text"],
            font=("Yu Gothic UI", 10, "bold"))
        self._overall_lbl.pack(side="left")
        self._overall_stat = tk.Label(
            top_row, text="", bg=c["bg3"], fg=c["text2"],
            font=("Yu Gothic UI", 9))
        self._overall_stat.pack(side="right")

        self._overall_bar = AnimatedProgressBar(
            prog_inner, height=8, bg=c["bar_bg"], fg=c["bar_fg"])
        self._overall_bar.pack(fill="x", pady=(4, 0))

        ttk.Separator(p, orient="horizontal").pack(fill="x")

        # タブ
        self._notebook = ttk.Notebook(p)
        self._notebook.pack(fill="both", expand=True)

        # キュータブ
        queue_tab = ttk.Frame(self._notebook)
        self._notebook.add(queue_tab, text="  📋 ダウンロードキュー  ")
        self._build_queue_tab(queue_tab)

        # ログタブ
        log_tab = ttk.Frame(self._notebook)
        self._notebook.add(log_tab, text="  📝 ログ  ")
        self._build_log_tab(log_tab)

        # 履歴タブ
        hist_tab = ttk.Frame(self._notebook)
        self._notebook.add(hist_tab, text="  🕐 ダウンロード履歴  ")
        self._build_history_tab(hist_tab)

    # ── キュータブ ────────────────────────────────────────
    def _build_queue_tab(self, parent):
        c = self.theme.c

        # ツールバー
        tb = tk.Frame(parent, bg=c["bg3"])
        tb.pack(fill="x", padx=8, pady=6)
        tk.Label(tb, text="キュー管理:",
                 bg=c["bg3"], fg=c["text2"],
                 font=("Yu Gothic UI", 9)).pack(side="left")
        ttk.Button(tb, text="全選択",
                   style="Ghost.TButton",
                   command=self._select_all_queue).pack(side="right", padx=2)
        ttk.Button(tb, text="選択削除",
                   style="Ghost.TButton",
                   command=self._remove_selected).pack(side="right", padx=2)

        # Treeview
        cols = ("idx", "title", "state", "progress", "speed", "eta", "size")
        tree_f = tk.Frame(parent, bg=c["bg2"])
        tree_f.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self._queue_tree = ttk.Treeview(
            tree_f, columns=cols, show="headings",
            selectmode="extended")

        vsb = ttk.Scrollbar(tree_f, orient="vertical",
                            command=self._queue_tree.yview)
        hsb = ttk.Scrollbar(tree_f, orient="horizontal",
                            command=self._queue_tree.xview)
        self._queue_tree.configure(
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._queue_tree.pack(fill="both", expand=True)

        hdrs = [
            ("idx",      "#",       40,  False),
            ("title",    "タイトル/URL", 300, True),
            ("state",    "状態",    80,  False),
            ("progress", "進捗",    70,  False),
            ("speed",    "速度",    90,  False),
            ("eta",      "残り時間",80,  False),
            ("size",     "サイズ",  90,  False),
        ]
        for col, lbl, w, stretch in hdrs:
            self._queue_tree.heading(col, text=lbl)
            self._queue_tree.column(col, width=w,
                                    stretch=stretch, anchor="center")
        self._queue_tree.column("title", anchor="w")

        # タグ
        self._queue_tree.tag_configure("done",
            foreground=c["success"])
        self._queue_tree.tag_configure("error",
            foreground=c["error"])
        self._queue_tree.tag_configure("active",
            foreground=c["accent"])
        self._queue_tree.tag_configure("warn",
            foreground=c["warning"])

        # 行インジケータ
        self._row_bars: Dict[int, AnimatedProgressBar] = {}

    # ── ログタブ ─────────────────────────────────────────
    def _build_log_tab(self, parent):
        c = self.theme.c
        tb = tk.Frame(parent, bg=c["bg3"])
        tb.pack(fill="x", padx=8, pady=4)
        ttk.Button(tb, text="ログクリア",
                   style="Ghost.TButton",
                   command=self._clear_log).pack(side="right", padx=(4, 0))
        ttk.Button(tb, text="💾 ログを保存",
                   style="Ghost.TButton",
                   command=self._export_log).pack(side="right")
        tk.Label(tb, text="ダウンロードログ",
                 bg=c["bg3"], fg=c["text2"],
                 font=("Yu Gothic UI", 9)).pack(side="left")

        txt_f = tk.Frame(parent, bg=c["bg2"])
        txt_f.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self._log_text = AutoScrollText(
            txt_f,
            bg=c["bg2"], fg=c["text"],
            font=("Consolas", 9),
            insertbackground=c["text"],
            selectbackground=c["accent"],
            relief="flat", bd=0,
            padx=8, pady=4,
            state="disabled",
            wrap="word",
        )
        vsb = ttk.Scrollbar(txt_f, orient="vertical",
                            command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True)

        # ログ色タグ
        self._log_text.tag_configure("info",
            foreground=c["accent"])
        self._log_text.tag_configure("warn",
            foreground=c["warning"])
        self._log_text.tag_configure("error",
            foreground=c["error"])
        self._log_text.tag_configure("done",
            foreground=c["success"])
        self._log_text.tag_configure("dim",
            foreground=c["text3"])

    # ── 履歴タブ ─────────────────────────────────────────
    def _build_history_tab(self, parent):
        c = self.theme.c
        tb = tk.Frame(parent, bg=c["bg3"])
        tb.pack(fill="x", padx=8, pady=4)
        ttk.Button(tb, text="履歴クリア",
                   style="Ghost.TButton",
                   command=self._clear_history).pack(side="right")
        tk.Label(tb, text="ダウンロード履歴",
                 bg=c["bg3"], fg=c["text2"],
                 font=("Yu Gothic UI", 9)).pack(side="left")

        cols = ("date", "title", "url", "status")
        hist_f = tk.Frame(parent, bg=c["bg2"])
        hist_f.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self._hist_tree = ttk.Treeview(
            hist_f, columns=cols, show="headings")
        vsb = ttk.Scrollbar(hist_f, orient="vertical",
                            command=self._hist_tree.yview)
        self._hist_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._hist_tree.pack(fill="both", expand=True)

        hdrs = [
            ("date",   "日時",      130),
            ("title",  "タイトル",  250),
            ("url",    "URL",       300),
            ("status", "結果",       70),
        ]
        for col, lbl, w in hdrs:
            self._hist_tree.heading(col, text=lbl)
            self._hist_tree.column(col, width=w)

        self._hist_tree.tag_configure("done",
            foreground=c["success"])
        self._hist_tree.tag_configure("error",
            foreground=c["error"])

        # ダブルクリックで URL をコピー
        self._hist_tree.bind("<Double-1>", self._hist_copy_url)

        # 既存履歴ロード
        self._reload_history()

    # ── ステータスバー ─────────────────────────────────────
    def _build_statusbar(self):
        c = self.theme.c
        sb = tk.Frame(self.root, bg=c["bg3"], height=26)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        ttk.Separator(self.root, orient="horizontal").pack(
            fill="x", side="bottom")

        self._status_lbl = tk.Label(
            sb, text="準備完了", bg=c["bg3"], fg=c["text2"],
            font=("Yu Gothic UI", 9), anchor="w")
        self._status_lbl.pack(side="left", padx=12)

        self._yt_dlp_lbl = tk.Label(
            sb,
            text=f"yt-dlp {'✓' if YT_DLP_OK else '✗ 未インストール'}",
            bg=c["bg3"],
            fg=c["success"] if YT_DLP_OK else c["error"],
            font=("Yu Gothic UI", 9))
        self._yt_dlp_lbl.pack(side="right", padx=12)

        tk.Label(sb, text="|", bg=c["bg3"], fg=c["border"]
                 ).pack(side="right")
        self._speed_lbl = tk.Label(
            sb, text="", bg=c["bg3"], fg=c["text2"],
            font=("Yu Gothic UI", 9))
        self._speed_lbl.pack(side="right", padx=8)

    # ══════════════════════════════════════════════════════
    #  設定保存・復元
    # ══════════════════════════════════════════════════════

    def _restore_config(self):
        pass  # すでに __init__ で Config.load() 済み

    def _save_opts(self):
        # UI構築途中はまだ変数が存在しないためスキップ
        if not hasattr(self, "_save_var"):
            return
        self.cfg["mode"]            = self._mode_var.get()   # ← 抜けていた
        self.cfg["video_fmt"]       = self._vfmt_var.get()
        self.cfg["audio_fmt"]       = self._afmt_var.get()
        self.cfg["quality"]         = self._quality_var.get()
        self.cfg["save_dir"]        = self._save_var.get()
        self.cfg["time_start"]      = self._ts_var.get()
        self.cfg["time_end"]        = self._te_var.get()
        self.cfg["concurrent"]      = self._concurrent_var.get()
        self.cfg["retries"]         = self._retries_var.get()
        self.cfg["rate_limit"]      = self._rate_var.get()
        self.cfg["cookie_file"]     = self._cookie_var.get()
        for k, v in self._opts_vars.items():
            self.cfg[k] = v.get()
        if hasattr(self, "_post_action_var"):
            self.cfg["post_action"] = self._post_action_var.get()
        self.cfg.save()

    # ══════════════════════════════════════════════════════
    #  URL 操作
    # ══════════════════════════════════════════════════════

    def _get_urls(self) -> List[str]:
        raw = self.url_text.get("1.0", "end")
        return extract_urls(raw)

    def _update_url_count(self):
        n = len(self._get_urls())
        self._url_count_lbl.config(text=f"{n} URL")

    def _clear_urls(self):
        self.url_text.delete("1.0", "end")
        self._update_url_count()

    def _paste_clipboard(self):
        try:
            txt = self.root.clipboard_get()
            urls = extract_urls(txt)
            if urls:
                self.url_text.insert("end",
                    "\n".join(urls) + "\n")
                self._update_url_count()
                self._log(f"クリップボードから {len(urls)} URL を追加", "info")
        except Exception:
            pass

    def _on_drop(self, event):
        data = event.data
        urls = extract_urls(data)
        if urls:
            self.url_text.insert("end",
                "\n".join(urls) + "\n")
            self._update_url_count()
            self._log(f"D&Dで {len(urls)} URL を追加", "info")

    _last_clip = ""

    def _watch_clipboard(self):
        try:
            clip = self.root.clipboard_get()
            if clip != self._last_clip:
                self._last_clip = clip
                urls = extract_urls(clip)
                if urls and not self._running:
                    # 入力欄が空のときだけ自動追加しない→通知のみ
                    self._status_lbl.config(
                        text=f"📋 クリップボード: {len(urls)} URLを検出")
        except Exception:
            pass
        self.root.after(1500, self._watch_clipboard)

    # ══════════════════════════════════════════════════════
    #  ダウンロード制御
    # ══════════════════════════════════════════════════════

    def _start_download(self):
        if not YT_DLP_OK:
            messagebox.showerror(
                "エラー",
                "yt-dlp がインストールされていません。\n"
                "pip install yt-dlp を実行してください。")
            return

        self._save_opts()
        urls = self._get_urls()
        if not urls:
            messagebox.showwarning("警告", "URLが入力されていません。")
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
            rename_name = (self._rename_var.get()
                           if hasattr(self, "_rename_var") else "")

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

        self._log(f"▶ {len(new_tasks)} 件のダウンロードを開始", "info")
        self._running = True
        self._dl_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self.dl.reset()
        self._launch_tasks(new_tasks)
        self._update_overall()

    def _launch_tasks(self, tasks: List[DownloadTask]):
        """タスクリストを並列スレッドで起動する"""
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
        """DL 実行後に全完了チェックを UI スレッドへ依頼する"""
        self.dl.run_task(task)
        self.root.after(0, self._check_all_done)

    # ── ③ URL 重複・無効チェック ────────────────────────
    def _check_urls(self, urls: List[str]) -> List[str]:
        """問題のある URL のリストを返す。空リストなら問題なし。"""
        issues: List[str] = []
        seen: set = set()
        url_pat = re.compile(r'^https?://.{4,}')
        for url in urls:
            if not url_pat.match(url):
                issues.append(f"無効な形式: {url[:60]}")
            elif url in seen:
                issues.append(f"重複URL: {url[:60]}")
            seen.add(url)
        return issues

    def _check_all_done(self):
        """全タスクが終了していたら完了処理を行う"""
        if not self.tasks:
            return
        all_done = all(
            t.state in (TaskState.DONE, TaskState.ERROR, TaskState.CANCELLED)
            for t in self.tasks
        )
        if all_done and self._running:
            self._running = False
            self._dl_btn.config(state="normal")
            self._stop_btn.config(state="disabled")
            done   = sum(1 for t in self.tasks if t.state == TaskState.DONE)
            errors = sum(1 for t in self.tasks if t.state == TaskState.ERROR)
            self._retry_btn.config(
                state="normal" if errors else "disabled")
            self._log(
                f"✓ 全ダウンロード完了 ({done}/{len(self.tasks)}件成功"
                + (f", {errors}件エラー" if errors else "") + ")", "done")
            desktop_notify("yt-dlp GUI",
                f"ダウンロード完了: {done}/{len(self.tasks)}件")
            # ② 完了後アクション
            self._run_post_action()
        self._update_overall()

    def _run_post_action(self):
        """② 完了後アクションを実行する"""
        action = self.cfg.get("post_action", "何もしない")
        if action == "フォルダを開く":
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
        elif action == "シャットダウン":
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

    # ── ⑤ ログ書き出し ────────────────────────────────
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
            content = self._log_text.get("1.0", "end")
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(content)
            self._log(f"ログを保存しました: {path}", "info")
        except Exception as e:
            messagebox.showerror("エラー", f"ログの保存に失敗しました:\n{e}")

    def _stop_download(self):
        self.dl.stop()
        self._log("■ ダウンロードを停止中…", "warn")
        self._stop_btn.config(state="disabled")
        self._running = False
        self._dl_btn.config(state="normal")

    def _retry_failed(self):
        failed = [t for t in self.tasks
                  if t.state in (TaskState.ERROR, TaskState.CANCELLED)]
        if not failed:
            return
        for task in failed:
            task.state    = TaskState.PENDING
            task.progress = 0.0
            task.error    = ""
            task.retry    = 0
            self._update_queue_row(task)

        self.dl.reset()
        self._running = True
        self._dl_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._retry_btn.config(state="disabled")

        for task in failed:
            t = threading.Thread(
                target=self.dl.run_task,
                args=(task,),
                daemon=True,
                name=f"retry-{task.idx}"
            )
            self.threads.append(t)
            t.start()

        self._log(f"↺ 失敗 {len(failed)} 件を再試行", "info")

    def _clear_queue(self):
        if self._running:
            messagebox.showwarning("警告", "ダウンロード中はキューをクリアできません。")
            return
        self.tasks.clear()
        for item in self._queue_tree.get_children():
            self._queue_tree.delete(item)
        self._row_bars.clear()
        self._update_overall()

    # ══════════════════════════════════════════════════════
    #  キューUI
    # ══════════════════════════════════════════════════════

    def _add_queue_row(self, task: DownloadTask):
        iid = str(task.idx)
        self._queue_tree.insert(
            "", "end", iid=iid,
            values=(
                task.idx + 1,
                task.display_name(),
                task.state.label(),
                "",
                "",
                "",
                "",
            ),
            tags=("pending",)
        )
        self._queue_tree.see(iid)

    def _update_queue_row(self, task: DownloadTask):
        iid = str(task.idx)
        if not self._queue_tree.exists(iid):
            return

        state = task.state
        pct_s = f"{task.progress:.0f}%" if task.progress else ""
        size_s = fmt_size(task.tot_bytes) if task.tot_bytes else ""

        tag = "pending"
        if state == TaskState.DONE:           tag = "done"
        elif state == TaskState.ERROR:        tag = "error"
        elif state == TaskState.DOWNLOADING:  tag = "active"
        elif state in (TaskState.CONVERTING,
                       TaskState.RETRYING):   tag = "warn"

        self._queue_tree.item(iid, values=(
            task.idx + 1,
            task.display_name(),
            state.label(),
            pct_s,
            task.speed,
            task.eta,
            size_s,
        ), tags=(tag,))

    def _select_all_queue(self):
        self._queue_tree.selection_set(
            self._queue_tree.get_children())

    def _remove_selected(self):
        sels = self._queue_tree.selection()
        for iid in sels:
            idx = int(iid)
            if self.tasks[idx].state == TaskState.DOWNLOADING:
                continue  # DL中は削除不可
            self._queue_tree.delete(iid)

    # ══════════════════════════════════════════════════════
    #  全体進捗
    # ══════════════════════════════════════════════════════

    def _update_overall(self):
        total  = len(self.tasks)
        done   = sum(1 for t in self.tasks if t.state == TaskState.DONE)
        errors = sum(1 for t in self.tasks if t.state == TaskState.ERROR)
        active = sum(1 for t in self.tasks if t.state == TaskState.DOWNLOADING)
        pending = sum(1 for t in self.tasks if t.state == TaskState.PENDING)

        if total == 0:
            self._overall_lbl.config(text="待機中")
            self._overall_stat.config(text="")
            self._overall_bar.set(0)
            return

        pct = done / total * 100
        self._overall_bar.set(pct)
        self._overall_lbl.config(
            text=f"{total}本中 {done}本完了"
                 + (f" ({errors}本エラー)" if errors else ""))
        stat_parts = []
        if active:  stat_parts.append(f"DL中: {active}本")
        if pending: stat_parts.append(f"待機: {pending}本")
        self._overall_stat.config(text="  ".join(stat_parts))

    # ══════════════════════════════════════════════════════
    #  ログ
    # ══════════════════════════════════════════════════════

    def _log(self, msg: str, tag: str = ""):
        self._log_text.append(msg, tag)

    def _clear_log(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    # ══════════════════════════════════════════════════════
    #  履歴
    # ══════════════════════════════════════════════════════

    def _reload_history(self):
        for item in self._hist_tree.get_children():
            self._hist_tree.delete(item)
        for entry in self.cfg["history"]:
            tag = "done" if entry.get("status") == "完了" else "error"
            self._hist_tree.insert("", "end",
                values=(
                    entry.get("date", ""),
                    entry.get("title", ""),
                    entry.get("url", ""),
                    entry.get("status", ""),
                ),
                tags=(tag,))

    def _add_history_entry(self, task: DownloadTask):
        entry = {
            "date":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title":  task.title or task.short_url(),
            "url":    task.url,
            "status": task.state.label(),
        }
        self.cfg.add_history(entry)
        self.cfg.save()
        tag = "done" if task.state == TaskState.DONE else "error"
        self._hist_tree.insert("", 0,
            values=(
                entry["date"], entry["title"],
                entry["url"],  entry["status"],
            ),
            tags=(tag,))

    def _clear_history(self):
        self.cfg["history"] = []
        self.cfg.save()
        for item in self._hist_tree.get_children():
            self._hist_tree.delete(item)

    def _hist_copy_url(self, event):
        sel = self._hist_tree.selection()
        if sel:
            vals = self._hist_tree.item(sel[0], "values")
            url  = vals[2] if len(vals) > 2 else ""
            if url:
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                self._status_lbl.config(text=f"URLをコピーしました: {url[:60]}")

    # ══════════════════════════════════════════════════════
    #  テーマ切替
    # ══════════════════════════════════════════════════════

    def _toggle_theme(self):
        self.theme.toggle()
        self.cfg["dark_mode"] = self.theme.dark
        self.cfg.save()
        messagebox.showinfo(
            "テーマ変更",
            "テーマを変更しました。\n次回起動時に完全に適用されます。\n"
            "（一部は即座に反映されます）")
        self._setup_style()

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

            # ステータス・速度表示
            if task.state == TaskState.DOWNLOADING:
                parts = []
                if task.speed: parts.append(f"速度: {task.speed}")
                if task.eta:   parts.append(f"残り: {task.eta}")
                if parts:
                    self._speed_lbl.config(text="  ".join(parts))
                    self._status_lbl.config(
                        text=f"DL中: {task.display_name()[:50]}")

        elif msg_type == "task_done":
            task: DownloadTask = payload
            self._log(f"✓ 完了: {task.display_name()}", "done")
            self._add_history_entry(task)

        elif msg_type == "task_error":
            task: DownloadTask = payload
            self._log(f"✗ エラー: {task.display_name()}\n  {task.error}", "error")
            self._add_history_entry(task)

        elif msg_type == "log":
            text: str = payload
            tag = ""
            lt  = text.lower()
            if "[err"  in lt: tag = "error"
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
