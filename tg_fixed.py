"""
FIXED Telegram sender with:
- Correct curl_cffi API usage (json parameter instead of content)
- Better error handling
- Detailed logging
- Retry logic
- Connection pooling
"""

import asyncio
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
        self.bots = TELEGRAM_CONFIG['bot_tokens']
        self.channels = TELEGRAM_CONFIG['chat_channels']
        self.workers = workers
        self.debug = debug
        self.queue = asyncio.Queue(maxsize=10000)
        
        self.stats = {
            'sent': 0,
            'failed': 0,
            'queued': 0,
            'retried': 0,
        }
        
        self.error_counts = {}
        self.workers_list = []
        self.running = False
        self.client = None
        
        print(f"📱 Telegram Ready (FIXED v2)")
        print(f"   Bots: {len(self.bots)}")
        print(f"   Workers: {self.workers}")
        print(f"   Debug: {'ON' if debug else 'OFF'}")
        print(f"   curl_cffi: {'YES' if HAS_CURL else 'NO'}")
    
    def _get_channels(self, discount: int) -> list:
        for min_d, names in CHANNEL_RULES['routing']:
            if discount >= min_d:
                return [self.channels[n] for n in names if n in self.channels]
        return [self.channels.get('all', TELEGRAM_CONFIG['chat_id'])]
    
    def format(self, product: Dict) -> str:
        discount = int(product.get('discount', 0))
        emoji = get_discount_emoji(discount)
        
        return OUTPUT_CONFIG['telegram_format'].format(
            emoji=emoji,
            discount=discount,
            price=product.get('current_price', '0'),
            mrp=product.get('original_price', '0'),
            brand=product.get('brand', ''),
            title=product.get('title', 'Unknown'),
            url=product.get('url', ''),
            product_id=product.get('product_id', '')
        )
    
    async def _send(self, chat_id: str, message: str, bot: str, retry: int = 0) -> bool:
        """Send message with retry logic and detailed error logging"""
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": False
        }
        
        try:
            if HAS_CURL:
                # curl_cffi uses 'json' parameter for JSON data
                resp = await self.client.post(
                    url, 
                    json=payload,  # ✅ Use json parameter, not content
                    timeout=15
                )
            else:
                # httpx uses content with headers
                if HAS_ORJSON:
                    content = orjson.dumps(payload)
                else:
                    content = json.dumps(payload).encode()
                
                resp = await self.client.post(
                    url, 
                    content=content, 
                    headers={'Content-Type': 'application/json'}, 
                    timeout=15
                )
            
            if resp.status_code == 200:
                try:
                    data = resp.json() if hasattr(resp, 'json') else (orjson.loads(resp.content) if HAS_ORJSON else json.loads(resp.content))
                    if data.get('ok'):
                        self.stats['sent'] += 1
                        if self.debug:
                            print(f"  ✅ Sent to {chat_id}")
                        return True
                    else:
                        error = data.get('description', 'Unknown error')
                        self._log_error(f"API Error: {error}", chat_id)
                except Exception as parse_err:
                    # Sometimes 200 but can't parse JSON - assume success
                    if self.debug:
                        print(f"  ✅ Sent (parse error: {parse_err})")
                    self.stats['sent'] += 1
                    return True
            
            # Handle specific error codes
            if resp.status_code == 429:  # Rate limit
                if retry < 2:
                    self.stats['retried'] += 1
                    retry_after = 1
                    try:
                        data = resp.json()
                        retry_after = data.get('parameters', {}).get('retry_after', 1)
                    except:
                        pass
                    
                    if self.debug:
                        print(f"  ⏳ Rate limited, waiting {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    return await self._send(chat_id, message, bot, retry + 1)
                self._log_error(f"Rate limited (429)", chat_id)
            
            elif resp.status_code == 403:  # Forbidden
                self._log_error(f"Forbidden (403) - Bot not in channel or not admin", chat_id)
            
            elif resp.status_code == 400:  # Bad request
                try:
                    error_data = resp.json() if hasattr(resp, 'json') else json.loads(resp.content)
                    error = error_data.get('description', 'Bad request')
                    self._log_error(f"Bad request (400): {error}", chat_id)
                except:
                    text = resp.text if hasattr(resp, 'text') else str(resp.content[:100])
                    self._log_error(f"Bad request (400): {text[:100]}", chat_id)
            
            else:
                text = resp.text if hasattr(resp, 'text') else str(resp.content[:100])
                self._log_error(f"HTTP {resp.status_code}: {text[:100]}", chat_id)
            
            self.stats['failed'] += 1
            return False
            
        except asyncio.TimeoutError:
            self._log_error("Timeout", chat_id)
            self.stats['failed'] += 1
            return False
        except Exception as e:
            self._log_error(f"Exception: {type(e).__name__}: {str(e)[:100]}", chat_id)
            self.stats['failed'] += 1
            return False
    
    def _log_error(self, error: str, chat_id: str):
        """Log errors with counting"""
        key = f"{error[:50]}|{chat_id}"
        self.error_counts[key] = self.error_counts.get(key, 0) + 1
        
        if self.debug:
            print(f"  ⚠️ Telegram error: {error} (channel: {chat_id})")
        elif self.error_counts[key] == 1:
            # Only print first occurrence of each error type
            print(f"  ⚠️ Telegram: {error}")
    
    async def _worker(self, wid: int):
        """Worker with better error handling"""
        bot = self.bots[wid % len(self.bots)]
        
        while self.running:
            try:
                msg = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await self._send(msg['chat_id'], msg['message'], bot)
                await asyncio.sleep(0.05)  # Rate limit
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.debug:
                    print(f"  ⚠️ Worker error: {e}")
                await asyncio.sleep(1)
    
    async def start(self):
        """Start persistent workers"""
        if self.running:
            return
        
        self.running = True
        
        # Create HTTP client with better settings
        if HAS_CURL:
            self.client = AsyncSession(impersonate="chrome110", timeout=15)
        else:
            limits = httpx.Limits(
                max_keepalive_connections=50, 
                max_connections=100,
                keepalive_expiry=30
            )
            self.client = httpx.AsyncClient(
                http2=True, 
                limits=limits, 
                timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=True
            )
        
        # Start workers
        self.workers_list = [
            asyncio.create_task(self._worker(i)) 
            for i in range(self.workers)
        ]
        
        print(f"📱 Started {self.workers} Telegram workers")
    
    async def stop(self):
        """Stop workers gracefully"""
        if not self.running:
            return
        
        self.running = False
        
        # Wait for queue to empty
        if self.queue.qsize() > 0:
            print(f"📱 Waiting for {self.queue.qsize()} messages to send...")
            try:
                await asyncio.wait_for(self.queue.join(), timeout=30)
            except asyncio.TimeoutError:
                print(f"  ⚠️ Timeout waiting for queue, {self.queue.qsize()} messages remain")
        
        # Cancel workers
        for worker in self.workers_list:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self.workers_list, return_exceptions=True)
        
        # Close client
        if self.client:
            try:
                if HAS_CURL:
                    pass  # AsyncSession auto-closes
                else:
                    await self.client.aclose()
            except:
                pass
        
        # Print error summary if there were errors
        if self.error_counts and self.debug:
            print(f"\n📱 Telegram Error Summary:")
            for key, count in sorted(self.error_counts.items(), key=lambda x: -x[1])[:5]:
                error, channel = key.split('|', 1)
                print(f"  {count}x: {error} ({channel})")
        
        print(f"📱 Stopped Telegram workers")
    
    def queue_product(self, product: Dict):
        """Queue a product for sending"""
        discount = int(product.get('discount', 0))
        channels = self._get_channels(discount)
        message = self.format(product)
        
        for cid in channels:
            try:
                self.queue.put_nowait({'chat_id': cid, 'message': message})
                self.stats['queued'] += 1
            except:
                pass
    
    def get_stats(self) -> Dict:
        stats = self.stats.copy()
        stats['pending'] = self.queue.qsize()
        return stats


# Backward compatibility alias
TelegramImproved = TelegramFixed
