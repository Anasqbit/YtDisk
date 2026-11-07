"""yt-dlp wrapper: check a link, download the 4K video stream with real progress."""
import importlib.util
import os
import shutil
from pathlib import Path

import ytdisk
from ytdisk import Cancelled, YtdiskError

BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")


def js_runtime():
    """Find a JavaScript runtime for yt-dlp (needed by YouTube).
    Returns ({name: {'path': ...}} or None, name or None)."""
    app = ytdisk.app_dir()
    names = (("deno", "deno"), ("node", "node"), ("bun", "bun"), ("quickjs", "qjs"))
    # 1) runtime bundled inside the EXE (or ./bin) always wins, so it works on a clean PC
    for name, exe in names:
        found = next((str(p) for p in (app / f"{exe}.exe", app / "bin" / f"{exe}.exe") if p.is_file()), None)
        if found:
            return {name: {"path": found}}, name
    # 2) otherwise fall back to whatever is installed on the system
    for name, exe in names:
        path = shutil.which(exe)
        if path:
            return {name: {"path": path}}, name
    return None, None


def js_runtime_path():
    rt, name = js_runtime()
    return rt[name]["path"] if rt else None


def status():
    import yt_dlp
    _, rt = js_runtime()
    path = js_runtime_path()
    try:
        bundled = bool(path) and Path(path).resolve().is_relative_to(ytdisk.app_dir().resolve())
    except Exception:
        bundled = False
    return {
        "ytdlp": yt_dlp.version.__version__,
        "js_runtime": rt,
        "js_runtime_path": path,
        "js_runtime_bundled": bundled,
        "ejs": importlib.util.find_spec("yt_dlp_ejs") is not None,
    }


def _base_opts(cookies_browser=None):
    rt, _ = js_runtime()
    o = {
        "quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
        "socket_timeout": 30, "retries": 5, "fragment_retries": 10,
    }
    ff = ytdisk.ffmpeg_exe()
    if os.path.isfile(ff):
        o["ffmpeg_location"] = ff
    if rt:
        o["js_runtimes"] = rt
    if cookies_browser in BROWSERS:
        o["cookiesfrombrowser"] = (cookies_browser,)
    return o


def _map_error(err: Exception) -> YtdiskError:
    msg = str(err)
    low = msg.lower()
    if "requested format is not available" in low:
        return YtdiskError("no_4k")
    if "not a bot" in low or "sign in to confirm" in low:
        return YtdiskError("bot_check")
    if "ffmpeg" in low and "not found" in low:
        return YtdiskError("no_ffmpeg")
    clean = msg.replace("ERROR: ", "").strip()
    return YtdiskError("yt_error", clean[:300])


def check_url(url, cookies_browser=None):
    import yt_dlp
    from yt_dlp.utils import DownloadError
    try:
        with yt_dlp.YoutubeDL({**_base_opts(cookies_browser), "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise _map_error(e) from None
    except Exception as e:
        raise YtdiskError("yt_error", str(e)[:300]) from None
    heights = sorted({f["height"] for f in info.get("formats", [])
                      if f.get("height") and f.get("vcodec") not in (None, "none")})
    return {
        "id": info.get("id"), "title": info.get("title"), "channel": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"), "thumbnail": info.get("thumbnail"),
        "max_height": max(heights) if heights else 0, "has_4k": any(h >= 2160 for h in heights),
    }


def download_video(url, out_dir, on_progress, should_cancel=None, cookies_browser=None, fmt=None):
    """Downloads the video stream only (no audio). on_progress(frac, info_dict). Returns the file path."""
    import yt_dlp
    from yt_dlp.utils import DownloadCancelled, DownloadError

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    found = {}

    def hook(d):
        if should_cancel and should_cancel():
            raise DownloadCancelled()
        st = d.get("status")
        if st == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            on_progress(min(0.999, done / total) if total else 0.0,
                        {"done": done, "total": total, "speed": d.get("speed"), "eta": d.get("eta")})
        elif st == "finished":
            found["path"] = d.get("filename")
            on_progress(1.0, {"done": d.get("downloaded_bytes"), "total": d.get("downloaded_bytes")})

    opts = {
        **_base_opts(cookies_browser),
        "format": fmt or "bestvideo[height>=2160]",
        "outtmpl": str(out_dir / "ytdisk_%(id)s.%(ext)s"),
        "progress_hooks": [hook],
        "continuedl": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            guess = ydl.prepare_filename(info)
    except DownloadCancelled:
        raise Cancelled() from None
    except DownloadError as e:
        if should_cancel and should_cancel():
            raise Cancelled() from None
        raise _map_error(e) from None

    path = found.get("path") or guess
    if not path or not os.path.isfile(path):
        cands = sorted(out_dir.glob(f"ytdisk_{info.get('id')}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        cands = [c for c in cands if c.suffix not in (".part", ".ytdl")]
        if not cands:
            raise YtdiskError("yt_error", "downloaded file not found")
        path = str(cands[0])
    return path
