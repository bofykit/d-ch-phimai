"""Lấy phụ đề gốc: dùng file .srt cùng tên nếu có, nếu không thì nhận dạng giọng nói bằng Groq Whisper."""
from pathlib import Path

from common import TEMP_DIR, parse_srt
from ffmpeg_utils import extract_audio


def get_source_segments(video, rot, whisper_model, src_lang, log):
    video = Path(video)
    srt = video.with_suffix(".srt")
    if srt.exists():
        log(f"Dùng phụ đề có sẵn: {srt.name}")
        return parse_srt(srt)

    log("Không có .srt → nhận dạng giọng nói bằng Groq Whisper…")
    TEMP_DIR.mkdir(exist_ok=True)
    mp3 = TEMP_DIR / (video.stem + "_16k.mp3")
    extract_audio(video, mp3)
    if mp3.stat().st_size > 24 * 1024 * 1024:
        raise RuntimeError("Audio > 25MB (giới hạn Groq). Hãy cắt video ngắn hơn hoặc cung cấp file .srt.")

    def fn(c):
        with open(mp3, "rb") as f:
            kw = dict(file=(mp3.name, f.read()), model=whisper_model,
                      response_format="verbose_json", timestamp_granularities=["segment"])
            if src_lang and src_lang != "auto":
                kw["language"] = src_lang
            return c.audio.transcriptions.create(**kw)

    resp = rot.call(fn, log)
    segs = []
    for s in resp.segments:
        g = (lambda k: s[k]) if isinstance(s, dict) else (lambda k: getattr(s, k))
        txt = g("text").strip()
        if txt:
            segs.append({"start": float(g("start")), "end": float(g("end")), "text": txt})
    mp3.unlink(missing_ok=True)
    return segs
