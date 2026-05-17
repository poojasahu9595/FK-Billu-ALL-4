"""
Enhanced Scraper with INFINITE SCROLL/PAGINATION Support

Features:
- Continues scraping until no more products
- Detects pagination automatically
- Supports infinite scroll pattern
- Configurable max pages limit
"""

import asyncio, uuid, random, time, json as std_json, platform, os
from typing import List, Dict, Optional
from datetime import datetime

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

from config import USER_AGENTS, SCRAPER_CONFIG


class InfiniteScrollScraper:
    """
    Enhanced scraper with infinite scroll/pagination support
    """
    
    def __init__(self):
        self.session_file = "data/session_data.json"
        self.dc_id = "1"
        
        if self._load_existing_session():
            print(f"✓ Session loaded (DC:{self.dc_id})")
        else:
            self.device_id = "4cd8968d962c7d6c2ae9dffef00eba76"
            self.tokens = {}
        
        self.base_url = f"https://{self.dc_id}.rome.api.flipkart.net"
        self.user_agents = USER_AGENTS.copy()
        random.shuffle(self.user_agents)
        self.ua_index = 0
        self.stats = {'requests': 0, 'products': 0, 'pages': 0, 'errors': 0}
        
        # ✅ NEW: Infinite scroll settings
        self.max_pages = SCRAPER_CONFIG.get('max_pages_per_url', 20)  # Increased default
        self.enable_infinite_scroll = SCRAPER_CONFIG.get('enable_infinite_scroll', True)
        self.min_products_per_page = SCRAPER_CONFIG.get('min_products_per_page', 5)
        
        print(f"📜 Scroll Mode: {'INFINITE' if self.enable_infinite_scroll else f'LIMITED ({self.max_pages} pages)'}")
    
    def _load_existing_session(self):
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file) as f:
                    d = std_json.load(f)
                    self.tokens = d.get('tokens', {})
                    self.device_id = d.get('device_id', '')
                    self.dc_id = d.get('dc_id', '1')
                    return bool(self.tokens.get('at'))
        except:
            pass
        return False
    
    def _save_session(self):
        try:
            os.makedirs("data", exist_ok=True)
            with open(self.session_file, 'w') as f:
                std_json.dump({
                    "tokens": self.tokens,
                    "device_id": self.device_id,
                    "dc_id": self.dc_id,
                    "timestamp": time.time()
                }, f, indent=2)
        except:
            pass
    
    def _headers(self):
        trace_id = str(uuid.uuid4()).replace('-', '')
        span_id = trace_id[:16]
        ts = int(time.time() * 1000)
        h = {
            'User-Agent': 'okhttp/4.9.3',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'Content-Type': 'application/json; charset=UTF-8',
            'Host': f'{self.dc_id}.rome.api.flipkart.net',
            'traceparent': f'00-{trace_id}-{span_id}-00',
            'tracestate': f'@nr=0-2---{span_id}----{ts}',
            'newrelic': std_json.dumps({
                "v": [0, 2],
                "d": {
                    "ty": "Mobile",
                    "ac": "",
                    "ap": "",
                    "tr": trace_id,
                    "id": span_id,
                    "ti": ts
                }
            }),
            'X-AR-AVAILABILITY': 'NOT_PRESENT',
            'x-atlas-versions': '10401000/1810000',
            'Network-Type': 'wifi',
            'X-DLS': 'true',
            'X-User-Agent': f'Mozilla/5.0 (Linux; Android 13; LEX821 Build/TQ3C.250905.001.C2) FKUA/Retail/1810000/Android/Mobile (LeEco/LEX821/{self.device_id})',
            'X-Layout-Version': '{"appVersion":"910000","frameworkVersion":"1.0"}'
        }
        if self.tokens.get('at'):
            h['at'] = self.tokens['at']
        if self.tokens.get('sn'):
            h['sn'] = self.tokens['sn']
        return h
    
    def _dumps(self, data):
        return orjson.dumps(data) if HAS_ORJSON else std_json.dumps(data).encode()
    
    def _loads(self, data):
        return orjson.loads(data) if HAS_ORJSON else std_json.loads(data)
    
    async def _get_dc(self, client):
        try:
            r = await client.post(
                "https://rome.api.flipkart.net/4/register/app",
                json={
                    "timestamp": int(time.time()),
                    "referral": "",
                    "isAppUpdated": False,
                    "isOSUpdated": False,
                    "isFirstLaunch": True,
                    "installId": str(uuid.uuid4()).replace('-', ''),
                    "iemi": None,
                    "macAddress": "02:00:00:00:00:00",
                    "prip": "fe80::d32b:43a4:6e67:13fd%rmnet_data0",
                    "securityPatchInfo": "2025-09-05",
                    "locale": None,
                    "deviceLanguage": "en"
                },
                headers={
                    'Host': 'rome.api.flipkart.net',
                    'User-Agent': 'okhttp/4.9.3',
                    'Content-Type': 'application/json; charset=UTF-8',
                    'X-User-Agent': f'Mozilla/5.0 (Linux; Android 13; LEX821) FKUA/Retail/1810000/Android/Mobile (LeEco/LEX821/{self.device_id})',
                    'X-Visit-Id': f'{self.device_id}-{int(time.time()*1000)}',
                    'checksum': 'eba600bf75c255d672efb2eded37cf1c'
                },
                timeout=30
            )
            if r.status_code == 406:
                return r.json().get('RESPONSE', {}).get('id', '1')
        except:
            pass
        return '1'
    
    async def _session(self, client):
        try:
            self.dc_id = await self._get_dc(client)
            self.base_url = f"https://{self.dc_id}.rome.api.flipkart.net"
            
            p = {
                "pageUri": "/",
                "pageContext": {
                    "pageHashKey": None,
                    "slotContextMap": None,
                    "paginationContextMap": None,
                    "paginatedFetch": False,
                    "pageNumber": 1,
                    "fetchAllPages": False,
                    "networkSpeed": 384,
                    "trackingContext": {"context": {"eVar51": "rich_carousel_neo/merchandising_clp"}},
                    "fetchSeoData": False
                },
                "partnerContext": None,
                "locationContext": None,
                "requestContext": {
                    "type": "BROWSE_PAGE",
                    "ssid": str(uuid.uuid4()),
                    "sqid": str(uuid.uuid4())
                }
            }
            
            r = await client.post(
                f"{self.base_url}/api/4/page/fetch",
                json=p,
                headers=self._headers(),
                timeout=30
            )
            
            at = r.headers.get('at') or r.headers.get('AT')
            sn = r.headers.get('sn') or r.headers.get('SN')
            
            if not at:
                try:
                    d = r.json()
                    if 'SESSION' in d:
                        at = d['SESSION'].get('at')
                        sn = d['SESSION'].get('sn')
                except:
                    pass
            
            if at:
                self.tokens['at'] = at
                if sn:
                    self.tokens['sn'] = sn
                self._save_session()
                return True
        except:
            pass
        return False
    
    async def _page(self, client, uri, num=1):
        try:
            p = {
                "pageUri": uri,
                "pageContext": {
                    "pageHashKey": None,
                    "slotContextMap": None,
                    "paginationContextMap": None,
                    "paginatedFetch": False,
                    "pageNumber": num,
                    "fetchAllPages": False,
                    "networkSpeed": 384,
                    "trackingContext": {"context": {"eVar51": "rich_carousel_neo"}},
                    "fetchSeoData": False
                },
                "partnerContext": None,
                "locationContext": None,
                "requestContext": {
                    "type": "BROWSE_PAGE",
                    "ssid": str(uuid.uuid4()),
                    "sqid": str(uuid.uuid4())
                }
            }
            
            r = await client.post(
                f"{self.base_url}/api/4/page/fetch",
                json=p,
                headers=self._headers(),
                timeout=15
            )
            self.stats['requests'] += 1
            
            if r.status_code == 200:
                d = self._loads(r.content)
                prods = self._extract(d)
                self.stats['pages'] += 1
                self.stats['products'] += len(prods)
                return prods
            elif r.status_code in [406, 401]:
                await self._session(client)
                await asyncio.sleep(2)
                return await self._page(client, uri, num)
            else:
                self.stats['errors'] += 1
                return []
        except:
            self.stats['errors'] += 1
            return []
    
    def _extract(self, data):
        prods = []
        seen = set()
        
        def search(o, d=0):
            if d > 20:
                return
            if isinstance(o, dict):
                if ('productMeta' in o and 'pricing' in o) or ('productId' in o and 'pricing' in o):
                    p = self._product(o)
                    if p and p['product_id'] not in seen:
                        seen.add(p['product_id'])
                        prods.append(p)
                for v in o.values():
                    search(v, d + 1)
            elif isinstance(o, list):
                for i in o:
                    search(i, d + 1)
        
        search(data)
        return prods
    
    def _product(self, data):
        try:
            t = data.get('titles', {})
            pr = data.get('pricing', {})
            m = data.get('productMeta', {})
            pid = m.get('productId') or data.get('productId') or ''
            if not pid or len(str(pid)) < 5:
                return None
            title = t.get('newTitle') or t.get('title') or 'Unknown'
            brand = t.get('superTitle', '')
            price = str(pr.get('displayPrice', '')).replace('₹', '').replace(',', '').strip()
            mrp = str(pr.get('strikeOffPrice', price)).replace('₹', '').replace(',', '').strip()
            disc = str(pr.get('discountPercentage', '0'))
            if disc == '0' and price and mrp:
                try:
                    c = float(price)
                    mm = float(mrp)
                    if mm > c > 0:
                        disc = str(round((mm - c) / mm * 100))
                except:
                    pass
            return {
                'product_id': str(pid),
                'listing_id': m.get('listingId', ''),
                'brand': str(brand),
                'title': str(title)[:200],
                'current_price': price,
                'original_price': mrp,
                'discount': disc,
                'url': f"https://www.flipkart.com/product/p/{pid}?pid={pid}",
                'scraped_at': datetime.now().isoformat()
            }
        except:
            return None
    
    def _uri(self, url):
        uri = url.replace('https://www.flipkart.com', '').replace('http://www.flipkart.com', '')
        return uri if uri.startswith('/') else '/' + uri
    
    async def scrape_url_infinite(self, url):
        """
        ✅ NEW: Scrape with infinite scroll support
        Continues until no more products or max_pages reached
        """
        uri = self._uri(url)
        all_prods = []
        consecutive_empty = 0
        page = 1
        
        print(f"   📜 Starting infinite scroll for: {uri[:50]}...")
        
        if HAS_CURL:
            async with AsyncSession(impersonate="chrome110") as client:
                if not self.tokens.get('at'):
                    await self._session(client)
                
                while True:
                    # Fetch page
                    prods = await self._page(client, uri, page)
                    
                    if prods:
                        print(f"      Page {page}: {len(prods)} products")
                        all_prods.extend(prods)
                        consecutive_empty = 0
                        
                        # ✅ Check stopping conditions
                        if not self.enable_infinite_scroll and page >= self.max_pages:
                            print(f"      ⏸️ Reached max pages limit ({self.max_pages})")
                            break
                        
                        # Small delay between pages
                        delay = random.uniform(*SCRAPER_CONFIG.get('delay_between_pages', (1, 2)))
                        await asyncio.sleep(delay)
                        page += 1
                    else:
                        consecutive_empty += 1
                        print(f"      Page {page}: 0 products (empty #{consecutive_empty})")
                        
                        # ✅ Stop if multiple consecutive empty pages
                        if consecutive_empty >= 2:
                            print(f"      🛑 No more products found (2 consecutive empty pages)")
                            break
                        
                        # Try one more page
                        page += 1
                        if page > self.max_pages:
                            print(f"      🛑 Reached max pages ({self.max_pages})")
                            break
        else:
            # Same logic with httpx
            async with httpx.AsyncClient(
                http2=True,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
                timeout=30
            ) as client:
                if not self.tokens.get('at'):
                    await self._session(client)
                
                while True:
                    prods = await self._page(client, uri, page)
                    
                    if prods:
                        print(f"      Page {page}: {len(prods)} products")
                        all_prods.extend(prods)
                        consecutive_empty = 0
                        
                        if not self.enable_infinite_scroll and page >= self.max_pages:
                            print(f"      ⏸️ Reached max pages limit ({self.max_pages})")
                            break
                        
                        delay = random.uniform(*SCRAPER_CONFIG.get('delay_between_pages', (1, 2)))
                        await asyncio.sleep(delay)
                        page += 1
                    else:
                        consecutive_empty += 1
                        print(f"      Page {page}: 0 products (empty #{consecutive_empty})")
                        
                        if consecutive_empty >= 2:
                            print(f"      🛑 No more products found")
                            break
                        
                        page += 1
                        if page > self.max_pages:
                            print(f"      🛑 Reached max pages ({self.max_pages})")
                            break
        
        print(f"   ✅ Scraped {len(all_prods)} total products from {page-1} pages")
        return all_prods
    
    async def scrape_url(self, url):
        """Main scrape method - uses infinite scroll if enabled"""
        if self.enable_infinite_scroll:
            return await self.scrape_url_infinite(url)
        else:
            # Fallback to limited pagination (original method)
            return await self._scrape_url_limited(url)
    
    async def _scrape_url_limited(self, url):
        """Original limited pagination method"""
        uri = self._uri(url)
        all_prods = []
        
        if HAS_CURL:
            async with AsyncSession(impersonate="chrome110") as client:
                if not self.tokens.get('at'):
                    await self._session(client)
                for page in range(1, self.max_pages + 1):
                    prods = await self._page(client, uri, page)
                    if prods:
                        all_prods.extend(prods)
                        if page < self.max_pages:
                            await asyncio.sleep(random.uniform(1, 2))
                    else:
                        break
        else:
            async with httpx.AsyncClient(
                http2=True,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
                timeout=30
            ) as client:
                if not self.tokens.get('at'):
                    await self._session(client)
                for page in range(1, self.max_pages + 1):
                    prods = await self._page(client, uri, page)
                    if prods:
                        all_prods.extend(prods)
                        if page < self.max_pages:
                            await asyncio.sleep(random.uniform(1, 2))
                    else:
                        break
        
        return all_prods
    
    async def scrape_urls(self, urls):
        tasks = [self.scrape_url(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_prods = []
        for r in results:
            if isinstance(r, list):
                all_prods.extend(r)
        return all_prods
    
    def get_stats(self):
        return self.stats.copy()


# Alias for backward compatibility
Scraper = InfiniteScrollScraper