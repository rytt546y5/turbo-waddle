import asyncio
import json
import os
import re
import time
import traceback
import random
import string
import aiohttp
from playwright.async_api import async_playwright
from selectors import SELECTORS

OUTPUT_DIR = "output"
ACCOUNTS_JSON = os.path.join(OUTPUT_DIR, "accounts.json")
LOG_FILE = os.path.join(OUTPUT_DIR, "log.txt")

# =====================================================================
# ログ関連
# =====================================================================

LEVEL_TAGS = ("OK", "ERR", "RUN", "INFO", "WARN")

def log(message: str, cb=None, level: str = "INFO"):
    """GUIおよびファイル両方にログ出力。"""
    level = (level or "INFO").upper()
    m = re.match(r"\s*\[([A-Za-z]+)\]", message)
    if m and m.group(1).upper() in LEVEL_TAGS:
        level = m.group(1).upper()

    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} {message}"

    print(line)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    if cb:
        try:
            cb(line, level)
        except TypeError:
            cb(line)


def log_exception(msg: str, e: Exception, cb=None):
    """例外を詳細トレース込みでERR出力"""
    log(f"[ERR] {msg}: {type(e).__name__}: {e}", cb, "ERR")
    for line in traceback.format_exc().splitlines():
        log(f"    {line}", cb, "ERR")


# =====================================================================
# 基本設定
# =====================================================================

def ensure_output():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(ACCOUNTS_JSON):
        with open(ACCOUNTS_JSON, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def load_accounts():
    ensure_output()
    try:
        with open(ACCOUNTS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_accounts(accounts):
    ensure_output()
    with open(ACCOUNTS_JSON, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def get_next_index(accounts):
    indices = [a.get("index", 0) for a in accounts if isinstance(a.get("index", 0), int)]
    return (max(indices) + 1) if indices else 1


# =====================================================================
# メール関連
# =====================================================================

MAILTM_BASE = "https://api.mail.tm"
# もともとの固定ドメインは残す（ここは変えない）
FIXED_DOMAIN = "virgilian.com"
MAIL_WAIT_SECONDS = 90
MAIL_RETRY_TIMES = 3


async def _fetch_random_domain(session: aiohttp.ClientSession, cb):
    """
    422で「そのドメイン無効」と言われた時だけ呼ぶフォールバック。
    /domains から取れたものの中でランダムに1つ返す。
    失敗したら None を返す（その場合は元のエラーを投げる）。
    """
    try:
        async with session.get(f"{MAILTM_BASE}/domains", timeout=10) as r:
            data = await r.json()
        domains = [d["domain"] for d in data.get("hydra:member", [])]
        if domains:
            picked = random.choice(domains)
            log(f"[INFO] mail.tmから有効ドメインを取得しました: {picked}", cb, "INFO")
            return picked
    except Exception as e:
        log(f"[WARN] ドメイン一覧の取得に失敗しました: {e}", cb, "WARN")
    return None


async def create_mailtm_account(session: aiohttp.ClientSession, cb):
    """mail.tmアカウント作成 + レート制限対応 + 422時だけドメイン自動置換"""
    # もとの安定していたアドレス生成（小文字4 + 数字4）
    def make_address(domain: str) -> str:
        return (
            ''.join(random.choice(string.ascii_lowercase) for _ in range(4))
            + ''.join(random.choice(string.digits) for _ in range(4))
            + f"@{domain}"
        )

    # まずは今まで通り固定ドメインでやる
    address = make_address(FIXED_DOMAIN)
    password = "Aa123456"

    log(f"[RUN] メールアカウント作成中... {address}", cb, "RUN")

    # 最大5回リトライ（429対応・422時は別ドメインで再試行）
    for attempt in range(5):
        async with session.post(f"{MAILTM_BASE}/accounts",
                                json={"address": address, "password": password}) as r:
            if r.status == 201:
                # 作成成功
                break
            elif r.status == 429:
                # レート制限：待って再試行
                wait = 3 + attempt * 2
                log(f"[WARN] mail.tmレート制限。{wait}秒待機して再試行します ({attempt+1}/5)", cb, "WARN")
                await asyncio.sleep(wait)
                continue
            elif r.status == 422:
                # ←今回の問題はここ
                # tiffincrane.com が無効なときだけ、都度 /domains から有効なものを取って再チャレンジ
                body = await r.text()
                log(f"[WARN] 固定ドメインが無効になりました。別ドメインを取得して再試行します。詳細: {body}", cb, "WARN")
                new_domain = await _fetch_random_domain(session, cb)
                if not new_domain:
                    # 取れなかった場合は元の動きと同じく落とす
                    raise RuntimeError(f"mail.tm error {r.status}: {body}")
                # 新しいドメインでアドレスを作り直して次のループで再試行
                address = make_address(new_domain)
                log(f"[INFO] ドメインを切り替えて再試行します: {address}", cb, "INFO")
                continue
            else:
                # その他のエラーは今まで通り即エラー
                raise RuntimeError(f"mail.tm error {r.status}: {await r.text()}")
    else:
        # 5回ともダメだったら今まで通りエラー
        raise RuntimeError("mail.tm error 429: レート制限によりアカウント作成失敗")

    # トークン取得（ここもそのまま）
    async with session.post(f"{MAILTM_BASE}/token",
                            json={"address": address, "password": password}) as r:
        token_data = await r.json()
    token = token_data.get("token")

    headers = {"Authorization": f"Bearer {token}"}
    async with session.get(f"{MAILTM_BASE}/me", headers=headers) as r:
        me = await r.json()

    log(f"[OK] メール準備完了: {address}", cb, "OK")
    return {
        "address": address,
        "password": password,
        "token": token,
        "id": me.get("id")
    }


async def wait_for_mail(session: aiohttp.ClientSession, acc, cb):
    """確認メールを取得する（3回まで再試行）"""
    headers = {"Authorization": f"Bearer {acc['token']}"}
    for attempt in range(1, MAIL_RETRY_TIMES + 1):
        log(f"[INFO] 確認メール待機中 ({attempt}/{MAIL_RETRY_TIMES})", cb, "INFO")
        deadline = time.time() + MAIL_WAIT_SECONDS
        while time.time() < deadline:
            async with session.get(f"{MAILTM_BASE}/messages", headers=headers) as r:
                data = await r.json()
            for m in data.get("hydra:member", []):
                mid = m.get("id")
                async with session.get(f"{MAILTM_BASE}/messages/{mid}", headers=headers) as r:
                    msg = await r.json()
                text = (msg.get("text") or "") + "\n" + (msg.get("intro") or "")
                html = msg.get("html") or ""
                if isinstance(html, list):
                    html = "\n".join(html)
                m2 = re.search(r"https://auth\.level5-id\.com/user_registration/verify/[0-9a-fA-F]+", text + html)
                if m2:
                    log(f"[OK] 確認メール検出: {acc['address']}", cb, "OK")
                    return m2.group(0)
            await asyncio.sleep(2)
        log(f"[WARN] 確認メール未着。再試行します。", cb, "WARN")
    log(f"[ERR] 確認メール取得失敗: {acc['address']}", cb, "ERR")
    return None


async def register_one(email, password, headless, cb):
    """登録メール送信"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()
            log("[RUN] 登録ページへアクセスしています...", cb, "RUN")
            await page.goto("https://auth.level5-id.com/user_registration", wait_until="domcontentloaded", timeout=30000)
            await page.locator(SELECTORS["agree_btn"]).first.click()
            await page.wait_for_url("**/user_registration_agree_terms**", timeout=30000)
            await page.locator(SELECTORS["email_input"]).fill(email)
            await page.locator(SELECTORS["send_btn"]).click()
            await browser.close()
            log(f"[OK] 登録メール送信完了: {email}", cb, "OK")
            return True
    except Exception as e:
        log_exception("登録ページ処理中に例外が発生しました", e, cb)
        return False


async def complete_verify_and_login(email, password, verify_url, headless, cb):
    """確認リンクから登録完了処理"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()
            log("[RUN] 確認リンクにアクセスしています...", cb, "RUN")
            await page.goto(verify_url, wait_until="domcontentloaded", timeout=30000)
            await page.locator(SELECTORS["password_1"]).fill(password)
            await page.locator(SELECTORS["password_2"]).fill(password)
            await page.locator(SELECTORS["register_btn"]).click()
            await browser.close()
            log(f"[OK] 登録完了: {email}", cb, "OK")
            return True
    except Exception as e:
        log_exception("登録完了処理で例外が発生しました", e, cb)
        return False


# =====================================================================
# メイン処理
# =====================================================================

async def run_batch(count, headless, password, logcb, stop_flag):
    """バッチ登録メイン"""
    ensure_output()
    success = 0
    fail = 0
    timeout = aiohttp.ClientTimeout(total=120)
    log("[INFO] === 自動作成を開始します ===", logcb, "INFO")

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while success < count:
            # ここは元のまま：GUIから渡されるのは関数なので()で呼ぶ
            if stop_flag():
                log("[WARN] 停止要求を確認しました。中断します。", logcb, "WARN")
                break
            try:
                acc = await create_mailtm_account(session, logcb)
                sent = await register_one(acc["address"], password, headless, logcb)
                if not sent:
                    fail += 1
                    continue
                verify_url = await wait_for_mail(session, acc, logcb)
                if not verify_url:
                    fail += 1
                    continue
                ok = await complete_verify_and_login(acc["address"], password, verify_url, headless, logcb)
                if ok:
                    rec = {
                        "index": get_next_index(load_accounts()),
                        "email": acc["address"],
                        "password": password,
                        "activated": True,
                        "login_ok": True,
                        "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    data = load_accounts()
                    data.append(rec)
                    save_accounts(data)
                    success += 1
                    
                    # ✅ ここを追加：登録完了ごとに進捗を表示
                    log(f"[PROG] 進捗: {success}/{count}", logcb, "INFO")
                     
                else:
                    fail += 1
            except Exception as e:
                log_exception("処理中に例外が発生しました", e, logcb)
                fail += 1
            await asyncio.sleep(2)

    log(f"[INFO] === 完了: 成功 {success} 件 / 失敗 {fail} 件 ===", logcb, "INFO")


# =====================================================================
# TXT/CSV 変換互換用（convert_accounts_range）
# =====================================================================
def convert_accounts_range(start=None, end=None):
    """
    変換指定のルール：
      ・5～10            => index 5～10
      ・空欄～10         => index 最小～10
      ・5～空欄          => index 5～最大
      ・空欄～空欄       => index 最小～最大（全件）
    """
    accounts = load_accounts()
    if not accounts:
        return []

    indices = [a.get("index", 0) for a in accounts if isinstance(a.get("index", 0), int)]
    if not indices:
        return []

    min_idx = min(indices)
    max_idx = max(indices)

    s = min_idx if start is None else int(start)
    e = max_idx if end is None else int(end)

    if s > e:
        s, e = e, s

    return [a for a in accounts if s <= a.get("index", 0) <= e]
