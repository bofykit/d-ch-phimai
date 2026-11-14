"""Xoay vòng nhiều Groq API key, test key, tìm model chạy được."""
import threading
import time

from groq import Groq

SKIP_WORDS = ("whisper", "tts", "guard", "orpheus", "playai", "embed", "distil-whisper")


class KeyRotator:
    """Dùng key lần lượt theo thứ tự 1→2→3→1…; lỗi (429/hết quota/sai key) thì nhảy key kế tiếp."""

    def __init__(self, keys: list[str]):
        self.keys = [k.strip() for k in keys if k.strip()]
        self._i = 0
        self._lock = threading.Lock()

    def _next(self) -> str:
        with self._lock:
            k = self.keys[self._i % len(self.keys)]
            self._i += 1
            return k

    def call(self, fn, log=None):
        if not self.keys:
            raise RuntimeError("Chưa có Groq API key nào.")
        last = None
        for round_ in range(2):
            for _ in range(len(self.keys)):
                key = self._next()
                try:
                    return fn(Groq(api_key=key))
                except Exception as e:  # noqa: BLE001
                    last = e
                    if log:
                        log(f"  key …{key[-4:]} lỗi: {str(e)[:120]} → thử key kế tiếp")
            if round_ == 0:
                time.sleep(5)
        raise RuntimeError(f"Tất cả key đều lỗi: {last}")


def test_key(key: str) -> tuple[bool, str]:
    try:
        n = len(Groq(api_key=key.strip()).models.list().data)
        return True, f"OK ({n} model)"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:150]


def list_chat_models(key: str) -> list[str]:
    ids = [m.id for m in Groq(api_key=key).models.list().data]
    return sorted(i for i in ids if not any(w in i.lower() for w in SKIP_WORDS))


def find_working_models(rotator: KeyRotator, log, progress=None) -> list[str]:
    """Gọi thử từng model chat với 1 câu ngắn; model nào trả lời được thì giữ lại."""
    models = rotator.call(lambda c: sorted(
        m.id for m in c.models.list().data if not any(w in m.id.lower() for w in SKIP_WORDS)))
    working = []
    for i, m in enumerate(models, 1):
        try:
            rotator.call(lambda c: c.chat.completions.create(
                model=m, max_tokens=5, messages=[{"role": "user", "content": "Say OK"}]))
            working.append(m)
            log(f"✔ {m}")
        except Exception as e:  # noqa: BLE001
            log(f"✘ {m}: {str(e)[:80]}")
        if progress:
            progress(i / len(models))
    return working
