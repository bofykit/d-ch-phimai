"""Dịch có ngữ cảnh: đọc toàn bộ phụ đề → tóm tắt cốt truyện, danh sách nhân vật + xưng hô → dùng khi dịch."""
import json

from groq_client import KeyRotator

BATCH = 30
MAX_CONTEXT_CHARS = 28000


def _chat_json(rot: KeyRotator, model: str, system: str, user: str, log) -> dict:
    def fn(c):
        r = c.chat.completions.create(
            model=model, temperature=0.2,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return json.loads(r.choices[0].message.content)
    return rot.call(fn, log)


def analyze_context(rot, model, segs, target_lang, log) -> str:
    text = "\n".join(s["text"] for s in segs)
    if len(text) > MAX_CONTEXT_CHARS:  # phụ đề quá dài: lấy mẫu đều toàn bộ phim
        step = len(text) // MAX_CONTEXT_CHARS + 1
        text = "\n".join(s["text"] for s in segs[::step])
    system = ("You are a professional subtitle translator and story analyst. "
              "Reply ONLY with a JSON object.")
    user = (f"Read this whole subtitle transcript. Target language: {target_lang}.\n"
            'Return JSON: {"summary": "plot summary (<=200 words)", '
            '"characters": [{"name": "...", "translated_name": "...", "gender": "...", "role": "..."}], '
            '"address_terms": [{"speaker": "...", "listener": "...", "speaker_calls_self": "...", '
            '"calls_listener": "..."}], "style": "tone/register notes"}\n\n'
            f"TRANSCRIPT:\n{text}")
    log("Đang đọc toàn bộ phụ đề để tóm tắt cốt truyện, nhân vật, xưng hô…")
    data = _chat_json(rot, model, system, user, log)
    ctx = json.dumps(data, ensure_ascii=False, indent=1)
    log("Ngữ cảnh đã lập:\n" + ctx[:1200] + ("…" if len(ctx) > 1200 else ""))
    return ctx


def translate_segments(rot, model, segs, target_lang, context, log, progress=None, cancel=None):
    system = ("You are a professional subtitle translator. Use the CONTEXT for consistent names and "
              "forms of address. Keep each line short and natural for subtitles. "
              'Reply ONLY JSON: {"items":[{"id":int,"text":"translation"}]} with the same ids.\n\n'
              f"CONTEXT:\n{context}")
    out = []
    for b in range(0, len(segs), BATCH):
        if cancel and cancel():
            raise RuntimeError("Đã dừng.")
        chunk = segs[b:b + BATCH]
        prev = " | ".join(s["text"] for s in segs[max(0, b - 3):b])
        user = (f"Translate to {target_lang}. Previous lines (context only): {prev}\n"
                + json.dumps([{"id": i, "text": s["text"]} for i, s in enumerate(chunk)],
                             ensure_ascii=False))
        mapping = {}
        try:
            data = _chat_json(rot, model, system, user, log)
            mapping = {int(x["id"]): str(x["text"]) for x in data.get("items", [])}
        except Exception as e:  # noqa: BLE001
            log(f"Lô {b // BATCH + 1} lỗi ({e}); giữ nguyên bản.")
        for i, s in enumerate(chunk):
            out.append({**s, "text": mapping.get(i, s["text"])})
        if progress:
            progress(min(1.0, (b + BATCH) / len(segs)))
    return out
