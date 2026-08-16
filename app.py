import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import *
from l5_register import run_batch_register, convert_accounts

CONFIG = "config.json"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

THEMES = {
    "ライト": "flatly",
    "ダーク": "darkly",
    "濃紺": "superhero",
    "オーシャンブルー": "cyborg",
}

class App(tb.Window):
    def __init__(self):
        super().__init__(themename=THEMES.get("ライト", "flatly"))
        self.title("LEVEL5 ID AutoRegister (GUI) V14.10")
        self.geometry("920x660")
        self.minsize(900, 640)

        # 状態
        self.var_count = tk.StringVar(value="3")
        self.var_headless = tk.BooleanVar(value=True)
        self.var_theme = tk.StringVar(value="ライト")
        self.var_pass = tk.StringVar(value="Aa123456")
        self.var_range_from = tk.StringVar(value="")
        self.var_range_to = tk.StringVar(value="")
        self.var_format = tk.StringVar(value="txt")
        self._stop = False
        self.worker: threading.Thread | None = None

        self._style = tb.Style()
        self._build_ui()
        self._load_config()
        self._apply_theme()

    # ---------- UI ----------
    def _build_ui(self):
        # ヘッダー
        top = tb.Frame(self, padding=10)
        top.pack(fill=X, side=TOP)

        title = tb.Label(top, text="LEVEL5 ID AutoRegister (GUI) V14.10", font=("Segoe UI", 16, "bold"))
        title.pack(side=LEFT)

        owner = tb.Label(top, text="hpcpr451（ヨコイ）", font=("Segoe UI", 13, "bold"))
        owner.pack(side=RIGHT)
        
        title2 = tb.Label(top, text="LEVEL5ID垢いっぱい", font=("Segoe UI", 10))
        title2.pack(side=RIGHT, padx=50)

        # 設定ブロック
        frm = tb.Labelframe(self, text="設定", padding=10)
        frm.pack(fill=X, padx=12, pady=(0,8))

        # 登録数
        tb.Label(frm, text="登録数").grid(row=0, column=0, sticky=W, padx=6, pady=6)
        ent_count = tb.Entry(frm, textvariable=self.var_count, width=10)
        ent_count.grid(row=0, column=1, sticky=W, padx=6, pady=6)

        # 実行モード（ラジオ ○）
        tb.Label(frm, text="実行モード（ヘッドレス）").grid(row=0, column=2, sticky=W, padx=6, pady=6)

        rb_on = tb.Radiobutton(frm, text="有効（ブラウザ非表示）", variable=self.var_headless, value=True, bootstyle="success")
        rb_off = tb.Radiobutton(frm, text="無効（ブラウザ表示）", variable=self.var_headless, value=False)
        rb_on.grid(row=0, column=3, sticky=W, padx=(6,2), pady=6)
        rb_off.grid(row=0, column=4, sticky=W, padx=(2,6), pady=6)

        # テーマ
        tb.Label(frm, text="テーマ").grid(row=1, column=0, sticky=W, padx=6, pady=6)
        cbo = tb.Combobox(frm, values=list(THEMES.keys()), textvariable=self.var_theme, width=18, state="readonly")
        cbo.grid(row=1, column=1, sticky=W, padx=6, pady=6)
        cbo.bind("<<ComboboxSelected>>", lambda e: self._apply_theme())

        # パスワード（可視）
        tb.Label(frm, text="パスワード").grid(row=1, column=2, sticky=W, padx=6, pady=6)
        ent_pw = tb.Entry(frm, textvariable=self.var_pass, width=22)
        ent_pw.grid(row=1, column=3, sticky=W, padx=6, pady=6, columnspan=2)

        # 注意書き
        note = ("【パスワード仕様】6〜32文字、半角英数字のみ（a〜z/A〜Z/0〜9）。\n"
                "アルファベットは大文字/小文字を区別します。")
        tb.Label(frm, text=note, bootstyle="info").grid(row=1, column=4, columnspan=5, sticky=W, padx=30, pady=(6,0))

        # 実行/停止/設定保存
        btns = tb.Frame(self)
        btns.pack(fill=X, padx=12)
        tb.Button(btns, text="▶ 実行", bootstyle="success", command=self.start).pack(side=LEFT, padx=4, pady=6)
        tb.Button(btns, text="■ 停止", bootstyle="danger", command=self.stop).pack(side=LEFT, padx=4, pady=6)
        tb.Button(btns, text="設定保存", command=self._save_config).pack(side=LEFT, padx=4, pady=6)

        # 変換ブロック
        cv = tb.Labelframe(self, text="TXT/CSV 変換（成功のみ・連番範囲）", padding=10)
        cv.pack(fill=X, padx=12, pady=(0,8))
        tb.Label(cv, text="範囲（連番）").grid(row=0, column=0, sticky=W, padx=6, pady=6)
        ent_from = tb.Entry(cv, textvariable=self.var_range_from, width=10)
        ent_to = tb.Entry(cv, textvariable=self.var_range_to, width=10)
        tb.Label(cv, text="〜").grid(row=0, column=2, sticky=W, padx=(0,6), pady=6)
        ent_from.grid(row=0, column=1, sticky=W, padx=(6,2), pady=6)
        ent_to.grid(row=0, column=3, sticky=W, padx=(2,6), pady=6)

        fmt = tb.Radiobutton(cv, text="TXT", variable=self.var_format, value="txt", bootstyle="info")
        fmc = tb.Radiobutton(cv, text="CSV", variable=self.var_format, value="csv")
        fmt.grid(row=0, column=4, sticky=W, padx=6, pady=6)
        fmc.grid(row=0, column=5, sticky=W, padx=6, pady=6)
        tb.Button(cv, text="変換して保存...", command=self.convert).grid(row=0, column=6, sticky=W, padx=6, pady=6)
        
        # 例
        example = ("例：5～10／省略～10／5～省略／省略～省略\n"
                "（どちらも省略した場合は作成済みのすべてを変換します）")
        tb.Label(cv, text=example, bootstyle="info").grid(row=0, column=12, columnspan=5, sticky=W, padx=25, pady=(6,0))

        # 凡例（固定）
        legend = tb.Frame(self)
        legend.pack(fill=X, padx=12)
        tb.Label(legend, text="🟢 成功", bootstyle="success").pack(side=LEFT, padx=(4,12))
        tb.Label(legend, text="🔴 エラー", bootstyle="danger").pack(side=LEFT, padx=12)
        tb.Label(legend, text="🟡 進行中", bootstyle="warning").pack(side=LEFT, padx=12)

        # ログ
        lf = tb.Labelframe(self, text="実行ログ（リアルタイム）", padding=6)
        lf.pack(fill=BOTH, expand=YES, padx=12, pady=8)

        self.txt = tk.Text(lf, wrap="none", height=18, padx=6, pady=6)
        self.txt.pack(side=LEFT, fill=BOTH, expand=YES)
        # 色タグ
        self.txt.tag_config("OK", foreground="#22c55e")
        self.txt.tag_config("ERR", foreground="#ef4444")
        self.txt.tag_config("RUN", foreground="#eab308")
        self.txt.tag_config("INFO", foreground="#eab308")
        self.txt.tag_config("WARN", foreground="#eab308")

        # スクロールバー（常時表示・ホイール対応）
        sb = tb.Scrollbar(lf, orient="vertical", command=self.txt.yview)
        sb.pack(side=RIGHT, fill=Y)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.bind("<MouseWheel>", lambda e: self.txt.yview_scroll(int(-1*(e.delta/120)), "units"))
        # Linux の場合
        self.txt.bind("<Button-4>", lambda e: self.txt.yview_scroll(-1, "units"))
        self.txt.bind("<Button-5>", lambda e: self.txt.yview_scroll(1, "units"))

        # 終了時自動保存
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _apply_theme(self):
        theme = THEMES.get(self.var_theme.get(), "flatly")
        try:
            self._style.theme_use(theme)
        except Exception:
            self._style.theme_use("flatly")

    # ---------- ログ出力 ----------
    def log(self, line: str, level: str = "INFO"):
        tag = level if level in ("OK", "ERR", "RUN", "INFO", "WARN") else "INFO"
        self.txt.insert("end", line + "\n", tag)
        self.txt.see("end")

    # ---------- 動作 ----------
    def start(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("実行中", "すでに実行中です。")
            return
        try:
            count = int(self.var_count.get())
            if count <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror("入力エラー", "登録数は正の整数を入力してください。")
            return

        pwd = self.var_pass.get().strip()
        if not (6 <= len(pwd) <= 32) or (not pwd.isalnum()):
            messagebox.showerror("パスワード", "6〜32文字・半角英数字のみ（a〜z/A〜Z/0〜9）で入力してください。")
            return

        self._stop = False
        headless = bool(self.var_headless.get())
        # バックグラウンド実行
        self.worker = threading.Thread(
            target=run_batch_register,
            args=(count, headless, pwd, self.log, lambda: self._stop),
            daemon=True
        )
        self.worker.start()

    def stop(self):
        self._stop = True
        self.log("停止要求を出しました。", "WARN")

    def convert(self):
        fmt = self.var_format.get().lower()
        ext = "txt" if fmt == "txt" else "csv"
        path = filedialog.asksaveasfilename(
            title="出力ファイルを選択",
            defaultextension=f".{ext}",
            filetypes=[(ext.upper(), f"*.{ext}"), ("すべて", "*.*")]
        )
        if not path:
            return
        try:
            convert_accounts(fmt, self.var_range_from.get(), self.var_range_to.get(), path, self.log)
        except Exception as e:
            messagebox.showerror("変換エラー", str(e))

    # ---------- 設定 ----------
    def _load_config(self):
        if not os.path.exists(CONFIG):
            return
        try:
            with open(CONFIG, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.var_count.set(cfg.get("count", "3"))
            self.var_headless.set(bool(cfg.get("headless", True)))
            self.var_theme.set(cfg.get("theme", "ライト"))
            self.var_pass.set(cfg.get("password", "Aa123456"))
            self.var_range_from.set(cfg.get("range_from", ""))
            self.var_range_to.set(cfg.get("range_to", ""))
            self.var_format.set(cfg.get("format", "txt"))
        except Exception:
            pass

    def _save_config(self):
        cfg = {
            "count": self.var_count.get(),
            "headless": bool(self.var_headless.get()),
            "theme": self.var_theme.get(),
            "password": self.var_pass.get(),
            "range_from": self.var_range_from.get(),
            "range_to": self.var_range_to.get(),
            "format": self.var_format.get(),
        }
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        self.log("[OK] 設定を保存しました。", "OK")

    def on_close(self):
        try:
            self._save_config()
        finally:
            self.destroy()

if __name__ == "__main__":
    App().mainloop()
