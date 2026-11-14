"""Dịch có ngữ cảnh: đọc toàn bộ phụ đề → tóm tắt cốt truyện, danh sách nhân vật + xưng hô → dùng khi dịch."""
import json

from groq_client import KeyRotator

BATCH = 30
MAX_CONTEXT_CHARS = 28000


def _chat_json(rot: KeyRotator, model: str, system: str, user: str, log) -> dict:
    def fn(c):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            r = c.chat.completions.create(model=model, temperature=0.2, messages=msgs,
                                          response_format={"type": "json_object"})
        except Exception as e:  # noqa: BLE001
            if "response_format" not in str(e) and "json" not in str(e).lower():
                raise
            r = c.chat.completions.create(model=model, temperature=0.2, messages=msgs)
        txt = (r.choices[0].message.content or "").strip()
        try:
            return json.loads(txt)
        except ValueError:
            a, b = txt.find("{"), txt.rfind("}")
            return json.loads(txt[a:b + 1])
    return rot.call(fn, log)


def _items(data, n) -> dict:
    """Chấp nhận nhiều dạng trả lời: dict{"items":[...]}, list[{id,text}], hoặc list[str] đủ n dòng."""
    if isinstance(data, dict):
        data = (data.get("items") or data.get("translations")
                or next((v for v in data.values() if isinstance(v, list)), []))
    out = {}
    if isinstance(data, list):
        if data and all(isinstance(x, str) for x in data) and len(data) == n:
            return {i: x for i, x in enumerate(data)}
        for x in data:
            if isinstance(x, dict) and "id" in x and "text" in x:
                try:
                    out[int(x["id"])] = str(x["text"])
                except (TypeError, ValueError):
                    pass
    return out


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
            '"calls_listener": "..."}], "style": "tone/register notes"}\n'
            "Write summary/style/notes in English; only translated_name and the address terms "
            f"must be in {target_lang}.\n\n"
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
        for attempt in range(2):
            try:
                mapping = _items(_chat_json(rot, model, system, user, log), len(chunk))
            except Exception as e:  # noqa: BLE001
                log(f"Lô {b // BATCH + 1} lỗi ({e})")
            if len(mapping) >= len(chunk) * 0.8:
                break
            log(f"Lô {b // BATCH + 1}: thiếu dòng, thử lại…")
        for i, s in enumerate(chunk):
            out.append({**s, "text": mapping.get(i, s["text"]), "tr": i in mapping})
        if progress:
            progress(min(1.0, (b + BATCH) / len(segs)))
    return out
