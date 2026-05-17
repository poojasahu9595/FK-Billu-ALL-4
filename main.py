"""
PRODUCTION MAIN - Multi-Session Scraper
Optimized for 2-minute target with 10-15 sessions
"""

import asyncio
import time
import os
import sys
from typing import List, Dict
import platform

if platform.system() != 'Windows':
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except Exception:
        pass
else:
    # Windows optimization
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from config import SCRAPER_CONFIG, DUPLICATE_CONFIG, FEATURES, initialize_directories
from scraper_multi_session import MultiSessionScraper
from filter import Filter
from tg_fixed import TelegramFixed as Telegram
from utils import format_time
from storage import ProductStorage


def load_urls(file: str = "links.txt") -> List[str]:
    """Load URLs from file"""
    try:
        with open(file, 'r', encoding='utf-8') as f:
            urls = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if line.startswith('http') or line.startswith('/'):
                        urls.append(line)
            return urls
    except FileNotFoundError:
        with open(file, 'w', encoding='utf-8') as f:
            f.write("# Add your Flipkart URLs here (one per line)\n")
            f.write("# Example:\n")
            f.write("# /mobiles/pr?sid=tyy,4io\n")
            f.write("# /laptops/pr?sid=6bo,b5g\n")
        return []
    except Exception as e:
        print(f"❌ Failed to load URLs from {file}: {e}")
        return []


class ProductionApp:

    def __init__(self):
        initialize_directories()

        print("\n" + "=" * 80)
        print(" 🚀 PRODUCTION FLIPKART SCRAPER ".center(80, "="))
        print(" 🔐 Multi-Session | Ultra-Fast | Production Ready ".center(80, "="))
        print("=" * 80 + "\n")

        # Multi-session scraper
        num_sessions = SCRAPER_CONFIG.get('num_sessions', 15)
        self.scraper = MultiSessionScraper(num_sessions=num_sessions)

        self.filter = Filter(
            db_path=DUPLICATE_CONFIG['db_path'],
            min_new=DUPLICATE_CONFIG['min_discount_new'],
            min_exist=DUPLICATE_CONFIG['min_discount_existing'],
            min_change=DUPLICATE_CONFIG['min_change_percent']
        ) if FEATURES.get('enable_duplicate_filter', False) else None

        self.telegram = Telegram(
            workers=SCRAPER_CONFIG.get('telegram_workers', 25),
            debug=False
        ) if FEATURES.get('enable_telegram_notifications', False) else None

        self.storage = ProductStorage(
            db_path=SCRAPER_CONFIG.get('archive_db_path', 'data/products_archive.db'),
            use_duckdb=FEATURES.get('enable_duckdb_analytics', False)
        ) if FEATURES.get('enable_storage', True) else None

        self.stats = {
            'cycles': 0,
            'found': 0,
            'posted': 0,
            'total_time': 0,
            'avg_speed': 0
        }

        self.initialized = False

        print("\n" + "=" * 80)
        print(" ✅ COMPONENTS LOADED ".center(80, "="))
        print("=" * 80 + "\n")

    async def initialize(self):
        """Initialize multi-session system"""
        if self.initialized:
            return

        print("\n" + "=" * 80)
        print(" 🔐 INITIALIZING MULTI-SESSION SYSTEM ".center(80, "="))
        print("=" * 80 + "\n")

        success = await self.scraper.initialize()

        if success:
            print("\n✅ Multi-session system ready!")
        else:
            print("\n⚠️ Some sessions failed, but continuing with available ones")

        self.initialized = True

        print("\n" + "=" * 80)
        print(" 🚀 READY TO SCRAPE ".center(80, "="))
        print("=" * 80 + "\n")

    def process(self, product: Dict) -> bool:
        """Process single product"""
        try:
            pid = product.get('product_id')
            price = product.get('current_price', '0')
            mrp = product.get('original_price', '0')
            disc = int(product.get('discount', 0))

            if self.filter:
                ok, reason = self.filter.should_notify(pid, price, mrp, disc)
                if not ok:
                    return False
            else:
                ok = True

            if ok and self.telegram:
                self.telegram.queue_product(product)

            if ok and self.filter:
                self.filter.save(
                    pid,
                    product.get('listing_id', ''),
                    price,
                    disc,
                    product.get('brand', ''),
                    product.get('title', '')
                )

            return ok
        except Exception:
            return False

    def process_all(self, products: List[Dict]) -> int:
        """Process all products"""
        posted = 0
        for product in products:
            if self.process(product):
                posted += 1
        return posted

    async def scrape_url_tracked(self, url: str, idx: int, total: int) -> tuple:
        """Scrape URL with progress tracking"""
        category = url.split('/')[-1].split('?')[0] if '/' in url else url[:30]

        start = time.time()
        products = await self.scraper.scrape_url(url)
        elapsed = time.time() - start

        if products:
            posted = self.process_all(products)
            speed = len(products) / elapsed if elapsed > 0 else 0

            print(
                f"[{idx}/{total}] {category[:40]:<40} | "
                f"{len(products):>4} products | {elapsed:>5.1f}s | {speed:>5.1f}/s"
            )

            self.stats['found'] += len(products)
            self.stats['posted'] += posted

            return len(products), products, elapsed, speed
        else:
            print(f"[{idx}/{total}] {category[:40]:<40} | {0:>4} products | {0:>5.1f}s")
            return 0, [], 0, 0

    async def scrape_urls_batch(self, urls: List[str], batch_size: int = 20):
        """Process URLs in optimized batches"""
        all_found = 0
        total_elapsed = 0

        print(f"\n{'=' * 90}")
        print(f"  Processing {len(urls)} URLs with multi-session system")
        print(f"  Batch size: {batch_size} | Sessions: {SCRAPER_CONFIG.get('num_sessions', 15)}")
        print(f"{'=' * 90}")
        print(f"{'Progress':<10} | {'Category':<40} | {'Products':>8} | {'Time':>6} | {'Speed':>7}")
        print(f"{'-' * 90}")

        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(urls) + batch_size - 1) // batch_size

            batch_start = time.time()

            tasks = [
                self.scrape_url_tracked(url, i + idx + 1, len(urls))
                for idx, url in enumerate(batch)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_products = []
            batch_speed = 0
            batch_count = 0

            for result in results:
                if isinstance(result, Exception):
                    print(f"⚠️ Batch task failed: {result}")
                    continue

                if isinstance(result, tuple):
                    count, products, elapsed, speed = result
                    all_found += count
                    batch_products.extend(products)
                    if speed > 0:
                        batch_speed += speed
                        batch_count += 1

            batch_elapsed = time.time() - batch_start
            total_elapsed += batch_elapsed

            if self.storage and batch_products:
                asyncio.create_task(self.storage.save_products(batch_products))

            avg_speed = batch_speed / batch_count if batch_count > 0 else 0
            print(f"{'-' * 90}")
            print(
                f"Batch {batch_num}/{total_batches}: "
                f"{len(batch_products)} products in {batch_elapsed:.1f}s | Avg: {avg_speed:.1f} prod/s"
            )

            if batch_num < total_batches:
                remaining = len(urls) - (i + len(batch))
                processed = i + len(batch)
                avg_time_per_url = total_elapsed / processed if processed > 0 else 0
                eta_seconds = avg_time_per_url * remaining
                print(f"ETA: {format_time(int(eta_seconds))} remaining")

            print(f"{'-' * 90}\n")

            if i + batch_size < len(urls):
                delay = SCRAPER_CONFIG.get('delay_between_batches', 1)
                await asyncio.sleep(delay)

        avg_speed = all_found / total_elapsed if total_elapsed > 0 else 0
        self.stats['avg_speed'] = avg_speed

        return all_found, total_elapsed

    async def cycle(self, num: int):
        """Run single scraping cycle"""
        print("\n" + "=" * 80)
        print(f" 🔄 CYCLE {num} ".center(80, "="))
        print("=" * 80)

        urls = load_urls(SCRAPER_CONFIG['links_file'])

        if not urls:
            print("❌ No URLs found in links.txt!")
            print("   Add URLs to links.txt and try again.")
            return

        print(f"📋 URLs: {len(urls)}")

        if self.telegram and not self.telegram.running:
            await self.telegram.start()

        cycle_start = time.time()

        batch_size = SCRAPER_CONFIG.get('parallel_batch_size', 20)
        found, elapsed = await self.scrape_urls_batch(urls, batch_size)

        cycle_elapsed = time.time() - cycle_start

        self.stats['cycles'] += 1
        self.stats['total_time'] += cycle_elapsed

        speed = found / cycle_elapsed if cycle_elapsed > 0 else 0

        print(f"\n{'=' * 80}")
        print(f" ⚡ CYCLE {num} COMPLETE ".center(80, "="))
        print(f"{'=' * 80}")
        print(f"  Time: {format_time(int(cycle_elapsed))}")
        print(f"  Products: {found:,}")
        print(f"  Speed: {speed:.1f} products/second")
        print(f"{'=' * 80}\n")

        if self.telegram:
            pending = self.telegram.queue.qsize()
            if pending > 0:
                print(f"📱 {pending} messages queued (sending in background)")

        self.print_stats(num)
        self.scraper.print_session_stats()

    def print_stats(self, num: int):
        """Print statistics"""
        print(f"\n📊 Overall Stats:")
        print(f"   Found: {self.stats['found']:,}")
        print(f"   Posted: {self.stats['posted']:,}")
        print(f"   Avg Speed: {self.stats['avg_speed']:.1f} prod/s")

        if self.filter:
            f = self.filter.get_stats()
            print(f"\n💾 Filter DB:")
            print(f"   Total: {f['total']:,}")
            print(f"   Hot (70%+): {f['hot']:,}")

        if self.telegram:
            t = self.telegram.get_stats()
            print(f"\n📱 Telegram:")
            print(f"   Sent: {t['sent']:,}")
            print(f"   Failed: {t['failed']}")
            print(f"   Queued: {t['queued']}")

        if self.storage:
            s = self.storage.get_stats()
            print(f"\n💿 Archive DB:")
            print(f"   Total: {s.get('total', 0):,}")
            print(f"   Hot deals: {s.get('hot_deals', 0):,}")
            if s.get('top_brands'):
                top = s['top_brands'][0]
                print(f"   Top brand: {top[0]} ({top[1]:,} products)")

        print("=" * 80)

    async def continuous(self):
        """Run in continuous mode"""
        print(f"\n🔄 Continuous Mode")
        print(f"   Loop interval: {SCRAPER_CONFIG['loop_delay']}s ({SCRAPER_CONFIG['loop_delay'] // 60}m)")
        print(f"   Press Ctrl+C to stop\n")

        await self.initialize()

        if self.telegram:
            await self.telegram.start()

        cycle_num = 1
        try:
            while True:
                await self.cycle(cycle_num)

                mins = SCRAPER_CONFIG['loop_delay'] // 60
                print(f"\n⏸️ Waiting {mins}m until next cycle...")

                await asyncio.sleep(SCRAPER_CONFIG['loop_delay'])
                cycle_num += 1

        except KeyboardInterrupt:
            print("\n\n⚠️ Stopping...")
        finally:
            if self.telegram:
                await self.telegram.stop()
            await self.cleanup()

    async def cleanup(self):
        """Cleanup resources"""
        print("\n🧹 Cleaning up...")

        if self.scraper:
            await self.scraper.close()

        if self.filter:
            self.filter.close()

        if self.storage:
            self.storage.close()

        print("✅ Cleanup complete")

    async def run_once(self):
        """Run single cycle"""
        try:
            await self.initialize()

            if self.telegram:
                await self.telegram.start()

            await self.cycle(1)
        finally:
            if self.telegram:
                await self.telegram.stop()
            await self.cleanup()


def get_run_mode() -> str:
    """
    Determine run mode safely for local and Railway environments.
    Supports env var RUN_MODE and falls back to interactive prompt only when available.
    """
    run_mode = os.getenv("RUN_MODE", "").strip().lower()

    if run_mode in ("1", "once", "single"):
        print("\nUsing RUN_MODE=once")
        return "1"

    if run_mode in ("2", "continuous", "loop"):
        print("\nUsing RUN_MODE=continuous")
        return "2"

    if sys.stdin and sys.stdin.isatty():
        return input("\nChoice (1 or 2): ").strip()

    print("\nNo interactive stdin detected. Defaulting to continuous mode.")
    return "2"


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║          🚀 PRODUCTION FLIPKART SCRAPER                              ║
║          🔐 Multi-Session | Ultra-Fast | 2-Minute Target             ║
╚══════════════════════════════════════════════════════════════════════╝

Features:
  ✓ 10-15 concurrent sessions (no rate limiting!)
  ✓ Connection pooling & reuse
  ✓ Response caching
  ✓ Concurrent page fetching
  ✓ Real-time performance monitoring
  ✓ High-performance database storage

Expected Performance:
  • Speed: 800-1,500 products/minute
  • Time for ~150k products: 2-3 minutes
  • Rate limit errors: <0.5%

""")

    app = ProductionApp()

    print("\n" + "=" * 80)
    print("Select Mode:")
    print("  1. Run once (single cycle)")
    print("  2. Run continuous (loop forever)")
    print("=" * 80)

    choice = get_run_mode()

    if choice == "1":
        print("\n▶️ Starting single cycle...\n")
        asyncio.run(app.run_once())
    elif choice == "2":
        print("\n▶️ Starting continuous mode...\n")
        asyncio.run(app.continuous())
    else:
        print("❌ Invalid choice!")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
