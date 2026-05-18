"""
tg_fixed.py — Fixed Telegram Sender
=====================================
FIXES:
  1. Markdown parse errors → auto-retry without parse_mode (plain text fallback)
  2. Failed count properly tracked with reason logging
  3. _telegram_loop spam fix → pending=0 hone par print nahi karta
  4. Smart bot rotation with cooldown
  5. Error summary on stop
"""

import asyncio
import time
from typing import Dict
import platform

if platform.system() != 'Windows':
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except:
        pass

try:
    import orjson
    HAS_ORJSON = True
except:
    import json
    HAS_ORJSON = False

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL = True
except:
    import httpx
    HAS_CURL = False

from config import TELEGRAM_CONFIG, CHANNEL_RULES, OUTPUT_CONFIG, get_discount_emoji


class TelegramFixed:

    def __init__(self, workers: int = 20, debug: bool = False):
        self.bots     = TELEGRAM_CONFIG['bot_tokens']
        self.channels = TELEGRAM_CONFIG['chat_channels']
        self.workers  = workers
        self.debug    = debug
        self.queue    = asyncio.Queue(maxsize=10000)

        self.stats = {
            'sent':    0,
            'failed':  0,
            'queued':  0,
            'retried': 0,
        }

        # Error tracking: reason → count
        self.error_counts: dict = {}

        self.workers_list: list = []
        self.running   = False
        self.client    = None

        # Bot rotation
        self._bot_cooldown: dict = {}   # token → cooldown_until
        self._bot_failures: dict = {}   # token → fail count

        # Per-bot rate limiter: max 20 msg/s per bot
        # Telegram limit: 30 msg/s per bot — 20 rakho safe margin ke saath
        self._bot_last_sent: dict = {}  # token → last_sent_timestamp
        self._BOT_MIN_INTERVAL = 1.0 / 20  # 50ms between msgs per bot

        # Global rate: max 25 msg/s across all bots (one channel limit ~30/s)
        self._global_semaphore = None  # asyncio.Semaphore — start() mein banao

        print(f"📱 Telegram Ready")
        print(f"   Bots      : {len(self.bots)}")
        print(f"   Workers   : {self.workers}")
        print(f"   Rate limit: 20 msg/s per bot  |  25 msg/s global")
        print(f"   curl_cffi : {'YES' if HAS_CURL else 'NO (httpx)'}")

    # ── Channel routing ───────────────────────────────────────

    def _get_channels(self, discount: int) -> list:
        for min_d, names in CHANNEL_RULES['routing']:
            if discount >= min_d:
                return [self.channels[n] for n in names if n in self.channels]
        return [self.channels.get('all', TELEGRAM_CONFIG.get('chat_id', ''))]

    # ── Format ────────────────────────────────────────────────

    def format(self, product: Dict) -> str:
        discount = int(product.get('discount', 0))
        emoji    = get_discount_emoji(discount)

        # Special chars escape nahi karte — plain text format use karo
        # Markdown OFF by default taaki parse errors na aayein
        return OUTPUT_CONFIG['telegram_format'].format(
            emoji=emoji,
            discount=discount,
            price=product.get('current_price', '0'),
            mrp=product.get('original_price', '0'),
            brand=product.get('brand', ''),
            title=product.get('title', 'Unknown'),
            url=product.get('url', ''),
            product_id=product.get('product_id', ''),
        )

    # ── Send (with plain-text fallback) ──────────────────────

    async def _send(self, chat_id: str, message: str, bot: str,
                    retry: int = 0, wid: int = 0,
                    use_markdown: bool = False) -> bool:
        """
        Send one message.
        - First attempt: plain text (no parse_mode) — avoids Markdown parse errors
        - On 400 with markdown: already plain, so just log
        - On 429: rotate bot immediately
        """
        url = f"https://api.telegram.org/bot{bot}/sendMessage"

        payload: dict = {
            "chat_id":                  chat_id,
            "text":                     message,
            "disable_web_page_preview": False,
        }
        if use_markdown:
            payload["parse_mode"] = "Markdown"

        try:
            if HAS_CURL:
                resp = await self.client.post(url, json=payload, timeout=15)
            else:
                resp = await self.client.post(url, json=payload)

            # ── 200 OK ───────────────────────────────────────
            if resp.status_code == 200:
                try:
                    data = resp.json() if hasattr(resp, 'json') else (
                        orjson.loads(resp.content) if HAS_ORJSON else
                        __import__('json').loads(resp.content)
                    )
                    if data.get('ok'):
                        self.stats['sent'] += 1
                        return True
                    # ok=False but 200 — rare
                    err = data.get('description', 'ok=False')
                    self._log_error(f"ok=False: {err}", chat_id)
                except Exception:
                    # Can't parse JSON but got 200 → assume success
                    self.stats['sent'] += 1
                    return True

            # ── 429 Rate limit ────────────────────────────────
            elif resp.status_code == 429:
                retry_after = 30.0
                try:
                    data = resp.json() if hasattr(resp, 'json') else {}
                    retry_after = float(
                        data.get('parameters', {}).get('retry_after', 30)
                    )
                except Exception:
                    pass
                self._mark_ratelimited(bot, retry_after)
                if retry < len(self.bots):
                    self.stats['retried'] += 1
                    new_bot = self._pick_bot(wid + retry + 1)
                    # Naya bot bhi throttle karo
                    last = self._bot_last_sent.get(new_bot, 0)
                    wait = self._BOT_MIN_INTERVAL - (time.time() - last)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    return await self._send(chat_id, message, new_bot,
                                            retry + 1, wid + 1, use_markdown)
                self._log_error("429 all bots exhausted", chat_id)

            # ── 400 Bad Request ───────────────────────────────
            elif resp.status_code == 400:
                try:
                    data = resp.json() if hasattr(resp, 'json') else {}
                    desc = data.get('description', 'Bad request')
                except Exception:
                    desc = "Bad request (parse failed)"

                # Markdown parse error → retry as plain text once
                if use_markdown and "can't parse" in desc.lower() and retry == 0:
                    self.stats['retried'] += 1
                    return await self._send(chat_id, message, bot,
                                            retry=1, wid=wid, use_markdown=False)

                self._log_error(f"400: {desc[:80]}", chat_id)

            # ── 403 Forbidden ─────────────────────────────────
            elif resp.status_code == 403:
                self._log_error("403: Bot not admin or kicked from channel", chat_id)

            # ── Other ─────────────────────────────────────────
            else:
                try:
                    text_snippet = resp.text[:80] if hasattr(resp, 'text') else str(resp.content[:80])
                except Exception:
                    text_snippet = "?"
                self._log_error(f"HTTP {resp.status_code}: {text_snippet}", chat_id)

        except asyncio.TimeoutError:
            self._log_error("Timeout", chat_id)
        except Exception as e:
            self._log_error(f"{type(e).__name__}: {str(e)[:80]}", chat_id)

        self.stats['failed'] += 1
        return False

    # ── Error logging ─────────────────────────────────────────

    def _log_error(self, error: str, chat_id: str):
        key = f"{error[:60]}|{chat_id}"
        prev = self.error_counts.get(key, 0)
        self.error_counts[key] = prev + 1

        # First time kisi error ko print karo
        if prev == 0:
            print(f"  ⚠️  TG error: {error}  (chat: {chat_id})")
        # Har 100 baar repeat hone par bhi print karo
        elif (prev + 1) % 100 == 0:
            print(f"  ⚠️  TG error x{prev+1}: {error}  (chat: {chat_id})")

    # ── Bot rotation ──────────────────────────────────────────

    def _pick_bot(self, wid: int) -> str:
        now = time.time()
        for i in range(len(self.bots)):
            bot = self.bots[(wid + i) % len(self.bots)]
            if self._bot_cooldown.get(bot, 0) <= now:
                return bot
        # Sab rate-limited → least cooldown wala
        return min(self.bots, key=lambda b: self._bot_cooldown.get(b, 0))

    def _mark_ratelimited(self, bot: str, retry_after: float = 30.0):
        self._bot_cooldown[bot] = time.time() + retry_after
        self._bot_failures[bot] = self._bot_failures.get(bot, 0) + 1
        print(f"  ⏸️  Bot ...{bot[-10:]} rate-limited → {retry_after:.0f}s cooldown")

    # ── Worker ────────────────────────────────────────────────

    async def _wait_for_bot(self, bot: str):
        """Per-bot rate limiter — ek bot se max 20 msg/s."""
        last = self._bot_last_sent.get(bot, 0)
        wait = self._BOT_MIN_INTERVAL - (time.time() - last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._bot_last_sent[bot] = time.time()

    async def _worker(self, wid: int):
        while self.running:
            try:
                msg = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # Global semaphore: max 25 concurrent sends at once
                async with self._global_semaphore:
                    bot = self._pick_bot(wid)
                    await self._wait_for_bot(bot)
                    await self._send(msg['chat_id'], msg['message'], bot, wid=wid)

                self.queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.debug:
                    print(f"  ⚠️  Worker {wid} error: {e}")
                await asyncio.sleep(1)

    # ── Start / Stop ──────────────────────────────────────────

    async def start(self):
        if self.running:
            return
        self.running = True

        # Global semaphore: max 25 msgs in-flight at once
        self._global_semaphore = asyncio.Semaphore(25)

        if HAS_CURL:
            self.client = AsyncSession(impersonate="chrome110", timeout=15)
        else:
            limits = httpx.Limits(
                max_keepalive_connections=50,
                max_connections=100,
                keepalive_expiry=30,
            )
            self.client = httpx.AsyncClient(
                http2=True,
                limits=limits,
                timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=True,
            )

        self.workers_list = [
            asyncio.create_task(self._worker(i))
            for i in range(self.workers)
        ]
        print(f"📱 Started {self.workers} Telegram workers")

    async def stop(self):
        if not self.running:
            return
        self.running = False

        if self.queue.qsize() > 0:
            print(f"📱 Flushing {self.queue.qsize()} pending messages…")
            try:
                await asyncio.wait_for(self.queue.join(), timeout=30)
            except asyncio.TimeoutError:
                print(f"  ⚠️  Flush timeout, {self.queue.qsize()} messages remain")

        for w in self.workers_list:
            w.cancel()
        await asyncio.gather(*self.workers_list, return_exceptions=True)

        if self.client:
            try:
                if not HAS_CURL:
                    await self.client.aclose()
            except Exception:
                pass

        # Error summary
        if self.error_counts:
            print(f"\n📱 Telegram Error Summary (total failed={self.stats['failed']}):")
            top = sorted(self.error_counts.items(), key=lambda x: -x[1])[:8]
            for key, cnt in top:
                err, cid = key.split('|', 1)
                print(f"  {cnt:>5}x  {err}  (chat: {cid})")

        print(f"📱 Stopped | sent={self.stats['sent']} failed={self.stats['failed']}")

    # ── Public API ────────────────────────────────────────────

    def queue_product(self, product: Dict):
        discount = int(product.get('discount', 0))
        channels = self._get_channels(discount)
        message  = self.format(product)

        for cid in channels:
            try:
                self.queue.put_nowait({'chat_id': cid, 'message': message})
                self.stats['queued'] += 1
            except asyncio.QueueFull:
                self.stats['failed'] += 1

    def get_stats(self) -> Dict:
        s = self.stats.copy()
        s['pending'] = self.queue.qsize()
        return s


# Backward compat
TelegramImproved = TelegramFixed
