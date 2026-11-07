"""Build YtDisk.exe (single file, FFmpeg bundled, no console window).

    python build.py

Needs: pip install -r requirements.txt   (includes pyinstaller)
FFmpeg is taken from ./bin/ffmpeg.exe if present, otherwise from PATH.
Optional: put deno.exe (or node.exe) in ./bin to bundle a JavaScript runtime for YouTube.
"""
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEP = ";" if sys.platform == "win32" else ":"


def find(name):
    local = ROOT / "bin" / name
    if local.is_file():
        return str(local)
    return shutil.which(name)


def main():
    ffmpeg = find("ffmpeg.exe") or find("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg not found. Put ffmpeg.exe in ./bin or add it to PATH.")

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", "YtDisk", "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
           "--specpath", str(ROOT / "build"),
           "--add-data", f"{ROOT / 'ui'}{SEP}ui",
           "--add-data", f"{ROOT / 'ui desien'}{SEP}ui desien",     # alternative designs (switchable in-app)
           "--add-binary", f"{ffmpeg}{SEP}.",
           "--collect-submodules", "yt_dlp",
           "--collect-submodules", "webview",
           "--hidden-import", "reedsolo",
           "--exclude-module", "tkinter"]
    if importlib.util.find_spec("yt_dlp_ejs"):
        cmd += ["--collect-all", "yt_dlp_ejs"]
    bundled_js = False
    for rt in ("deno.exe", "node.exe"):
        p = (ROOT / "bin" / rt)
        if p.is_file():
            cmd += ["--add-binary", f"{p}{SEP}."]
            bundled_js = True
    if not bundled_js:
        sys.exit("No JavaScript runtime in ./bin (node.exe or deno.exe). YouTube would not work on a clean PC.")
    icon = ROOT / "ui" / "icon.ico"
    if icon.is_file():
        cmd += ["--icon", str(icon)]
    cmd.append(str(ROOT / "app.py"))

    print("FFmpeg:", ffmpeg)
    subprocess.check_call(cmd, cwd=ROOT)
    exe = ROOT / "dist" / "YtDisk.exe"
    print(f"\nDone: {exe}  ({exe.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
