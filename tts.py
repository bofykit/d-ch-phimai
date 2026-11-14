"""Lồng tiếng offline bằng Sherpa-ONNX (VITS/Piper)."""
import tarfile
import urllib.request
import wave
from pathlib import Path

import numpy as np

from common import TEMP_DIR, TTS_DIR

BASE_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"


def download_model(name: str, log) -> Path:
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    target = TTS_DIR / name
    if target.exists():
        return target
    tar = TTS_DIR / f"{name}.tar.bz2"
    log(f"Đang tải model giọng đọc {name} …")
    urllib.request.urlretrieve(BASE_URL + name + ".tar.bz2", tar)
    with tarfile.open(tar, "r:bz2") as t:
        t.extractall(TTS_DIR)
    tar.unlink(missing_ok=True)
    log("Tải xong.")
    return target


def _build(name: str):
    import sherpa_onnx
    d = TTS_DIR / name
    if not d.exists():
        raise RuntimeError(f"Chưa có model TTS '{name}'. Vào tab Cài đặt → Tải model giọng đọc.")
    onnx = next(d.glob("*.onnx"))
    lex = d / "lexicon.txt"
    espeak = d / "espeak-ng-data"
    vits = sherpa_onnx.OfflineTtsVitsModelConfig(
        model=str(onnx), tokens=str(d / "tokens.txt"),
        data_dir=str(espeak) if espeak.exists() else "",
        lexicon=str(lex) if lex.exists() else "")
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=4, provider="cpu"))
    return sherpa_onnx.OfflineTts(cfg)


def synthesize_track(segs, model_name: str, sid: int, out_wav, log, progress=None, cancel=None):
    """Đọc từng câu, căn theo mốc thời gian phụ đề; câu quá dài thì tăng tốc đọc để vừa khung."""
    tts = _build(model_name)
    sr = None
    pieces = []
    for i, s in enumerate(segs):
        if cancel and cancel():
            raise RuntimeError("Đã dừng.")
        slot = max(0.3, s["end"] - s["start"])
        a = tts.generate(s["text"], sid=sid, speed=1.0)
        sr = a.sample_rate
        x = np.asarray(a.samples, dtype=np.float32)
        dur = len(x) / sr
        if dur > slot * 1.05:
            a = tts.generate(s["text"], sid=sid, speed=min(1.8, dur / slot))
            x = np.asarray(a.samples, dtype=np.float32)
        pieces.append((int(s["start"] * sr), x))
        if progress:
            progress((i + 1) / len(segs))
    if sr is None:
        raise RuntimeError("Không có câu nào để lồng tiếng.")
    total = max(st + len(x) for st, x in pieces) + sr
    track = np.zeros(total, dtype=np.float32)
    for st, x in pieces:
        track[st:st + len(x)] += x
    track = np.clip(track, -1, 1)
    TEMP_DIR.mkdir(exist_ok=True)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((track * 32767).astype(np.int16).tobytes())
    log(f"Đã tạo track lồng tiếng ({len(pieces)} câu).")
