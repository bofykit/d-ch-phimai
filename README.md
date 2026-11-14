# Video Translator (Windows)
Nhập nhiều video → Groq Whisper (nếu chưa có .srt) → dịch có ngữ cảnh bằng Groq (nhiều key xoay vòng)
→ lồng tiếng offline Sherpa-ONNX → ghép phụ đề cỡ 14 → xóa metadata → Pitch & Tempo.

## Chạy thử
    pip install -r requirements.txt
    (đặt ffmpeg.exe cạnh main.py hoặc cài ffmpeg vào PATH)
    python main.py
Tab "Cài đặt" → "Tải model giọng" để tải giọng offline lần đầu.

## Build .exe trên GitHub
1. Push code lên repo (groq_keys.json đã nằm trong .gitignore).
2. Tab Actions → "Build Windows EXE" → Run workflow, hoặc: git tag v1.0 && git push --tags
3. Tải VideoTranslator-portable.zip / VideoTranslator-Setup.exe ở Artifacts (hoặc Releases nếu push tag).
