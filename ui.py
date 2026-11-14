"""Giao diện CustomTkinter: tab Video / Groq API / Model / Cài đặt."""
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from common import APP, load_config, load_keys, save_config, save_keys
from groq_client import KeyRotator, find_working_models, test_key
from pipeline import process_video
from tts import download_model, make_engine


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Video Translator – Groq + Sherpa-ONNX")
        self.geometry("980x720")
        self.cfg = load_config()
        self.files: list[str] = []
        self._cancel = False

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        for t in ("Video", "Groq API", "Model", "Cài đặt"):
            self.tabs.add(t)
        self._tab_video(); self._tab_keys(); self._tab_models(); self._tab_settings()

        self.bar = ctk.CTkProgressBar(self); self.bar.set(0)
        self.bar.pack(fill="x", padx=10)
        self.logbox = ctk.CTkTextbox(self, height=170)
        self.logbox.pack(fill="x", padx=10, pady=8)

    # ---------- tiện ích ----------
    def log(self, msg):
        self.after(0, lambda: (self.logbox.insert("end", msg + "\n"), self.logbox.see("end")))

    def prog(self, v):
        self.after(0, lambda: self.bar.set(v))

    def slider(self, parent, label, key, lo, hi, steps, fmt="{:.2f}"):
        row = ctk.CTkFrame(parent); row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=label, width=230, anchor="w").pack(side="left")
        val = ctk.CTkLabel(row, text=fmt.format(self.cfg[key]), width=60)

        def on(v):
            self.cfg[key] = round(float(v), 3) if steps > 50 or key != "font_size" else int(v)
            val.configure(text=fmt.format(self.cfg[key]))
        s = ctk.CTkSlider(row, from_=lo, to=hi, number_of_steps=steps, command=on)
        s.set(self.cfg[key]); s.pack(side="left", fill="x", expand=True, padx=8)
        val.pack(side="left")

    # ---------- tab Video ----------
    def _tab_video(self):
        t = self.tabs.tab("Video")
        top = ctk.CTkFrame(t); top.pack(fill="x")
        for text, cmd in (("＋ Thêm video", self.add_files), ("Xóa mục chọn", self.remove_sel),
                          ("Xóa hết", self.clear_files)):
            ctk.CTkButton(top, text=text, command=cmd, width=130).pack(side="left", padx=4, pady=4)
        self.btn_start = ctk.CTkButton(top, text="▶ Bắt đầu", command=self.start, fg_color="#2e8b57")
        self.btn_start.pack(side="right", padx=4)
        ctk.CTkButton(top, text="■ Dừng", command=lambda: setattr(self, "_cancel", True),
                      fg_color="#b22222", width=80).pack(side="right", padx=4)
        self.lb = tk.Listbox(t, selectmode="extended", bg="#1f1f1f", fg="white", height=14,
                             selectbackground="#1f6aa5", borderwidth=0)
        self.lb.pack(fill="both", expand=True, pady=6)
        ctk.CTkLabel(t, text="Mẹo: đặt file .srt cùng tên cạnh video để bỏ qua bước nhận dạng giọng nói.",
                     text_color="gray").pack(anchor="w")

    def add_files(self):
        for f in filedialog.askopenfilenames(filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
                                                        ("Tất cả", "*.*")]):
            if f not in self.files:
                self.files.append(f); self.lb.insert("end", f)

    def remove_sel(self):
        for i in reversed(self.lb.curselection()):
            self.lb.delete(i); del self.files[i]

    def clear_files(self):
        self.lb.delete(0, "end"); self.files.clear()

    # ---------- tab Groq API ----------
    def _tab_keys(self):
        t = self.tabs.tab("Groq API")
        ctk.CTkLabel(t, text="Mỗi dòng 1 API key – app dùng lần lượt theo thứ tự (xoay vòng). "
                             "Lưu trong groq_keys.json (không push lên GitHub).",
                     wraplength=900, anchor="w", justify="left").pack(fill="x")
        self.keybox = ctk.CTkTextbox(t, height=180); self.keybox.pack(fill="x", pady=6)
        self.keybox.insert("1.0", "\n".join(load_keys()))
        row = ctk.CTkFrame(t); row.pack(fill="x")
        ctk.CTkButton(row, text="Lưu key", command=self.save_keys_ui).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Test tất cả key", command=self.test_keys).pack(side="left", padx=4)
        self.keyres = ctk.CTkTextbox(t, height=200); self.keyres.pack(fill="both", expand=True, pady=6)

    def _keys(self):
        return [k.strip() for k in self.keybox.get("1.0", "end").splitlines() if k.strip()]

    def save_keys_ui(self):
        save_keys(self._keys()); self.log(f"Đã lưu {len(self._keys())} key.")

    def test_keys(self):
        keys = self._keys(); self.keyres.delete("1.0", "end")

        def work():
            for i, k in enumerate(keys, 1):
                ok, msg = test_key(k)
                line = f"Key {i} (…{k[-4:]}): {'✔' if ok else '✘'} {msg}\n"
                self.after(0, lambda l=line: self.keyres.insert("end", l))
        threading.Thread(target=work, daemon=True).start()

    # ---------- tab Model ----------
    def _tab_models(self):
        t = self.tabs.tab("Model")
        row = ctk.CTkFrame(t); row.pack(fill="x")
        ctk.CTkButton(row, text="🔍 Tìm model chạy được", command=self.find_models).pack(side="left", padx=4)
        ctk.CTkLabel(row, text="Model dịch:").pack(side="left", padx=(20, 4))
        self.model_menu = ctk.CTkOptionMenu(row, values=[self.cfg["model"]], width=320,
                                            command=lambda v: self.cfg.__setitem__("model", v))
        self.model_menu.set(self.cfg["model"]); self.model_menu.pack(side="left")
        row2 = ctk.CTkFrame(t); row2.pack(fill="x", pady=6)
        ctk.CTkLabel(row2, text="Model nhận dạng giọng nói:").pack(side="left", padx=4)
        self.whisper_entry = ctk.CTkEntry(row2, width=280)
        self.whisper_entry.insert(0, self.cfg["whisper_model"]); self.whisper_entry.pack(side="left")
        self.modelbox = ctk.CTkTextbox(t); self.modelbox.pack(fill="both", expand=True, pady=6)

    def find_models(self):
        self.save_keys_ui(); self.modelbox.delete("1.0", "end")
        rot = KeyRotator(self._keys())

        def work():
            try:
                ok = find_working_models(
                    rot, lambda m: self.after(0, lambda: self.modelbox.insert("end", m + "\n")), self.prog)
                if ok:
                    self.after(0, lambda: (self.model_menu.configure(values=ok),
                                           self.model_menu.set(self.cfg["model"] if self.cfg["model"] in ok else ok[0]),
                                           self.cfg.__setitem__("model", self.model_menu.get())))
            except Exception as e:  # noqa: BLE001
                self.log(f"Lỗi: {e}")
        threading.Thread(target=work, daemon=True).start()

    # ---------- tab Cài đặt ----------
    def _tab_settings(self):
        t = self.tabs.tab("Cài đặt")
        self.slider(t, "Cỡ chữ phụ đề", "font_size", 8, 40, 32, "{:.0f}")
        self.slider(t, "Cao độ (bán cung, Pitch)", "pitch", -12, 12, 48, "{:+.1f}")
        self.slider(t, "Tốc độ (Tempo)", "tempo", 0.5, 2.0, 30, "{:.2f}x")
        self.slider(t, "Âm lượng tiếng gốc (0 = tắt)", "orig_vol", 0, 1, 20)
        self.slider(t, "Âm lượng lồng tiếng", "dub_vol", 0, 2, 20)
        self.vars = {}
        for key, label in (("do_dub", "Lồng tiếng offline (Sherpa-ONNX)"),
                           ("do_burn", "Ghép phụ đề đã dịch vào video"),
                           ("strip_meta", "Xóa metadata")):
            v = tk.BooleanVar(value=self.cfg[key]); self.vars[key] = v
            ctk.CTkCheckBox(t, text=label, variable=v,
                            command=lambda k=key: self.cfg.__setitem__(k, self.vars[k].get())).pack(anchor="w", pady=2)
        row = ctk.CTkFrame(t); row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Ngôn ngữ đích:").pack(side="left", padx=4)
        self.tl = ctk.CTkEntry(row, width=150); self.tl.insert(0, self.cfg["target_lang"]); self.tl.pack(side="left")
        ctk.CTkLabel(row, text="Ngôn ngữ gốc (mã, vd en/zh/ja hoặc auto):").pack(side="left", padx=(16, 4))
        self.sl = ctk.CTkEntry(row, width=80); self.sl.insert(0, self.cfg["src_lang"]); self.sl.pack(side="left")
        row = ctk.CTkFrame(t); row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Engine giọng:").pack(side="left", padx=4)
        self.eng_menu = ctk.CTkOptionMenu(row, values=["vieneu", "sherpa"], width=110,
                                          command=lambda v: self.cfg.__setitem__("tts_engine", v))
        self.eng_menu.set(self.cfg["tts_engine"]); self.eng_menu.pack(side="left")
        ctk.CTkLabel(row, text="Giọng VieNeu:").pack(side="left", padx=(16, 4))
        self.vv = ctk.CTkEntry(row, width=150); self.vv.insert(0, self.cfg["vieneu_voice"]); self.vv.pack(side="left")
        self.prec = ctk.CTkOptionMenu(row, values=["fp32", "int8"], width=80,
                                      command=lambda v: self.cfg.__setitem__("vieneu_precision", v))
        self.prec.set(self.cfg["vieneu_precision"]); self.prec.pack(side="left", padx=8)
        ctk.CTkButton(row, text="Xem danh sách giọng", width=150, command=self.list_voices).pack(side="left")
        row = ctk.CTkFrame(t); row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="(Sherpa) model giọng, thư mục trong models/tts:").pack(side="left", padx=4)
        self.ttsm = ctk.CTkEntry(row, width=300); self.ttsm.insert(0, self.cfg["tts_model"]); self.ttsm.pack(side="left")
        ctk.CTkButton(row, text="Tải model giọng", command=self.dl_tts, width=130).pack(side="left", padx=8)
        row = ctk.CTkFrame(t); row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Thư mục xuất:").pack(side="left", padx=4)
        self.out = ctk.CTkEntry(row, width=420); self.out.insert(0, self.cfg["out_dir"]); self.out.pack(side="left")
        ctk.CTkButton(row, text="Chọn…", width=70,
                      command=lambda: self._pick_dir()).pack(side="left", padx=6)

    def _pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.out.delete(0, "end"); self.out.insert(0, d)

    def list_voices(self):
        def work():
            try:
                eng = make_engine({**self.cfg, "tts_engine": "vieneu", "vieneu_precision": self.prec.get()}, self.log)
                self.log("Các giọng có sẵn: " + ", ".join(str(l) for l, _ in eng.list_voices()))
            except Exception as e:  # noqa: BLE001
                self.log(f"Lỗi: {e}")
        threading.Thread(target=work, daemon=True).start()

    def dl_tts(self):
        name = self.ttsm.get().strip()
        threading.Thread(target=lambda: self._safe(lambda: download_model(name, self.log)), daemon=True).start()

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self.log(f"Lỗi: {e}")

    # ---------- chạy ----------
    def _collect(self):
        self.cfg.update(target_lang=self.tl.get().strip(), src_lang=self.sl.get().strip() or "auto",
                        tts_model=self.ttsm.get().strip(), vieneu_voice=self.vv.get().strip(), out_dir=self.out.get().strip(),
                        whisper_model=self.whisper_entry.get().strip())
        save_config(self.cfg); save_keys(self._keys())

    def start(self):
        if not self.files:
            return messagebox.showinfo("Thiếu video", "Hãy thêm ít nhất 1 video.")
        if not self._keys():
            return messagebox.showinfo("Thiếu key", "Hãy nhập Groq API key ở tab Groq API.")
        self._collect(); self._cancel = False
        self.btn_start.configure(state="disabled")
        rot = KeyRotator(self._keys()); files = list(self.files); cfg = dict(self.cfg)

        def work():
            for n, f in enumerate(files, 1):
                if self._cancel:
                    break
                self.log(f"\n=== [{n}/{len(files)}] {f}")
                try:
                    process_video(f, cfg, rot, self.log, self.prog, lambda: self._cancel)
                except Exception as e:  # noqa: BLE001
                    tb = traceback.format_exc()
                    self.log(f"✘ Lỗi: {e}\n{tb}")
                    try:
                        (APP / "error.log").write_text(tb, encoding="utf-8")
                    except OSError:
                        pass
            self.log("\nHoàn tất."); self.after(0, lambda: self.btn_start.configure(state="normal"))
        threading.Thread(target=work, daemon=True).start()
