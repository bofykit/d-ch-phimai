"""Đường dẫn, cấu hình, đọc/ghi SRT dùng chung."""
import json
import re
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


APP = app_dir()
CONFIG_PATH = APP / "config.json"
KEYS_PATH = APP / "groq_keys.json"      # KHÔNG push lên GitHub (đã có trong .gitignore)
MODELS_DIR = APP / "models"
TTS_DIR = MODELS_DIR / "tts"
TEMP_DIR = APP / "temp"
FFMPEG = str(APP / "ffmpeg.exe") if (APP / "ffmpeg.exe").exists() else "ffmpeg"

DEFAULTS = {
    "model": "llama-3.3-70b-versatile",
    "whisper_model": "whisper-large-v3-turbo",
    "src_lang": "auto",
    "target_lang": "Tiếng Việt",
    "font_size": 14,
    "pitch": 0.0,          # bán cung (semitone), -12..12
    "tempo": 1.0,          # 0.5..2.0
    "orig_vol": 0.0,       # âm lượng tiếng gốc khi lồng tiếng (0 = tắt hẳn)
    "dub_vol": 1.0,
    "do_dub": True,
    "do_burn": True,
    "strip_meta": True,
    "tts_model": "vits-piper-vi_VN-vais1000-medium",
    "tts_sid": 0,
    "out_dir": str(APP / "output"),
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def load_keys() -> list[str]:
    if KEYS_PATH.exists():
        try:
            return [k for k in json.loads(KEYS_PATH.read_text(encoding="utf-8")) if k.strip()]
        except Exception:
            return []
    return []


def save_keys(keys: list[str]) -> None:
    KEYS_PATH.write_text(json.dumps(keys, indent=2), encoding="utf-8")


# ---------------- SRT ----------------
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _to_sec(s: str) -> float:
    h, m, sec, ms = _TS.match(s.strip()).groups()
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms.ljust(3, "0")[:3]) / 1000


def _fmt(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def parse_srt(path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="ignore").replace("\r\n", "\n")
    segs = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, l in enumerate(lines):
            if "-->" in l:
                a, b = l.split("-->")
                body = " ".join(lines[i + 1:]).strip()
                if body:
                    segs.append({"start": _to_sec(a), "end": _to_sec(b), "text": body})
                break
    return segs


def write_srt(segs: list[dict], path) -> None:
    out = []
    for i, s in enumerate(segs, 1):
        out.append(f"{i}\n{_fmt(s['start'])} --> {_fmt(s['end'])}\n{s['text']}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")
