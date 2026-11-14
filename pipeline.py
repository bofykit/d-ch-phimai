"""Xử lý 1 video từ đầu đến cuối."""
import shutil
from pathlib import Path

from common import TEMP_DIR, write_srt
from ffmpeg_utils import render
from transcribe import get_source_segments
from translate import analyze_context, translate_segments
from tts import synthesize_track


def process_video(video, cfg, rot, log, progress=None, cancel=None):
    video = Path(video)
    out_dir = Path(cfg["out_dir"]); out_dir.mkdir(parents=True, exist_ok=True)
    work = TEMP_DIR / video.stem; work.mkdir(parents=True, exist_ok=True)
    P = progress or (lambda x: None)

    segs = get_source_segments(video, rot, cfg["whisper_model"], cfg["src_lang"], log)
    if not segs:
        raise RuntimeError("Không lấy được phụ đề/lời thoại.")
    P(0.15)
    ctx = analyze_context(rot, cfg["model"], segs, cfg["target_lang"], log)
    P(0.25)
    tr = translate_segments(rot, cfg["model"], segs, cfg["target_lang"], ctx, log,
                            lambda x: P(0.25 + 0.3 * x), cancel)
    srt_out = out_dir / f"{video.stem}.{cfg['target_lang'][:12].replace(' ', '_')}.srt"
    write_srt(tr, srt_out)
    shutil.copy(srt_out, work / "sub.srt")

    dub = None
    if cfg["do_dub"]:
        dub = work / "dub.wav"
        synthesize_track(tr, cfg["tts_model"], int(cfg["tts_sid"]), dub, log,
                         lambda x: P(0.55 + 0.25 * x), cancel)
    log("Đang xuất video (phụ đề, pitch/tempo, xóa metadata)…")
    out = out_dir / f"{video.stem}_dich.mp4"
    render(video, out, work, dub_wav=dub, srt=(work / "sub.srt") if cfg["do_burn"] else None,
           font_size=cfg["font_size"], pitch=cfg["pitch"], tempo=cfg["tempo"],
           orig_vol=cfg["orig_vol"], dub_vol=cfg["dub_vol"], strip_meta=cfg["strip_meta"])
    shutil.rmtree(work, ignore_errors=True)
    P(1.0)
    log(f"✔ Xong: {out}")
    return out
