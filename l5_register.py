import asyncio
from typing import Callable
import core
from core import run_batch, log


def run_batch_register(count: int, headless: bool, password: str,
                       logcb: Callable[[str, str], None],
                       stop_flag: Callable[[], bool]):
    """GUIから呼ばれる同期ラッパー"""
    try:
        asyncio.run(run_batch(count, headless, password, logcb, stop_flag))
    except KeyboardInterrupt:
        log("中断されました。", logcb, "WARN")


def convert_accounts(format_: str, start_text: str, end_text: str,
                     out_path: str, logcb):
    # --- ここから置き換え ---
    def _to_int_or_none(s: str):
        if s is None:
            return None
        t = str(s).strip()
        # 全角→半角
        trans = str.maketrans("０１２３４５６７８９", "0123456789")
        t = t.translate(trans)
        return int(t) if t.isdigit() else None

    s = _to_int_or_none(start_text)   # 空欄→None
    e = _to_int_or_none(end_text)     # 空欄→None

    # core 側のルール実装に委譲（None は境界に展開される）
    accounts = core.convert_accounts_range(s, e)
    # --- 置き換えここまで ---

    if not accounts:
        log("[WARN] 該当するアカウントが見つかりません。", logcb, "WARN")
        return

    import os, csv
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    if format_.lower() == "txt":
        with open(out_path, "w", encoding="utf-8") as f:
            for a in accounts:
                f.write(f"{a.get('email','')},{a.get('password','')}\n")
    elif format_.lower() == "csv":
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["index", "email", "password", "activated", "login_ok", "datetime"])
            for a in accounts:
                writer.writerow([
                    a.get("index", ""),
                    a.get("email", ""),
                    a.get("password", ""),
                    a.get("activated", ""),
                    a.get("login_ok", ""),
                    a.get("datetime", "")
                ])
    else:
        log(f"[ERR] 未対応の形式です: {format_}", logcb, "ERR")
        return

    log(f"[OK] 変換完了: 件数={len(accounts)} 形式={format_} 出力={out_path}", logcb, "OK")
