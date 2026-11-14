"""Lồng tiếng offline. Hai engine: VieNeu-TTS v3 Turbo (ONNX, mặc định) hoặc Sherpa-ONNX (VITS/Piper)."""
import tarfile
import urllib.request
import wave
from pathlib import Path

import numpy as np

from common import TEMP_DIR, TTS_DIR
from ffmpeg_utils import stretch

BASE_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"


# ======================= VieNeu-TTS =======================
class VieNeuEngine:
    def __init__(self, cfg, log):
        from vieneu import Vieneu  # import muộn để engine Sherpa không cần cài vieneu
        kw = {"backend": "onnx"}
        if cfg.get("vieneu_precision") == "int8":
            kw["precision"] = "int8"
        log("Đang nạp VieNeu-TTS (lần đầu sẽ tải model từ Hugging Face, cần mạng 1 lần)…")
        self.tts = Vieneu(**kw)
        self.sr = int(getattr(self.tts, "sample_rate", 0) or 48000)
        self.voice = (cfg.get("vieneu_voice") or "").strip()
        self.log = log

    def list_voices(self):
        return self.tts.list_preset_voices()

    def _voice_candidates(self):
        if not self.voice:
            return [None]
        cands = [self.voice]
        try:
            for label, vid in self.list_voices():
                if self.voice.lower() in (str(label).lower(), str(vid).lower()):
                    cands += [label, vid]
        except Exception:  # noqa: BLE001
            pass
        out, seen = [], set()
        for c in cands + [None]:  # cuối cùng thử giọng mặc định
            if c not in seen:
                seen.add(c); out.append(c)
        return out

    def synth(self, text):
        last = None
        for v in self._voice_candidates():
            try:
                audio = self.tts.infer(text, voice=v) if v else self.tts.infer(text)
                self.voice = v or ""   # nhớ cách gọi đã chạy được
                return np.asarray(audio, dtype=np.float32).reshape(-1), self.sr
            except Exception as e:  # noqa: BLE001
                last = e
        raise RuntimeError(f"VieNeu không đọc được: {last}")


# ======================= Sherpa-ONNX =======================
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


class SherpaEngine:
    def __init__(self, cfg, log):
        import sherpa_onnx
        name = cfg["tts_model"]
        d = TTS_DIR / name
        if not d.exists():
            raise RuntimeError(f"Chưa có model TTS '{name}'. Vào tab Cài đặt → Tải model giọng.")
        onnx = next(d.glob("*.onnx"))
        lex, espeak = d / "lexicon.txt", d / "espeak-ng-data"
        vits = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=str(onnx), tokens=str(d / "tokens.txt"),
            data_dir=str(espeak) if espeak.exists() else "",
            lexicon=str(lex) if lex.exists() else "")
        c = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=4, provider="cpu"))
        self.tts = sherpa_onnx.OfflineTts(c)
        self.sid = int(cfg.get("tts_sid", 0))
        self.sr = int(self.tts.sample_rate) or 22050

    def synth(self, text):
        a = self.tts.generate(text, sid=self.sid, speed=1.0)
        return np.asarray(a.samples, dtype=np.float32), int(a.sample_rate or self.sr)


def make_engine(cfg, log):
    return SherpaEngine(cfg, log) if cfg.get("tts_engine") == "sherpa" else VieNeuEngine(cfg, log)


# ======================= Dựng track lồng tiếng =======================
def synthesize_track(segs, cfg, out_wav, log, progress=None, cancel=None):
    """Đọc từng câu, đặt theo mốc thời gian phụ đề; câu quá dài thì nén nhanh lên (tối đa 1.6x)."""
    eng = make_engine(cfg, log)
    sr = eng.sr
    pieces = []
    for i, s in enumerate(segs):
        if cancel and cancel():
            raise RuntimeError("Đã dừng.")
        if progress:
            progress((i + 1) / len(segs))
        if s.get("tr") is False or not s["text"].strip():
            continue  # câu chưa dịch được → không đọc
        slot = max(0.3, s["end"] - s["start"])
        try:
            x, sr = eng.synth(s["text"])
            if len(x) == 0:
                log(f"  Bỏ qua câu không đọc được: {s['text'][:40]}")
                continue
            dur = len(x) / sr
            if dur > slot * 1.05:
                x = stretch(x, sr, min(1.6, dur / slot))
        except Exception as e:  # noqa: BLE001
            log(f"  Lỗi đọc câu #{i + 1} ({type(e).__name__}: {e}) → bỏ qua: {s['text'][:40]}")
            continue
        pieces.append((int(s["start"] * sr), x))
    if not pieces:
        raise RuntimeError("Không có câu nào để lồng tiếng (kiểm tra engine giọng và bản dịch).")
    total = max(st + len(x) for st, x in pieces) + sr
    track = np.zeros(total, dtype=np.float32)
    for st, x in pieces:
        track[st:st + len(x)] += x
    track = np.clip(track, -1, 1)
    TEMP_DIR.mkdir(exist_ok=True)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((track * 32767).astype(np.int16).tobytes())
    log(f"Đã tạo track lồng tiếng ({len(pieces)} câu, {sr} Hz).")
