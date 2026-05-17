"""
MULTI-SESSION Scraper with Session Rotation
=============================================
Uses 10-15 different sessions (AT/SN tokens) to distribute load
and avoid rate limiting from Flipkart

Key features:
1. Multiple device IDs and sessions
2. Automatic session rotation
3. Round-robin distribution
4. Session health monitoring
5. Auto-regenerate dead sessions
"""

import asyncio
import uuid
import random
import time
import json as std_json
import platform
import os
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
from collections import defaultdict

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


class SessionManager:
    """
    Manages multiple sessions (device_id, at, sn tokens)
    Rotates between them to avoid rate limiting
    """
    
    def __init__(self, num_sessions: int = 15):
        self.num_sessions = num_sessions
        self.sessions = []
        self.current_index = 0
        self.session_stats = defaultdict(lambda: {"requests": 0, "errors": 0, "last_used": 0})
        self.lock = asyncio.Lock()
        
        # Generate multiple device IDs
        self.device_ids = [
            "4cd8968d962c7d6c2ae9dffef00eba76",  # Original working one
        ]
        
        # Generate additional device IDs
        for _ in range(num_sessions - 1):
            device_id = str(uuid.uuid4()).replace('-', '')[:32]
            self.device_ids.append(device_id)
        
        print(f"🔐 Session Manager initialized with {num_sessions} sessions")
    
    def _load_sessions(self, session_file: str = "data/sessions.json") -> bool:
        """Load multiple sessions from file"""
        try:
            if os.path.exists(session_file):
                with open(session_file) as f:
                    data = std_json.load(f)
                    self.sessions = data.get('sessions', [])
                    if len(self.sessions) >= 3:  # At least 3 valid sessions
                        print(f"   ✓ Loaded {len(self.sessions)} sessions from cache")
                        return True
        except:
            pass
        return False
    
    def _save_sessions(self, session_file: str = "data/sessions.json"):
        """Save all sessions to file"""
        try:
            os.makedirs("data", exist_ok=True)
            with open(session_file, 'w') as f:
                std_json.dump({
                    "sessions": self.sessions,
                    "timestamp": time.time()
                }, f, indent=2)
        except:
            pass
    
    async def initialize_sessions(self, client, base_url: str, get_session_func):
        """Initialize all sessions"""
        if self._load_sessions():
            return True
        
        print(f"   🔄 Generating {self.num_sessions} new sessions...")
        
        # Generate sessions concurrently (in batches to avoid overwhelming)
        batch_size = 5
        for i in range(0, self.num_sessions, batch_size):
            batch = self.device_ids[i:i+batch_size]
            tasks = [
                self._create_session(client, device_id, base_url, get_session_func)
                for device_id in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, dict):
                    self.sessions.append(result)
            
            # Small delay between batches
            if i + batch_size < self.num_sessions:
                await asyncio.sleep(2)
        
        print(f"   ✓ Generated {len(self.sessions)} sessions successfully")
        self._save_sessions()
        return len(self.sessions) > 0
    
    async def _create_session(self, client, device_id: str, base_url: str, get_session_func) -> Dict:
        """Create a single session"""
        try:
            tokens = await get_session_func(client, device_id)
            if tokens and tokens.get('at'):
                return {
                    "device_id": device_id,
                    "at": tokens['at'],
                    "sn": tokens.get('sn', ''),
                    "dc_id": tokens.get('dc_id', '1'),
                    "created_at": time.time()
                }
        except Exception as e:
            pass
        return None
    
    async def get_session(self) -> Dict:
        """Get next session in rotation"""
        async with self.lock:
            if not self.sessions:
                return None
            
            # Round-robin rotation
            session = self.sessions[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.sessions)
            
            # Update stats
            session_id = session['device_id']
            self.session_stats[session_id]["requests"] += 1
            self.session_stats[session_id]["last_used"] = time.time()
            
            return session
    
    async def mark_session_error(self, device_id: str):
        """Mark a session as having an error"""
        async with self.lock:
            self.session_stats[device_id]["errors"] += 1
            
            # If too many errors, remove from rotation
            if self.session_stats[device_id]["errors"] > 10:
                self.sessions = [s for s in self.sessions if s['device_id'] != device_id]
                print(f"   ⚠️ Removed session {device_id[:16]}... (too many errors)")
    
    def get_stats(self) -> Dict:
        """Get session statistics"""
        total_requests = sum(s["requests"] for s in self.session_stats.values())
        total_errors = sum(s["errors"] for s in self.session_stats.values())
        
        return {
            "total_sessions": len(self.sessions),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "requests_per_session": total_requests / len(self.sessions) if self.sessions else 0,
            "error_rate": total_errors / total_requests if total_requests > 0 else 0
        }


class MultiSessionScraper:
    """
    Scraper that uses multiple sessions to avoid rate limiting
    """
    
    def __init__(self, num_sessions: int = 15):
        self.session_manager = SessionManager(num_sessions)
        
        # User agent pool (rotate these too)
        self.user_agents = USER_AGENTS.copy()
        random.shuffle(self.user_agents)
        self.ua_index = 0
        
        # Stats
        self.stats = {
            'requests': 0,
            'products': 0,
            'pages': 0,
            'errors': 0,
            'cache_hits': 0,
            'concurrent_requests': 0,
            'session_rotations': 0
        }
        
        # Configuration
        self.max_pages = SCRAPER_CONFIG.get('max_pages_per_url', 50)
        self.enable_infinite_scroll = SCRAPER_CONFIG.get('enable_infinite_scroll', True)
        self.min_products_per_page = SCRAPER_CONFIG.get('min_products_per_page', 5)
        
        # Connection pooling
        self.client = None
        self.client_lock = asyncio.Lock()
        
        # Response cache
        self.cache = {}
        self.cache_ttl = SCRAPER_CONFIG.get('cache_ttl', 600)
        
        # Concurrency
        max_concurrent = SCRAPER_CONFIG.get('max_concurrent_pages', 20)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        print(f"🚀 Multi-Session Scraper Initialized")
        print(f"   Sessions: {num_sessions}")
        print(f"   Max Concurrent: {max_concurrent}")
        print(f"   User Agents: {len(self.user_agents)}")
    
    async def initialize(self):
        """Initialize sessions"""
        client = await self._get_client()
        success = await self.session_manager.initialize_sessions(
            client, 
            "https://1.rome.api.flipkart.net",  # Base URL
            self._create_session_tokens
        )
        if not success:
            print("   ⚠️ Warning: Could not create all sessions, will continue with available ones")
        return success
    
    async def _create_session_tokens(self, client, device_id: str) -> Dict:
        """Create session tokens for a device"""
        try:
            # Get datacenter
            dc_id = await self._get_dc(client, device_id)
            base_url = f"https://{dc_id}.rome.api.flipkart.net"
            
            # Get tokens
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
            
            headers = self._headers_for_device(device_id)
            
            r = await client.post(
                f"{base_url}/api/4/page/fetch",
                json=p,
                headers=headers,
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
                return {
                    'at': at,
                    'sn': sn or '',
                    'dc_id': dc_id
                }
        except:
            pass
        return None
    
    def _get_next_user_agent(self) -> str:
        """Get next user agent in rotation"""
        ua = self.user_agents[self.ua_index]
        self.ua_index = (self.ua_index + 1) % len(self.user_agents)
        return ua
    
    def _headers_for_device(self, device_id: str, at: str = None, sn: str = None, dc_id: str = "1") -> Dict:
        """Generate headers for a specific device"""
        trace_id = str(uuid.uuid4()).replace('-', '')
        span_id = trace_id[:16]
        ts = int(time.time() * 1000)
        
        h = {
            'User-Agent': 'okhttp/4.9.3',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'Content-Type': 'application/json; charset=UTF-8',
            'Host': f'{dc_id}.rome.api.flipkart.net',
            'traceparent': f'00-{trace_id}-{span_id}-00',
            'tracestate': f'@nr=0-2---{span_id}----{ts}',
            'newrelic': std_json.dumps({
                "v": [0, 2],
                "d": {"ty": "Mobile", "ac": "", "ap": "", "tr": trace_id, "id": span_id, "ti": ts}
            }),
            'X-AR-AVAILABILITY': 'NOT_PRESENT',
            'x-atlas-versions': '10401000/1810000',
            'Network-Type': 'wifi',
            'X-DLS': 'true',
            'X-User-Agent': f'Mozilla/5.0 (Linux; Android 13; LEX821 Build/TQ3C.250905.001.C2) FKUA/Retail/1810000/Android/Mobile (LeEco/LEX821/{device_id})',
            'X-Layout-Version': '{"appVersion":"910000","frameworkVersion":"1.0"}'
        }
        
        if at:
            h['at'] = at
        if sn:
            h['sn'] = sn
        
        return h
    
    async def _get_client(self):
        """Get or create persistent HTTP client"""
        if self.client is None:
            async with self.client_lock:
                if self.client is None:
                    pool_size = SCRAPER_CONFIG.get('connection_pool_size', 100)
                    
                    if HAS_CURL:
                        self.client = AsyncSession(
                            impersonate="chrome110",
                            timeout=15
                        )
                    else:
                        self.client = httpx.AsyncClient(
                            http2=True,
                            limits=httpx.Limits(
                                max_keepalive_connections=pool_size,
                                max_connections=pool_size * 2,
                                keepalive_expiry=120
                            ),
                            timeout=httpx.Timeout(10.0, connect=3.0),
                            follow_redirects=True
                        )
        return self.client
    
    async def close(self):
        """Close the persistent client"""
        if self.client:
            try:
                if not HAS_CURL:
                    await self.client.aclose()
            except:
                pass
    
    async def _get_dc(self, client, device_id: str) -> str:
        """Get datacenter ID"""
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
                    'X-User-Agent': f'Mozilla/5.0 (Linux; Android 13; LEX821) FKUA/Retail/1810000/Android/Mobile (LeEco/LEX821/{device_id})',
                    'X-Visit-Id': f'{device_id}-{int(time.time()*1000)}',
                    'checksum': 'eba600bf75c255d672efb2eded37cf1c'
                },
                timeout=30
            )
            if r.status_code == 406:
                return r.json().get('RESPONSE', {}).get('id', '1')
        except:
            pass
        return '1'
    
    def _dumps(self, data):
        return orjson.dumps(data) if HAS_ORJSON else std_json.dumps(data).encode()
    
    def _loads(self, data):
        return orjson.loads(data) if HAS_ORJSON else std_json.loads(data)
    
    def _cache_key(self, uri: str, page: int) -> str:
        return f"{uri}:{page}"
    
    def _get_cached(self, uri: str, page: int) -> Optional[List[Dict]]:
        key = self._cache_key(uri, page)
        if key in self.cache:
            cached_time, data = self.cache[key]
            if time.time() - cached_time < self.cache_ttl:
                self.stats['cache_hits'] += 1
                return data
            else:
                del self.cache[key]
        return None
    
    def _set_cache(self, uri: str, page: int, data: List[Dict]):
        key = self._cache_key(uri, page)
        self.cache[key] = (time.time(), data)
    
    async def _page(self, client, uri: str, num: int = 1) -> List[Dict]:
        """Fetch page using rotated session"""
        # Check cache first
        cached = self._get_cached(uri, num)
        if cached is not None:
            return cached
        
        # Get session from rotation
        session = await self.session_manager.get_session()
        if not session:
            self.stats['errors'] += 1
            return []
        
        self.stats['session_rotations'] += 1
        
        try:
            async with self.semaphore:
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
                
                # Use session-specific headers
                headers = self._headers_for_device(
                    session['device_id'],
                    session['at'],
                    session['sn'],
                    session['dc_id']
                )
                
                base_url = f"https://{session['dc_id']}.rome.api.flipkart.net"
                
                r = await client.post(
                    f"{base_url}/api/4/page/fetch",
                    json=p,
                    headers=headers,
                    timeout=10
                )
                
                self.stats['requests'] += 1
                
                if r.status_code == 200:
                    d = self._loads(r.content)
                    prods = self._extract(d)
                    self.stats['pages'] += 1
                    self.stats['products'] += len(prods)
                    
                    # Cache result
                    self._set_cache(uri, num, prods)
                    
                    return prods
                elif r.status_code in [406, 401, 429]:
                    # Mark session as having an error
                    await self.session_manager.mark_session_error(session['device_id'])
                    self.stats['errors'] += 1
                    return []
                else:
                    self.stats['errors'] += 1
                    return []
        except Exception as e:
            await self.session_manager.mark_session_error(session['device_id'])
            self.stats['errors'] += 1
            return []
    
    def _extract(self, data):
        """Extract products from response"""
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
        """Extract product data"""
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
        """Convert URL to URI"""
        uri = url.replace('https://www.flipkart.com', '').replace('http://www.flipkart.com', '')
        return uri if uri.startswith('/') else '/' + uri
    
    async def scrape_url(self, url: str) -> List[Dict]:
        """Scrape URL with multi-session support"""
        uri = self._uri(url)
        all_prods = []
        
        client = await self._get_client()
        
        # Fetch first page
        first_page_prods = await self._page(client, uri, 1)
        
        if not first_page_prods:
            return []
        
        all_prods.extend(first_page_prods)
        
        # Fetch remaining pages concurrently
        if len(first_page_prods) >= self.min_products_per_page:
            batch_size = 10
            max_pages = self.max_pages if not self.enable_infinite_scroll else 50
            
            for batch_start in range(2, max_pages + 1, batch_size):
                batch_end = min(batch_start + batch_size, max_pages + 1)
                page_range = range(batch_start, batch_end)
                
                # Each concurrent request uses a different session!
                tasks = [self._page(client, uri, page) for page in page_range]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                self.stats['concurrent_requests'] += len(tasks)
                
                empty_count = 0
                for result in results:
                    if isinstance(result, list) and result:
                        all_prods.extend(result)
                    else:
                        empty_count += 1
                
                if empty_count == len(results):
                    break
                
                await asyncio.sleep(0.1)
        
        return all_prods
    
    def get_stats(self):
        """Get scraper statistics"""
        stats = self.stats.copy()
        stats['session_stats'] = self.session_manager.get_stats()
        return stats
    
    def print_session_stats(self):
        """Print detailed session statistics"""
        session_stats = self.session_manager.get_stats()
        print(f"\n🔐 Session Statistics:")
        print(f"   Active sessions: {session_stats['total_sessions']}")
        print(f"   Total requests: {session_stats['total_requests']}")
        print(f"   Requests per session: {session_stats['requests_per_session']:.1f}")
        print(f"   Error rate: {session_stats['error_rate']*100:.2f}%")
        print(f"   Session rotations: {self.stats['session_rotations']}")
    
    def clear_cache(self):
        """Clear response cache"""
        self.cache.clear()


# Aliases for compatibility
Scraper = MultiSessionScraper
