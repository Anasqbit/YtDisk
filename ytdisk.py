"""YTDISK core: file <-> 4K video.

Used by the CLI (python ytdisk.py ...) and by the GUI (app.py).
The video format is unchanged from the original version.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

#1- config


GRID_W, GRID_H = 1920, 1080
OUT_W, OUT_H = 3840, 2160
FPS = 30

BLOCK = 4

NSYM = 32
RS_N = 255

HEADER_BLOCK = 16
HEADER_NSYM = 64
HEADER_FRAMES = 30
MAGIC = "YTDISK"
VERSION = 1
CRF = 12


def capacity(block=BLOCK, nsym=NSYM):
    cols, rows = GRID_W // block, GRID_H // block
    bytes_per_frame = cols * rows / 8
    useful_per_sec = bytes_per_frame * (RS_N - nsym) / RS_N * FPS
    return {
        "grid": f"{cols}x{rows}",
        "KB_per_frame": bytes_per_frame / 1024,
        "KB_per_sec": useful_per_sec / 1024,
        "minutes_per_GB": 1024 ** 3 / useful_per_sec / 60,
    }


#0- errors, cancel, process helpers (used by the GUI)


class Cancelled(Exception):
    """Raised when should_cancel() returns True."""


ERROR_TEXT = {
    "no_ffmpeg": "ffmpeg not found. Install it, or put ffmpeg.exe next to the app",
    "ffmpeg": "ffmpeg failed",
    "file_missing": "file not found",
    "empty_file": "the file is empty",
    "bad_params": "invalid options",
    "no_header": "no valid header found, is this a YTDISK video?",
    "bad_video": "ffmpeg could not read this video",
    "need_password": "this file is encrypted, pass --password",
    "wrong_password": "decryption failed: wrong password, or the data got corrupted",
    "rs_failed": "Too many errors, Reed-Solomon gave up. Try a bigger --block or a higher --nsym",
    "too_short": "video too short, data frames are missing",
}


class YtdiskError(Exception):
    """Error with a machine-readable code (the GUI translates the code)."""

    def __init__(self, code, detail="", **info):
        self.code = code
        self.detail = detail
        self.info = info
        base = ERROR_TEXT.get(code, code)
        self.message = f"{base} ({detail})" if detail else base
        super().__init__(self.message)


def _check(should_cancel):
    if should_cancel is not None and should_cancel():
        raise Cancelled()


def _noop_progress(stage, frac, info=None):
    pass


def app_dir() -> Path:
    """Folder with bundled files (PyInstaller temp dir, or the script folder)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def ffmpeg_exe() -> str:
    """Bundled ffmpeg first, then ./bin, then PATH."""
    here = Path(__file__).resolve().parent
    for d in (app_dir(), app_dir() / "bin", here, here / "bin"):
        for n in ("ffmpeg.exe", "ffmpeg"):
            p = d / n
            if p.is_file():
                return str(p)
    return shutil.which("ffmpeg") or "ffmpeg"


def _popen_kwargs():
    # no flashing console windows when running as a windowed EXE
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def _spawn(cmd, **kw):
    try:
        return subprocess.Popen(cmd, **kw, **_popen_kwargs())
    except FileNotFoundError:
        raise YtdiskError("no_ffmpeg") from None


class _Drain(threading.Thread):
    """Reads a pipe in the background so ffmpeg never blocks on stderr."""

    def __init__(self, stream):
        super().__init__(daemon=True)
        self.stream, self.buf = stream, []
        self.start()

    def run(self):
        try:
            for line in iter(self.stream.readline, b""):
                self.buf.append(line.decode(errors="replace"))
        except Exception:
            pass

    @property
    def text(self):
        return "".join(self.buf[-12:]).strip()


def ffmpeg_version() -> str:
    try:
        r = subprocess.run([ffmpeg_exe(), "-version"], capture_output=True, timeout=10, **_popen_kwargs())
        first = r.stdout.decode(errors="replace").splitlines()[0]
        return first.replace("ffmpeg version", "").strip().split(" ")[0]
    except Exception:
        return ""


def unique_path(p) -> Path:
    p = Path(p)
    if not p.exists():
        return p
    for i in range(1, 10000):
        q = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists():
            return q
    return p


#2- FILE TO BIT


def bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def bits_to_bytes(bits) -> bytes:
    bits = np.asarray(bits, dtype=np.uint8)
    pad = (-len(bits)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    return np.packbits(bits).tobytes()


class _BitSink:
    """Collects frame bits as packed bytes (8x less memory than keeping bit arrays)."""

    def __init__(self):
        self.parts, self.carry = [], np.zeros(0, np.uint8)

    def add(self, bits):
        if len(self.carry):
            bits = np.concatenate([self.carry, bits])
        n = len(bits) // 8 * 8
        if n:
            self.parts.append(np.packbits(bits[:n]))
        self.carry = bits[n:].copy()

    def finish(self) -> bytes:
        if len(self.carry):
            self.parts.append(np.packbits(self.carry))
            self.carry = np.zeros(0, np.uint8)
        return np.concatenate(self.parts).tobytes() if self.parts else b""


#3- AES


SALT_LEN, NONCE_LEN = 16, 12
AES_OVERHEAD = SALT_LEN + NONCE_LEN + 16


def _derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(password.encode())


def encrypt(data: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(SALT_LEN), os.urandom(NONCE_LEN)
    return salt + nonce + AESGCM(_derive_key(password, salt)).encrypt(nonce, data, None)


def decrypt(blob: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce, ct = blob[:SALT_LEN], blob[SALT_LEN:SALT_LEN + NONCE_LEN], blob[SALT_LEN + NONCE_LEN:]
    return AESGCM(_derive_key(password, salt)).decrypt(nonce, ct, None)


#4- RS


def num_codewords(payload_len: int, nsym: int = NSYM) -> int:
    return 0 if nsym == 0 else math.ceil(payload_len / (RS_N - nsym))


def ecc_encode(data: bytes, nsym: int = NSYM, progress=None, should_cancel=None) -> bytes:
    if nsym == 0:
        return data
    from reedsolo import RSCodec
    k = RS_N - nsym
    data = data + bytes((-len(data)) % k)
    rsc, out, step = RSCodec(nsym), bytearray(), k * 256     # slices of whole codewords: same output
    for off in range(0, len(data), step):
        _check(should_cancel)
        out += rsc.encode(data[off:off + step])
        if progress:
            progress(min(1.0, (off + step) / len(data)))
    codewords = np.frombuffer(bytes(out), np.uint8).reshape(-1, RS_N)
    return codewords.T.copy().tobytes()                      # the transpose is the interleaving


def ecc_decode(data: bytes, n_codewords: int, nsym: int = NSYM, progress=None, should_cancel=None):
    if nsym == 0:
        return data, 0
    from reedsolo import ReedSolomonError, RSCodec
    total = n_codewords * RS_N
    if len(data) < total:
        raise ReedSolomonError("not enough data")
    codewords = np.frombuffer(data[:total], np.uint8).reshape(RS_N, n_codewords).T
    rsc, out, fixed = RSCodec(nsym), bytearray(), 0
    for i, cw in enumerate(codewords):
        if i % 64 == 0:
            _check(should_cancel)
            if progress:
                progress(i / n_codewords)
        try:
            msg, _, errata = rsc.decode(cw.tobytes())
        except ReedSolomonError as e:
            raise ReedSolomonError(f"codeword {i}/{n_codewords} unrecoverable") from e
        fixed += len(errata)
        out += msg
    return bytes(out), fixed


# 5 - VIDEO

def grid(block: int):
    return GRID_W // block, GRID_H // block


def bits_per_frame(block: int = BLOCK) -> int:
    cols, rows = grid(block)
    return cols * rows


def bits_to_frame(bits, block: int = BLOCK) -> np.ndarray:
    cols, rows = grid(block)
    n = cols * rows
    bits = np.asarray(bits, dtype=np.uint8)
    if len(bits) < n:
        bits = np.concatenate([bits, np.zeros(n - len(bits), np.uint8)])
    small = bits[:n].reshape(rows, cols) * 255
    big = small.repeat(block, axis=0).repeat(block, axis=1)
    frame = np.zeros((GRID_H, GRID_W), np.uint8)
    frame[:rows * block, :cols * block] = big
    return frame


def frame_to_bits(frame: np.ndarray, block: int = BLOCK) -> np.ndarray:
    cols, rows = grid(block)
    blocks = frame[:rows * block, :cols * block].astype(np.float32).reshape(rows, block, cols, block)
    m = block // 4
    if m:
        blocks = blocks[:, m:block - m, :, m:block - m]
    return (blocks.mean(axis=(1, 3)) > 127).astype(np.uint8).ravel()


#6 - HEADER FILES

_H_CAPACITY = bits_per_frame(HEADER_BLOCK) // 8
_H_CODEWORDS = _H_CAPACITY // RS_N
_H_MAX_DATA = _H_CODEWORDS * (RS_N - HEADER_NSYM)


def make_header_frame(meta: dict) -> np.ndarray:
    from reedsolo import RSCodec
    raw = json.dumps(meta, separators=(",", ":")).encode()
    data = len(raw).to_bytes(2, "big") + raw
    if len(data) > _H_MAX_DATA:
        raise ValueError("header too big (file name too long?)")
    data += bytes(_H_MAX_DATA - len(data))
    return bits_to_frame(bytes_to_bits(bytes(RSCodec(HEADER_NSYM).encode(data))), HEADER_BLOCK)


def read_header_frame(frame: np.ndarray):
    from reedsolo import ReedSolomonError, RSCodec
    data = bits_to_bytes(frame_to_bits(frame, HEADER_BLOCK))[:_H_CODEWORDS * RS_N]
    try:
        decoded = bytes(RSCodec(HEADER_NSYM).decode(data)[0])
        meta = json.loads(decoded[2:2 + int.from_bytes(decoded[:2], "big")])
    except (ReedSolomonError, ValueError, UnicodeDecodeError):
        return None
    return meta if isinstance(meta, dict) and meta.get("magic") == MAGIC else None


#7 - video export

def open_writer(path: str, upscale_4k: bool = True, fps: int = FPS, crf: int = CRF):
    scale = ["-vf", f"scale={OUT_W}:{OUT_H}:flags=neighbor"] if upscale_4k else []
    cmd = [
        ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "gray",
        "-s", f"{GRID_W}x{GRID_H}", "-r", str(fps),
        "-i", "-",
        *scale,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        path,
    ]
    proc = _spawn(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    proc._drain = _Drain(proc.stderr)
    return proc


def close_writer(proc):
    proc.stdin.close()
    rc = proc.wait()
    proc._drain.join(1)
    if rc != 0:
        raise YtdiskError("ffmpeg", proc._drain.text)


def _kill_writer(proc):
    for fn in (lambda: proc.stdin.close(), lambda: proc.kill(), lambda: proc.wait(timeout=5)):
        try:
            fn()
        except Exception:
            pass


def read_frames(path: str, diag: dict = None):
    cmd = [ffmpeg_exe(), "-loglevel", "error", "-i", path,
           "-vf", f"scale={GRID_W}:{GRID_H}:flags=area",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = _spawn(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    drain = _Drain(proc.stderr)
    size = GRID_W * GRID_H
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(GRID_H, GRID_W)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()
        drain.join(0.5)
        if diag is not None:
            diag["stderr"] = drain.text


#8- encoder

def estimate(size: int, block: int = BLOCK, nsym: int = NSYM, encrypted: bool = False) -> dict:
    """Video length / frames for a file of `size` bytes (no encoding done)."""
    payload = size + (AES_OVERHEAD if encrypted else 0)
    ecc_len = num_codewords(payload, nsym) * RS_N if nsym else payload
    frames = math.ceil(ecc_len * 8 / bits_per_frame(block)) if ecc_len else 0
    return {
        "frames": frames,
        "seconds": (HEADER_FRAMES + frames) / FPS,
        "overhead_pct": (ecc_len / payload - 1) * 100 if payload else 0,
    }


def encode_file(in_path, out_path, block=BLOCK, nsym=NSYM, password=None,
                on_progress=None, on_log=None, should_cancel=None):
    """file -> video. Stages reported: read, encrypt (only with password), ecc, frames, finish."""
    prog = on_progress or _noop_progress
    log = on_log or (lambda m: None)
    t0 = time.time()
    in_path, out_path = Path(in_path), Path(out_path)
    if not in_path.is_file():
        raise YtdiskError("file_missing", str(in_path))
    if not (2 <= int(block) <= 32) or not (0 <= int(nsym) <= 200):
        raise YtdiskError("bad_params")

    prog("read", 0.0)
    _check(should_cancel)
    data = in_path.read_bytes()
    if not data:
        raise YtdiskError("empty_file")
    size = len(data)
    sha = hashlib.sha256(data).hexdigest()
    prog("read", 1.0)

    if password:
        prog("encrypt", 0.0)
        payload = encrypt(data, password)
        del data
        prog("encrypt", 1.0)
    else:
        payload = data
    _check(should_cancel)

    ecc = ecc_encode(payload, nsym, lambda f: prog("ecc", f), should_cancel)
    prog("ecc", 1.0)

    arr = np.frombuffer(ecc, np.uint8)
    total_bits = len(ecc) * 8
    bpf = bits_per_frame(block)
    n_frames = math.ceil(total_bits / bpf)
    total_frames = HEADER_FRAMES + n_frames

    def frame_bits(i):
        s = i * bpf
        e = min(s + bpf, total_bits)
        b0, b1 = s // 8, (e + 7) // 8
        off = s - b0 * 8
        return np.unpackbits(arr[b0:b1])[off:off + (e - s)]

    meta = {
        "magic": MAGIC, "v": VERSION, "name": in_path.name, "size": size,
        "sha256": sha, "payload_len": len(payload),
        "codewords": num_codewords(len(payload), nsym),
        "block": int(block), "nsym": int(nsym), "frames": n_frames, "encrypted": bool(password),
    }

    writer = open_writer(str(out_path))
    ok = False
    try:
        hb = make_header_frame(meta).tobytes()
        done = 0
        prog("frames", 0.0)
        for _ in range(HEADER_FRAMES):
            _check(should_cancel)
            writer.stdin.write(hb)
            done += 1
        for i in range(n_frames):
            _check(should_cancel)
            writer.stdin.write(bits_to_frame(frame_bits(i), block).tobytes())
            done += 1
            if i % 3 == 0 or i == n_frames - 1:
                prog("frames", done / total_frames)
        prog("frames", 1.0)
        prog("finish", 0.0)
        close_writer(writer)
        prog("finish", 1.0)
        ok = True
    except OSError:
        writer._drain.join(1)
        raise YtdiskError("ffmpeg", writer._drain.text) from None
    finally:
        if not ok:
            _kill_writer(writer)
            try:
                out_path.unlink()
            except OSError:
                pass

    info = dict(meta, out=str(out_path), video_bytes=out_path.stat().st_size,
                video_seconds=total_frames / FPS, ecc_len=len(ecc), elapsed=time.time() - t0)
    log(f"file: {meta['name']} ({size:,} bytes)")
    log("no error correction (nsym=0)" if nsym == 0 else
        f"with ECC: {len(ecc):,} bytes (+{(len(ecc) / len(payload) - 1) * 100:.0f}%)")
    log(f"video: {out_path.name} {OUT_W}x{OUT_H} {info['video_seconds']:.1f}s {info['video_bytes'] / 1e6:.1f} MB")
    log(f"sha256: {sha[:16]}...")
    return info


#9- decoder

def decode_video_ex(video_path, out_dir=".", password=None, on_progress=None, on_log=None,
                    should_cancel=None, overwrite=True):
    """video -> file. Stages: header, frames, ecc, decrypt (only if encrypted), verify.
    Returns a dict, raises YtdiskError / Cancelled."""
    from cryptography.exceptions import InvalidTag
    from reedsolo import ReedSolomonError

    prog = on_progress or _noop_progress
    log = on_log or (lambda m: None)
    t0 = time.time()
    video_path = Path(video_path)
    if not video_path.is_file():
        raise YtdiskError("file_missing", str(video_path))

    diag = {}
    frames = read_frames(str(video_path), diag)
    sink = _BitSink()
    try:
        prog("header", 0.0)
        meta, seen = None, 0
        for i, frame in enumerate(frames):
            _check(should_cancel)
            seen = i + 1
            meta = read_header_frame(frame)
            if meta or i > 90:
                break
            prog("header", min(0.95, seen / 92))
        if not meta:
            frames.close()
            if seen == 0:
                raise YtdiskError("bad_video", diag.get("stderr", ""))
            raise YtdiskError("no_header")
        if meta.get("encrypted") and not password:
            raise YtdiskError("need_password", name=meta.get("name", ""))
        prog("header", 1.0, meta)
        log(f"header: {meta['name']} {meta['size']:,} bytes block={meta['block']} "
            f"frames={meta['frames']} encrypted={meta['encrypted']}")

        n, got = meta["frames"], 0
        prog("frames", 0.0)
        for frame in frames:                       # skip the remaining header frames
            _check(should_cancel)
            if read_header_frame(frame) is None:
                sink.add(frame_to_bits(frame, meta["block"]))
                got = 1
                break
        for frame in frames:
            if got >= n:
                break
            _check(should_cancel)
            sink.add(frame_to_bits(frame, meta["block"]))
            got += 1
            if got % 3 == 0 or got == n:
                prog("frames", got / n)
        if got < n:
            raise YtdiskError("too_short", f"{got}/{n}", got=got, need=n)
        prog("frames", 1.0)
    finally:
        frames.close()

    raw = sink.finish()
    prog("ecc", 0.0)
    try:
        payload, fixed = ecc_decode(raw, meta["codewords"], meta["nsym"], lambda f: prog("ecc", f), should_cancel)
    except ReedSolomonError as e:
        raise YtdiskError("rs_failed", str(e)) from None
    del raw
    payload = payload[:meta["payload_len"]]
    prog("ecc", 1.0)
    log(f"Reed-Solomon fixed {fixed:,} bytes" if meta["nsym"] else
        "no error correction, whatever arrived is what you get")

    if meta["encrypted"]:
        prog("decrypt", 0.0)
        try:
            payload = decrypt(payload, password)
        except InvalidTag:
            raise YtdiskError("wrong_password") from None
        prog("decrypt", 1.0)

    prog("verify", 0.0)
    sha = hashlib.sha256(payload).hexdigest()
    ok = sha == meta["sha256"]
    out = Path(out_dir) / Path(meta["name"]).name
    out.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        out = unique_path(out)
    out.write_bytes(payload)
    prog("verify", 1.0)
    log(f"expected: {meta['sha256'][:16]}...")
    log(f"got:      {sha[:16]}...")
    return {"ok": ok, "out": str(out), "name": out.name, "size": len(payload), "sha": sha,
            "expected": meta["sha256"], "fixed": fixed, "encrypted": bool(meta["encrypted"]),
            "elapsed": time.time() - t0}


def decode_video(video_path, out_dir=".", password=None, **kw):
    """Old API: returns (ok, out_path) and prints errors."""
    try:
        r = decode_video_ex(video_path, out_dir, password, **kw)
    except YtdiskError as e:
        print(" " + e.message)
        return False, None
    return r["ok"], Path(r["out"])


#10 - main

def _cli_progress():
    last = {}

    def cb(stage, frac, info=None):
        pct = int(frac * 100)
        if last.get(stage) == pct:
            return
        last[stage] = pct
        print(f"\r  {stage}: {pct:3d}%", end="", flush=True)
        if frac >= 1:
            print()
    return cb


def main():
    p = argparse.ArgumentParser(prog="ytdisk", description="Store files inside 4K YouTube videos")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("encode", help="file -> 4K video")
    e.add_argument("file")
    e.add_argument("-o", "--output", default="upload.mp4")
    e.add_argument("--block", type=int, default=BLOCK)
    e.add_argument("--nsym", type=int, default=NSYM)
    e.add_argument("--password")

    d = sub.add_parser("decode", help="video -> file")
    d.add_argument("video")
    d.add_argument("-o", "--output", default="restored")
    d.add_argument("--password")

    a = p.parse_args()
    try:
        if a.cmd == "encode":
            r = encode_file(a.file, a.output, a.block, a.nsym, a.password,
                            on_progress=_cli_progress(), on_log=lambda m: print(" " + m))
            print(f" done in {r['elapsed']:.1f}s")
        else:
            r = decode_video_ex(a.video, a.output, a.password,
                                on_progress=_cli_progress(), on_log=lambda m: print(" " + m))
            print((" IDENTICAL, byte for byte!" if r["ok"] else " HASH MISMATCH, file is corrupted")
                  + f"  -> {r['out']}    {r['elapsed']:.1f}s")
            sys.exit(0 if r["ok"] else 1)
    except YtdiskError as err:
        print("\n " + err.message)
        sys.exit(1)


if __name__ == "__main__":
    main()
