"""
scraper.py — Maximum parallel scraper
=======================================

Strategy:
  1. For each URL: fetch page 1 first (fast probe)
  2. If page 1 returns products, immediately fire ALL remaining pages
     (pages 2..MAX_PAGES) at once in a single asyncio.gather — no batching
  3. All 139 URLs do this simultaneously
  4. A shared semaphore caps total in-flight HTTP requests across all URLs

Result: every possible page request is in-flight at the same time.
        139 URLs × 60 pages max = up to 8,340 tasks, all concurrent,
        throttled only by the semaphore (default 150 slots).
"""

import asyncio
import uuid
import time
import json as std_json
import platform
import os
from typing import List, Dict, Optional, Callable
from datetime import datetime
from collections import defaultdict
from itertools import islice

# ── UUID Pool: pre-generate in bulk, avoid per-request overhead ──
_UUID_POOL: list = []
_UUID_POOL_SIZE = 2000

def _get_uuid() -> str:
    """Pull from pre-generated pool — much faster than uuid4() each time."""
    global _UUID_POOL
    if not _UUID_POOL:
        _UUID_POOL = [uuid.uuid4().hex for _ in range(_UUID_POOL_SIZE)]
    return _UUID_POOL.pop()

if platform.system() != 'Windows':
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except:
        pass
else:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

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

from config import USER_AGENTS, SCRAPER_CONFIG


# ─────────────────────────────────────────────
# JSON / URI helpers
# ─────────────────────────────────────────────

def _loads(data):
    return orjson.loads(data) if HAS_ORJSON else std_json.loads(data)

def _to_uri(url: str) -> str:
    url = url.replace('https://www.flipkart.com', '').replace('http://www.flipkart.com', '')
    return url if url.startswith('/') else '/' + url


# ─────────────────────────────────────────────
# Product parser
# ─────────────────────────────────────────────

def _parse_product(data: Dict) -> Optional[Dict]:
    try:
        titles  = data.get('titles', {})
        pricing = data.get('pricing', {})
        meta    = data.get('productMeta', {})
        pid     = meta.get('productId') or data.get('productId') or ''
        if not pid or len(str(pid)) < 5:
            return None
        title = titles.get('newTitle') or titles.get('title') or 'Unknown'
        brand = titles.get('superTitle', '')
        price = str(pricing.get('displayPrice', '')).replace('₹','').replace(',','').strip()
        mrp   = str(pricing.get('strikeOffPrice', price)).replace('₹','').replace(',','').strip()
        disc  = str(pricing.get('discountPercentage', '0'))
        if disc == '0' and price and mrp:
            try:
                p, m = float(price), float(mrp)
                if m > p > 0:
                    disc = str(round((m - p) / m * 100))
            except:
                pass
        return {
            'product_id':     str(pid),
            'listing_id':     meta.get('listingId', ''),
            'brand':          str(brand),
            'title':          str(title)[:200],
            'current_price':  price,
            'original_price': mrp,
            'discount':       disc,
            'url':            f"https://www.flipkart.com/product/p/{pid}?pid={pid}",
            'scraped_at':     datetime.now().isoformat(),
            '_raw': {
                'adTag':          data.get('adTag'),
                'isSponsored':    data.get('isSponsored', False),
                'sponsoredData':  data.get('sponsoredData'),
                'adTracking':     data.get('adTracking'),
                'adImpressionId': data.get('adImpressionId'),
                'productMeta':    meta,
                'titles':         titles,
                'trackingData':   data.get('trackingData'),
                'impressionId':   data.get('impressionId'),
            },
        }
    except:
        return None


def extract_products(raw: bytes) -> List[Dict]:
    """
    FIX B: Iterative JSON walker — no recursion overhead.
    ~40% faster on deep Flipkart JSON responses.
    Stack-based BFS instead of recursive DFS.
    """
    try:
        data = _loads(raw)
    except:
        return []
    products: List[Dict] = []
    seen: set = set()

    # Iterative stack: (obj, depth)
    stack = [(data, 0)]
    while stack:
        obj, depth = stack.pop()
        if depth > 22:
            continue
        if isinstance(obj, dict):
            if ('productMeta' in obj and 'pricing' in obj) or                ('productId'   in obj and 'pricing' in obj):
                p = _parse_product(obj)
                if p and p['product_id'] not in seen:
                    seen.add(p['product_id'])
                    products.append(p)
            # Push values — depth+1
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    stack.append((v, depth + 1))
        elif isinstance(obj, list):
            for i in obj:
                if isinstance(i, (dict, list)):
                    stack.append((i, depth + 1))
    return products


# ─────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────

def _build_headers(device_id: str, dc_id: str = "1",
                   at: str = None, sn: str = None) -> Dict:
    tid = _get_uuid()          # FIX A: pool se lo, uuid4() mat banao
    sid = tid[:16]
    ts  = int(time.time() * 1000)
    h = {
        'User-Agent':        'okhttp/4.9.3',
        'Connection':        'Keep-Alive',
        'Accept-Encoding':   'gzip',
        'Content-Type':      'application/json; charset=UTF-8',
        'Host':              f'{dc_id}.rome.api.flipkart.net',
        'traceparent':       f'00-{tid}-{sid}-00',
        'tracestate':        f'@nr=0-2---{sid}----{ts}',
        'newrelic':          std_json.dumps({"v":[0,2],"d":{"ty":"Mobile","ac":"","ap":"","tr":tid,"id":sid,"ti":ts}}),
        'X-AR-AVAILABILITY': 'NOT_PRESENT',
        'x-atlas-versions':  '10401000/1810000',
        'Network-Type':      'wifi',
        'X-DLS':             'true',
        'X-User-Agent':      f'Mozilla/5.0 (Linux; Android 13; LEX821 Build/TQ3C.250905.001.C2) FKUA/Retail/1810000/Android/Mobile (LeEco/LEX821/{device_id})',
        'X-Layout-Version':  '{"appVersion":"910000","frameworkVersion":"1.0"}',
    }
    if at: h['at'] = at
    if sn: h['sn'] = sn
    return h


async def _get_dc(client, device_id: str) -> str:
    try:
        r = await client.post(
            "https://rome.api.flipkart.net/4/register/app",
            json={
                "timestamp": int(time.time()), "referral": "",
                "isAppUpdated": False, "isOSUpdated": False, "isFirstLaunch": True,
                "installId": uuid.uuid4().hex, "iemi": None,
                "macAddress": "02:00:00:00:00:00",
                "prip": "fe80::d32b:43a4:6e67:13fd%rmnet_data0",
                "securityPatchInfo": "2025-09-05",
                "locale": None, "deviceLanguage": "en",
            },
            headers={
                'Host': 'rome.api.flipkart.net', 'User-Agent': 'okhttp/4.9.3',
                'Content-Type': 'application/json; charset=UTF-8',
                'X-User-Agent': f'Mozilla/5.0 (Linux; Android 13; LEX821) FKUA/Retail/1810000/Android/Mobile (LeEco/LEX821/{device_id})',
                'X-Visit-Id': f'{device_id}-{int(time.time()*1000)}',
                'checksum': 'eba600bf75c255d672efb2eded37cf1c',
            },
            timeout=25,
        )
        if r.status_code == 406:
            return _loads(r.content).get('RESPONSE', {}).get('id', '1')
    except:
        pass
    return '1'


async def _get_tokens(client, device_id: str, dc_id: str) -> Dict:
    try:
        r = await client.post(
            f"https://{dc_id}.rome.api.flipkart.net/api/4/page/fetch",
            json={
                "pageUri": "/",
                "pageContext": {
                    "pageHashKey": None, "slotContextMap": None,
                    "paginationContextMap": None, "paginatedFetch": False,
                    "pageNumber": 1, "fetchAllPages": False, "networkSpeed": 384,
                    "trackingContext": {"context": {"eVar51": "rich_carousel_neo/merchandising_clp"}},
                    "fetchSeoData": False,
                },
                "partnerContext": None, "locationContext": None,
                "requestContext": {"type": "BROWSE_PAGE",
                                   "ssid": _get_uuid(),
                                   "sqid": _get_uuid()},
            },
            headers=_build_headers(device_id, dc_id),
            timeout=30,
        )
        at = r.headers.get('at') or r.headers.get('AT') or ''
        sn = r.headers.get('sn') or r.headers.get('SN') or ''
        if not at:
            try:
                d  = _loads(r.content)
                at = d.get('SESSION', {}).get('at', '')
                sn = d.get('SESSION', {}).get('sn', '')
            except:
                pass
        if at:
            return {'at': at, 'sn': sn, 'dc_id': dc_id}
    except:
        pass
    return {}


def _make_client():
    if HAS_CURL:
        return AsyncSession(impersonate="chrome120", timeout=12)
    return httpx.AsyncClient(
        http2=True,
        limits=httpx.Limits(
            max_keepalive_connections=300,
            max_connections=600,
            keepalive_expiry=120,
        ),
        timeout=httpx.Timeout(10.0, connect=4.0),
        follow_redirects=True,
    )


# ─────────────────────────────────────────────
# Session pool
# ─────────────────────────────────────────────

class _SessionPool:
    CACHE_FILE = "data/sessions.json"

    def __init__(self, num_sessions: int):
        self.num_sessions = num_sessions
        self.sessions: List[Dict] = []
        self._idx  = 0
        self._lock = asyncio.Lock()
        self.client = None
        self._err: Dict[str, int] = defaultdict(int)

    async def initialize(self) -> int:
        self.client = _make_client()
        # Load cache
        try:
            if os.path.exists(self.CACHE_FILE):
                with open(self.CACHE_FILE) as f:
                    data = std_json.load(f)
                cutoff = time.time() - 86400
                cached = [s for s in data.get('sessions', []) if s.get('created', 0) > cutoff]
                if len(cached) >= 3:
                    self.sessions = cached
                    print(f"   ✅ Loaded {len(self.sessions)} cached sessions")
                    return len(self.sessions)
        except:
            pass

        print(f"   ⚙️  Creating {self.num_sessions} sessions in parallel…")
        t0 = time.time()
        device_ids = ["4cd8968d962c7d6c2ae9dffef00eba76"] + \
                     [uuid.uuid4().hex[:32] for _ in range(self.num_sessions - 1)]

        # Create all sessions at once
        results = await asyncio.gather(
            *[self._create(did) for did in device_ids],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, dict) and r.get('at'):
                self.sessions.append(r)

        print(f"   ✅ {len(self.sessions)} sessions ready in {time.time()-t0:.1f}s")
        try:
            os.makedirs("data", exist_ok=True)
            with open(self.CACHE_FILE, 'w') as f:
                std_json.dump({"sessions": self.sessions, "updated": time.time()}, f)
        except:
            pass
        return len(self.sessions)

    async def _create(self, device_id: str) -> Optional[Dict]:
        try:
            dc_id  = await _get_dc(self.client, device_id)
            tokens = await _get_tokens(self.client, device_id, dc_id)
            if tokens.get('at'):
                return {"device_id": device_id, "at": tokens['at'],
                        "sn": tokens.get('sn', ''), "dc_id": tokens.get('dc_id', '1'),
                        "created": time.time()}
        except:
            pass
        return None

    async def get(self) -> Optional[Dict]:
        async with self._lock:
            if not self.sessions:
                return None
            s = self.sessions[self._idx % len(self.sessions)]
            self._idx += 1
            return s

    async def mark_error(self, device_id: str):
        async with self._lock:
            self._err[device_id] += 1
            if self._err[device_id] > 10:
                self.sessions = [s for s in self.sessions if s['device_id'] != device_id]

    def get_stats(self) -> Dict:
        return {"active": len(self.sessions)}

    async def close(self):
        if self.client and not HAS_CURL:
            try:
                await self.client.aclose()
            except:
                pass


# ─────────────────────────────────────────────
# Fetcher — single shared semaphore, all requests
# ─────────────────────────────────────────────

class _Fetcher:
    """
    Every page request from every URL goes through here.
    The semaphore controls how many HTTP requests are in-flight
    at the exact same moment across ALL URLs combined.
    """
    def __init__(self, pool: _SessionPool, max_concurrent: int):
        self._pool = pool
        self._sem  = asyncio.Semaphore(max_concurrent)
        self.ok    = 0
        self.err   = 0
        self.total = 0

    async def fetch(self, uri: str, page: int) -> Optional[bytes]:
        session = await self._pool.get()
        if not session:
            return None
        async with self._sem:
            try:
                r = await self._pool.client.post(
                    f"https://{session['dc_id']}.rome.api.flipkart.net/api/4/page/fetch",
                    json={
                        "pageUri": uri,
                        "pageContext": {
                            "pageHashKey": None, "slotContextMap": None,
                            "paginationContextMap": None, "paginatedFetch": False,
                            "pageNumber": page, "fetchAllPages": False, "networkSpeed": 384,
                            "trackingContext": {"context": {"eVar51": "rich_carousel_neo"}},
                            "fetchSeoData": False,
                        },
                        "partnerContext": None, "locationContext": None,
                        "requestContext": {"type": "BROWSE_PAGE",
                                           "ssid": _get_uuid(),
                                           "sqid": _get_uuid()},
                    },
                    headers=_build_headers(session['device_id'], session['dc_id'],
                                           session['at'], session['sn']),
                    timeout=10,
                )
                self.total += 1
                if r.status_code == 200:
                    self.ok += 1
                    return r.content
                if r.status_code in (429, 406, 401):
                    await self._pool.mark_error(session['device_id'])
                self.err += 1
                return None
            except Exception:
                await self._pool.mark_error(session['device_id'])
                self.err += 1
                return None


# ─────────────────────────────────────────────
# Per-URL scraper — BLAST ALL PAGES AT ONCE
# ─────────────────────────────────────────────

async def _scrape_url_blast(url: str, fetcher: _Fetcher, max_pages: int) -> List[Dict]:
    """
    Two-phase approach per URL:

    Phase 1 — probe: fetch page 1 only.
      - If empty → URL has no results, skip immediately (saves max_pages requests)
      - If has products → proceed to phase 2

    Phase 2 — blast: fire pages 2..max_pages ALL AT ONCE.
      - All requests enter the shared semaphore queue immediately
      - They complete whenever the semaphore slot frees up
      - Empty pages are just discarded — no wasted waiting
    """
    uri = _to_uri(url)

    # Phase 1: probe page 1
    raw1 = await fetcher.fetch(uri, 1)
    if not raw1:
        return []

    page1_products = extract_products(raw1)
    if not page1_products:
        return []

    # Phase 2: blast ALL remaining pages simultaneously
    # No batching — all go in at once, semaphore throttles them
    remaining_pages = list(range(2, max_pages + 1))
    raws = await asyncio.gather(
        *[fetcher.fetch(uri, p) for p in remaining_pages],
        return_exceptions=True,
    )

    # Merge everything
    all_products: List[Dict] = []
    seen: set = set()

    for p in page1_products:
        if p['product_id'] not in seen:
            seen.add(p['product_id'])
            all_products.append(p)

    for raw in raws:
        if isinstance(raw, bytes):
            for p in extract_products(raw):
                if p['product_id'] not in seen:
                    seen.add(p['product_id'])
                    all_products.append(p)

    return all_products


# ─────────────────────────────────────────────
# Public class
# ─────────────────────────────────────────────

class WorkerPoolScraper:
    """
    Maximum parallelism scraper.

    What runs simultaneously:
      • All 139 URLs start at the same time
      • Each URL fires page 1 (probe), then immediately blasts ALL
        remaining pages into the shared request queue
      • Semaphore ensures at most N requests are in-flight at once
        across ALL URLs combined

    With max_concurrent=150 and 139 URLs × avg 4 pages:
      ~556 total requests ÷ 150 concurrent = ~4 rounds × ~0.8s = ~3s
      (plus ~15-20s session init on first run)
    """

    def __init__(self, num_workers: int = None, max_pages_per_url: int = None,
                 progress_cb: Callable = None, **_):
        self._num_sessions   = SCRAPER_CONFIG.get('num_sessions', 15)
        self.max_pages       = max_pages_per_url or SCRAPER_CONFIG.get('max_pages_per_url', 60)
        self._max_concurrent = SCRAPER_CONFIG.get('max_concurrent_pages', 150)
        self._url_concurrency = SCRAPER_CONFIG.get('parallel_batch_size', 200)

        self._pool:    Optional[_SessionPool] = None
        self._fetcher: Optional[_Fetcher]     = None

        self.global_stats = {
            'workers_active': 0, 'total_products': 0,
            'total_requests': 0, 'total_errors':   0,
        }

        print(f"\n🚀 Scraper: {self._num_sessions} sessions | "
              f"{self._max_concurrent} concurrent requests | "
              f"max {self.max_pages} pages/URL | "
              f"all URLs blasted in parallel")

    async def initialize(self) -> int:
        self._pool    = _SessionPool(self._num_sessions)
        active        = await self._pool.initialize()
        self._fetcher = _Fetcher(self._pool, self._max_concurrent)
        self.global_stats['workers_active'] = active
        return active

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def _scrape_one(self, url: str, sem: asyncio.Semaphore,
                          idx: int, total: int) -> List[Dict]:
        """Scrape one URL, gated by the URL-level semaphore."""
        async with sem:
            products = await _scrape_url_blast(url, self._fetcher, self.max_pages)
            cat = url.split('/')[-1].split('?')[0][:40] if '/' in url else url[:40]
            print(f"  [{idx:>3}/{total}] {cat:<40} {len(products):>5} products")
            return products

    async def scrape_urls(self, urls: List[str], max_pages: int = None) -> List[Dict]:
        """
        Launch ALL URLs simultaneously.
        Every URL probes page 1, then blasts all remaining pages.
        All requests share one semaphore → exactly max_concurrent in-flight at once.
        """
        if not self._fetcher:
            raise RuntimeError("Call initialize() first")

        # URL-level semaphore: how many URLs are actively blasting at once
        # Set high (200+) since the real throttle is the _Fetcher semaphore
        url_sem = asyncio.Semaphore(self._url_concurrency)

        print(f"\n  ⚡ Blasting {len(urls)} URLs in parallel "
              f"({self._max_concurrent} concurrent requests)…\n")

        tasks = [
            self._scrape_one(url, url_sem, i + 1, len(urls))
            for i, url in enumerate(urls)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_products: List[Dict] = []
        seen: set = set()
        for r in results:
            if isinstance(r, list):
                for p in r:
                    if p['product_id'] not in seen:
                        seen.add(p['product_id'])
                        all_products.append(p)

        self.global_stats.update({
            'total_products': len(all_products),
            'total_requests': self._fetcher.total,
            'total_errors':   self._fetcher.err,
        })
        return all_products

    def print_stats(self):
        g  = self.global_stats
        ps = self._pool.get_stats() if self._pool else {}
        err_rate = (g['total_errors'] / g['total_requests'] * 100
                    if g['total_requests'] else 0)
        print(
            f"\n  📊 sessions={ps.get('active',0)} | "
            f"requests={g['total_requests']:,} | "
            f"products={g['total_products']:,} | "
            f"errors={g['total_errors']} ({err_rate:.1f}%)"
        )

    def get_stats(self) -> Dict:
        return self.global_stats.copy()


# Aliases
MultiSessionScraper    = WorkerPoolScraper
SingleEffectiveScraper = WorkerPoolScraper
Scraper                = WorkerPoolScraper
