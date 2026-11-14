"""Các lệnh FFmpeg: tách audio, đổi pitch/tempo, ghép phụ đề, xóa metadata."""
import subprocess
import sys
from pathlib import Path

from common import FFMPEG

_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def run(cmd: list[str], cwd=None) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", creationflags=_FLAGS)
    if p.returncode != 0:
        raise RuntimeError("FFmpeg lỗi:\n" + p.stderr[-1500:])
    return p.stderr


def has_audio(video) -> bool:
    p = subprocess.run([FFMPEG, "-i", str(video)], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", creationflags=_FLAGS)
    return "Audio:" in p.stderr


def extract_audio(video, out_mp3) -> None:
    run([FFMPEG, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
         "-b:a", "32k", str(out_mp3)])


def _atempo_chain(factor: float) -> list[str]:
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0"); factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5"); factor /= 0.5
    parts.append(f"atempo={factor:.5f}")
    return parts


def audio_tail(pitch_semitones: float, tempo: float, sr: int = 44100) -> str:
    """Pitch đổi độc lập với tốc độ: asetrate đổi cao độ, atempo bù lại độ dài."""
    parts = []
    if abs(pitch_semitones) > 1e-3:
        r = 2 ** (pitch_semitones / 12)
        parts += [f"asetrate={int(sr * r)}", f"aresample={sr}"] + _atempo_chain(1 / r)
    if abs(tempo - 1.0) > 1e-3:
        parts += _atempo_chain(tempo)
    return ",".join(parts)


def render(video, out_path, workdir: Path, *, dub_wav=None, srt=None, font_size=14,
           pitch=0.0, tempo=1.0, orig_vol=0.0, dub_vol=1.0, strip_meta=True) -> None:
    video = Path(video)
    inputs = ["-i", str(video)]
    if dub_wav:
        inputs += ["-i", str(dub_wav)]

    vf = []
    if srt:
        # copy srt vào workdir và dùng tên tương đối để tránh lỗi ký tự ':' '\' trên Windows
        vf.append(f"subtitles=sub.srt:force_style='FontSize={int(font_size)}'")
    if abs(tempo - 1.0) > 1e-3:
        vf.append(f"setpts=PTS/{tempo:.5f}")

    tail = audio_tail(pitch, tempo)
    af, fc = [], []
    audio_label = None
    orig_ok = has_audio(video)
    if dub_wav:
        if orig_ok and orig_vol > 0:
            fc.append(f"[0:a]volume={orig_vol}[o];[1:a]volume={dub_vol}[d];"
                      f"[o][d]amix=inputs=2:duration=first:normalize=0[m]")
        else:
            fc.append(f"[1:a]volume={dub_vol}[m]")
        fc.append(f"[m]{tail if tail else 'anull'}[a]")
        audio_label = "[a]"
    elif orig_ok and tail:
        fc.append(f"[0:a]{tail}[a]")
        audio_label = "[a]"

    cmd = [FFMPEG, "-y", *inputs]
    if vf:
        fc.append(f"[0:v]{','.join(vf)}[v]")
    if fc:
        cmd += ["-filter_complex", ";".join(fc)]
    cmd += ["-map", "[v]" if vf else "0:v"]
    if audio_label:
        cmd += ["-map", audio_label]
    elif orig_ok:
        cmd += ["-map", "0:a"]

    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"] if vf else ["-c:v", "copy"]
    if audio_label:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]
    if strip_meta:
        cmd += ["-map_metadata", "-1", "-map_chapters", "-1",
                "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1",
                "-metadata", "title=", "-fflags", "+bitexact",
                "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
    cmd += [str(out_path)]
    run(cmd, cwd=str(workdir))
