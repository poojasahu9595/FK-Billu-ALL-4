"""
cmd_handler.py - Telegram Command Handler (Threading version)
=============================================================
Myntra wali style mein rewrite kiya — sync + daemon thread.
"""

import re
import time
import threading
from typing import Optional, TYPE_CHECKING

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL = True
except ImportError:
    import requests as cffi_requests
    HAS_CURL = False

from config import TELEGRAM_CONFIG, SCRAPER_CONFIG, change_speed_preset, SPEED_PRESETS
from utils import load_urls

if TYPE_CHECKING:
    from main import App


class LinkManager:
    def __init__(self, filepath: str = "links.txt"):
        self.filepath = filepath

    def load(self):
        return load_urls(self.filepath)

    def add(self, url: str) -> bool:
        url = url.strip()
        if not url:
            return False
        urls = self.load()
        if url in urls:
            return False
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(url + "\n")
        return True

    def remove(self, url: str) -> bool:
        url = url.strip()
        urls = self.load()
        if url not in urls:
            return False
        with open(self.filepath, "w", encoding="utf-8") as f:
            for u in urls:
                if u != url:
                    f.write(u + "\n")
        return True

    def count(self) -> int:
        return len(self.load())


class CommandHandler:
    """
    Sync command handler - daemon thread mein chalta hai.
    Event loop se bilkul alag, kabhi starve nahi hota.
    """

    HELP_TEXT = """Bot Commands:

ADD# <url>          - URL add karo
REMOVE# <url>       - URL remove karo
LIST#               - Sabhi URLs dekho
CLEAR# <pid>        - Product DB se clear karo
CLEAR# (reply)      - Deal reply karke auto-detect
SPEED# <preset>     - Speed: safe/balanced/fast/aggressive
SPAM_ADD# <word>    - Spam word add
SPAM_REMOVE# <word> - Spam word remove
SPAM_LIST#          - Spam words list
STATUS#             - Live status
HELP#               - Yeh message"""

    def __init__(self, app: "App" = None, bot_token: str = None,
                 chat_id: str = None, poll_timeout: int = 15):
        self.app          = app
        self.bot_token    = bot_token or TELEGRAM_CONFIG["bot_tokens"][0]
        self.chat_id      = str(chat_id or TELEGRAM_CONFIG["chat_id"])
        self.poll_timeout = poll_timeout
        self.link_manager = LinkManager(SCRAPER_CONFIG.get("links_file", "links.txt"))
        self._last_update_id  = 0
        self._seen_ids: set   = set()
        self._running         = False
        self._thread          = None
        self._consecutive_errors = 0

        print(f"🎮 CommandHandler ready (threading mode)")
        print(f"   Bot  : ...{self.bot_token[-10:]}")
        print(f"   Chat : {self.chat_id}")

    def _api_get(self, method: str, **params) -> dict:
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
        try:
            # impersonate nahi — Telegram API ke liye zaroorat nahi,
            # aur chrome impersonation long-polling tod deta hai
            r = cffi_requests.get(url, params=params,
                                  timeout=self.poll_timeout + 10)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"  CMD API error ({method}): {e}")
        return {}

    def _api_post(self, method: str, **data) -> dict:
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
        try:
            r = cffi_requests.post(url, json=data, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"  CMD send error: {e}")
        return {}

    def send(self, text: str):
        self._api_post("sendMessage", chat_id=self.chat_id, text=text,
                       disable_web_page_preview=True)

    def _get_updates(self) -> list:
        data = self._api_get("getUpdates",
                             offset=self._last_update_id + 1,
                             timeout=self.poll_timeout,
                             allowed_updates=["message"])
        return data.get("result", [])

    @staticmethod
    def _extract_pid(text: str) -> Optional[str]:
        if not text:
            return None
        m = re.search(r'[?&]pid=([A-Z0-9]{10,25})', text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        m = re.search(r'/p/([A-Z0-9]{10,25})(?:[/?]|$)', text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        m = re.search(r'myntra\.com/(?:buy/)?(\d{6,10})', text, re.IGNORECASE)
        if m:
            return m.group(1)
        return None

    def _process(self, text: str, replied_text: str = None) -> Optional[str]:
        text = text.strip()

        if text.startswith("ADD#"):
            url = text[4:].strip()
            if not url.startswith("http"):
                return "URL dena zaroori hai (http...)!"
            if "flipkart.com" not in url and "myntra.com" not in url:
                return "Sirf Flipkart ya Myntra URL allowed hai!"
            added = self.link_manager.add(url)
            if added:
                return f"URL add ho gaya!\nTotal: {self.link_manager.count()}"
            return f"URL pehle se exist karta hai!\nTotal: {self.link_manager.count()}"

        elif text.startswith("REMOVE#"):
            url = text[7:].strip()
            removed = self.link_manager.remove(url)
            if removed:
                return f"URL remove ho gaya!\nTotal: {self.link_manager.count()}"
            return "URL nahi mila!"

        elif text.strip() == "LIST#":
            urls = self.link_manager.load()
            if not urls:
                return "Koi URL configure nahi hai!"
            lines = [f"Total URLs: {len(urls)}\n"]
            for i, u in enumerate(urls[:15], 1):
                short = u.replace("https://", "").replace("http://", "")
                lines.append(f"{i}. {short[:70]}")
            if len(urls) > 15:
                lines.append(f"\n...aur {len(urls) - 15} more")
            return "\n".join(lines)

        elif text.startswith("CLEAR#"):
            pid = text[6:].strip()
            if not pid:
                if replied_text:
                    pid = self._extract_pid(replied_text)
                    if not pid:
                        return ("Reply wale message mein product ID nahi mili!\n\n"
                                "Deal message ko reply karke CLEAR# likho\n"
                                "Ya manually: CLEAR# <product_id>")
                else:
                    return ("Product ID dena zaroori hai!\n\n"
                            "1. Deal message reply karke CLEAR# likho\n"
                            "2. CLEAR# ITME8GYYHKNTGDYZ manually likho")

            flt = getattr(self.app, "filter", None) if self.app else None
            if not flt:
                return "Filter available nahi hai!"
            conn = getattr(flt, "conn", None)
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT product_id FROM products WHERE product_id=?", (pid,))
                    row = cur.fetchone()
                    if row:
                        conn.execute("DELETE FROM products WHERE product_id=?", (pid,))
                        conn.commit()
                        flt._cache.pop(pid, None)
                        return (f"Product clear ho gaya!\n\n"
                                f"ID: {pid}\n"
                                f"Agle cycle mein nayi entry banega.")
                    return f"Product {pid} DB mein nahi mila!\nShayad pehle se clear hai."
                except Exception as e:
                    return f"DB error: {e}"
            return "DB connection nahi mila!"

        elif text.startswith("SPEED#"):
            preset = text[6:].strip().lower()
            if preset not in SPEED_PRESETS:
                opts = " / ".join(SPEED_PRESETS.keys())
                return f"Invalid preset!\n\nOptions: {opts}"
            change_speed_preset(preset)
            p = SPEED_PRESETS[preset]
            return (f"Speed preset -> {preset.upper()}\n\n"
                    f"Sessions   : {p['num_sessions']}\n"
                    f"Concurrent : {p['max_concurrent_pages']}\n"
                    f"Parallel   : {p['parallel_batch_size']}\n"
                    f"Loop delay : {p['loop_delay']}s\n\n"
                    f"Next cycle se apply hoga.")

        elif text.startswith("SPAM_ADD#"):
            word = text[9:].strip().lower()
            if not word:
                return "Word dena zaroori hai!\nUsage: SPAM_ADD# <word>"
            flt = getattr(self.app, "filter", None) if self.app else None
            if flt:
                flt.add_spam_word(word)
                return f"Spam word add: {word}\nTotal: {len(flt.spam_words)}"
            return "Filter available nahi!"

        elif text.startswith("SPAM_REMOVE#"):
            word = text[12:].strip().lower()
            if not word:
                return "Word dena zaroori hai!\nUsage: SPAM_REMOVE# <word>"
            flt = getattr(self.app, "filter", None) if self.app else None
            if flt:
                flt.remove_spam_word(word)
                return f"Spam word remove: {word}\nTotal: {len(flt.spam_words)}"
            return "Filter available nahi!"

        elif text.strip() == "SPAM_LIST#":
            flt = getattr(self.app, "filter", None) if self.app else None
            if not flt:
                return "Filter available nahi!"
            words = flt.get_spam_words()
            if not words:
                return "Koi spam word set nahi hai!"
            return "Spam Words:\n" + "\n".join(f"- {w}" for w in words[:50])

        elif text.strip() == "STATUS#":
            from datetime import datetime
            lines = [f"Scraper Status\n",
                     f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                     f"URLs: {self.link_manager.count()}"]
            flt = getattr(self.app, "filter", None) if self.app else None
            if flt:
                fs = flt.get_stats()
                lines += [f"DB total   : {fs.get('total', 0):,}",
                          f"Hot (70%+) : {fs.get('hot', 0):,}",
                          f"Notified   : {fs.get('notifications', 0):,}",
                          f"Sponsored  : {fs.get('blocked_sponsored', 0):,}",
                          f"Spam       : {fs.get('blocked_spam', 0):,}",
                          f"Wrong brand: {fs.get('blocked_wrong_brand', 0):,}",
                          f"Passed     : {fs.get('passed', 0):,}"]
            tg = getattr(self.app, "telegram", None) if self.app else None
            if tg:
                ts = tg.get_stats()
                lines += [f"\nTelegram:",
                          f"Sent   : {ts.get('sent', 0):,}",
                          f"Failed : {ts.get('failed', 0):,}",
                          f"Pending: {ts.get('pending', 0):,}"]
            sc = getattr(self.app, "scraper", None) if self.app else None
            if sc:
                ss = sc.get_stats()
                lines += [f"\nScraper:",
                          f"Requests: {ss.get('total_requests', 0):,}",
                          f"Products: {ss.get('total_products', 0):,}",
                          f"Errors  : {ss.get('total_errors', 0):,}"]
            return "\n".join(lines)

        elif text.strip() in ("HELP#", "#"):
            return self.HELP_TEXT

        return None

    def _loop(self):
        """Blocking polling loop — daemon thread mein."""
        print("🎮 Command handler: polling started (thread)")
        self._consecutive_errors = 0

        while self._running:
            try:
                if self._consecutive_errors >= 5:
                    print("CMD: too many errors, backing off 30s...")
                    time.sleep(30)
                    self._consecutive_errors = 0
                    continue

                updates = self._get_updates()
                self._consecutive_errors = 0

                for update in updates:
                    uid = update.get("update_id", 0)
                    if uid in self._seen_ids:
                        continue
                    self._seen_ids.add(uid)
                    self._last_update_id = uid
                    if len(self._seen_ids) > 500:
                        self._seen_ids.clear()
                        self._seen_ids.add(uid)

                    msg        = update.get("message", {})
                    text       = msg.get("text", "")
                    chat_id    = str(msg.get("chat", {}).get("id", ""))
                    if chat_id != self.chat_id:
                        continue
                    if not text:
                        continue

                    replied_text = None
                    reply_to = msg.get("reply_to_message", {})
                    if reply_to:
                        replied_text = (reply_to.get("text", "")
                                        or reply_to.get("caption", ""))

                    response = self._process(text, replied_text=replied_text)
                    if response:
                        print(f"📱 CMD: {text[:60]}")
                        self.send(response)

                time.sleep(1)

            except Exception as e:
                self._consecutive_errors += 1
                print(f"CMD loop error: {e}")
                time.sleep(3)

        print("🛑 CMD handler stopped")

    async def run(self):
        """asyncio.gather() compatible — thread start karke wait karta hai."""
        import asyncio
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="CmdHandler")
        self._thread.start()
        while self._running and self._thread.is_alive():
            await asyncio.sleep(1)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
