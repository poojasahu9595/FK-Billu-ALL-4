"""
filter.py — Unified duplicate + spam + brand filter
=====================================================
Merges filter.py + filter_enhanced.py + Brand_validator.py
into a single file.

Public class:  Filter
  • Duplicate detection with in-memory cache
  • Sponsored product blocking
  • Spam word filtering
  • Brand validation against URL parameters
"""

import sqlite3
import os
import threading
import re
from datetime import datetime
from typing import Tuple, Dict, List, Set
from urllib.parse import unquote


# ============================================================
# Brand Validator
# ============================================================

class BrandValidator:
    """Validates that a product's brand matches the brand filter in the URL."""

    def __init__(self):
        self._url_brands: Dict[str, Set[str]] = {}
        self.stats = {'blocked_wrong_brand': 0, 'passed': 0}

    @staticmethod
    def extract_brands_from_url(url: str) -> Set[str]:
        """
        Pull brand names out of a Flipkart filter URL.
        Handles double-encoded URL params like:
          facets.brand%255B%255D%3DApple  →  facets.brand[]=Apple
        """
        decoded = unquote(unquote(url))
        matches = re.findall(r'facets\.brand\[?\]?=([^&]+)', decoded, re.IGNORECASE)
        brands  = set()
        for m in matches:
            b = unquote(m.strip()).lower()
            if b:
                brands.add(b)
        return brands

    def set_url_brands(self, url: str) -> Set[str]:
        brands = self.extract_brands_from_url(url)
        self._url_brands[url] = brands
        return brands

    def is_valid_brand(self, product_brand: str, url: str) -> bool:
        if url not in self._url_brands:
            self.set_url_brands(url)

        expected = self._url_brands.get(url, set())

        # No brand filter in URL → allow everything
        if not expected:
            self.stats['passed'] += 1
            return True

        prod_lower = product_brand.lower().strip()
        for exp in expected:
            if exp in prod_lower or prod_lower in exp:
                self.stats['passed'] += 1
                return True

        self.stats['blocked_wrong_brand'] += 1
        return False


# ============================================================
# Unified Filter
# ============================================================

class Filter:
    """
    Single filter class replacing the old Filter + FilterEnhanced split.

    Checks (in order):
      1. Sponsored detection (via _raw fields or title/listing_id patterns)
      2. Brand validation against URL filter params
      3. Spam word matching in title / brand
      4. Price sanity check
      5. Duplicate / discount-change logic (in-memory cache + SQLite)
    """

    DEFAULT_SPAM_WORDS: Set[str] = {
        'sponsored', 'advertisement', 'promo code', 'limited time',
        'buy now', 'hurry up', 'flash sale', 'exclusive offer',
        'refurbished', 'open box', 'damaged box',
        'unbranded', 'generic', 'duplicate', 'imitation', 'replica',
        'factory second', 'b-grade', 'c-grade',
    }

    def __init__(
        self,
        db_path: str            = "data/products.db",
        min_new: int            = 0,
        min_exist: int          = 15,
        min_change: int         = 2,
        spam_words: List[str]   = None,
        block_sponsored: bool   = True,
        enable_brand_validation: bool = True,
    ):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data",
                    exist_ok=True)

        self.db              = db_path
        self.min_new         = min_new
        self.min_exist       = min_exist
        self.min_change      = min_change
        self.block_sponsored = block_sponsored
        self._lock           = threading.Lock()

        # Spam words
        self.spam_words: Set[str] = (
            {w.lower() for w in spam_words}
            if spam_words is not None
            else set(self.DEFAULT_SPAM_WORDS)
        )

        # Brand validator
        self.brand_validator = BrandValidator() if enable_brand_validation else None

        # SQLite — persistent, WAL mode for speed
        self.conn = sqlite3.connect(self.db, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-8000")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self._init_db()

        # In-memory O(1) lookup cache
        self._cache: Dict[str, Tuple[str, int]] = {}
        self._load_cache()

        # Running counters
        self.filter_stats = {
            'blocked_sponsored':  0,
            'blocked_spam':       0,
            'blocked_wrong_brand': 0,
            'passed':             0,
        }

        print(f"\n💎 Filter ready")
        print(f"   New: {min_new}%+  Existing: {min_exist}%+  Change: {min_change}%+")
        print(f"   Cached products   : {len(self._cache):,}")
        print(f"   Block sponsored   : {'YES' if block_sponsored else 'NO'}")
        print(f"   Brand validation  : {'YES' if enable_brand_validation else 'NO'}")
        print(f"   Spam words        : {len(self.spam_words)}")

    # ---- DB init ----

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id         TEXT PRIMARY KEY,
                listing_id         TEXT,
                last_price         TEXT,
                last_discount      INTEGER,
                brand              TEXT,
                title              TEXT,
                first_seen         TEXT,
                last_notified      TEXT,
                notification_count INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    def _load_cache(self):
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT product_id, last_price, last_discount FROM products")
            for row in cur.fetchall():
                self._cache[row[0]] = (row[1], row[2])
        except:
            pass

    # ---- Sponsored detection ----

    def _is_sponsored(self, product: Dict) -> bool:
        if not self.block_sponsored:
            return False

        raw = product.get('_raw', {})
        if raw:
            if raw.get('adTag'):            return True
            if raw.get('isSponsored'):      return True
            if raw.get('sponsoredData'):    return True
            if raw.get('adTracking') or raw.get('adImpressionId'): return True

            meta = raw.get('productMeta', {})
            for field_val in (str(meta.get('listingId', '')),
                              str(meta.get('productId', ''))):
                if any(p in field_val.lower()
                       for p in ('ad_', 'adv_', 'sponsor_', 'promo_', '_ad', '_sponsor')):
                    return True

        # Fallback checks (no _raw)
        title      = product.get('title', '').lower()
        brand      = product.get('brand', '').lower()
        listing_id = product.get('listing_id', '').lower()
        pid        = product.get('product_id', '').lower()

        if 'sponsored' in title or 'sponsored' in brand:
            return True

        ad_patterns = ('ad_', 'adv_', 'sponsor_', 'promo_', '_ad', '_sponsor')
        if any(p in listing_id or p in pid for p in ad_patterns):
            return True

        return False

    # ---- Spam detection ----

    def _is_spam(self, product: Dict) -> Tuple[bool, str]:
        title = product.get('title', '')
        brand = product.get('brand', '')
        for text, field in ((title, 'title'), (brand, 'brand')):
            text_l = text.lower()
            for word in self.spam_words:
                if word in text_l:
                    return True, f"spam_{field}:{word}"
        return False, ""

    # ---- Main check ----

    def should_notify(
        self,
        pid: str,
        price: str,
        mrp: str,
        discount: int,
        product: Dict  = None,
        url: str       = None,
    ) -> Tuple[bool, str]:
        """
        Returns (should_notify: bool, reason: str).

        Pass `product` dict for sponsored/spam/brand checking.
        Pass `url` for brand validation.
        """
        # 1. Sponsored
        if product and self._is_sponsored(product):
            self.filter_stats['blocked_sponsored'] += 1
            return False, "Sponsored"

        # 2. Brand validation
        if product and url and self.brand_validator:
            brand = product.get('brand', '')
            if not self.brand_validator.is_valid_brand(brand, url):
                self.filter_stats['blocked_wrong_brand'] += 1
                return False, f"wrong_brand:{brand}"

        # 3. Spam words
        if product:
            is_spam, reason = self._is_spam(product)
            if is_spam:
                self.filter_stats['blocked_spam'] += 1
                return False, reason

        # 4. Price sanity
        try:
            p = float(str(price).replace('₹', '').replace(',', ''))
            m = float(str(mrp).replace('₹', '').replace(',', ''))
            if p >= m or p <= 0:
                return False, "Invalid"
        except:
            return False, "Format"

        # 5. Duplicate / discount-change logic
        cached = self._cache.get(pid)

        if not cached:
            if discount < self.min_new:
                return False, f"New {discount}%"
            self.filter_stats['passed'] += 1
            return True, f"NEW {discount}%"

        old_price, old_disc = cached

        if discount < self.min_exist:
            return False, f"Low {discount}%"

        if str(price) == old_price and discount == old_disc:
            return False, f"Dup {discount}%"

        change = discount - old_disc

        if change < 0:
            return False, f"Down {old_disc}→{discount}%"

        if change < self.min_change:
            return False, f"+{change}%"

        self.filter_stats['passed'] += 1
        return True, f"{old_disc}→{discount}% (+{change}%)"

    # ---- Save ----

    def save(self, pid: str, lid: str, price: str, discount: int,
             brand: str = "", title: str = ""):
        try:
            now = datetime.now().isoformat()
            with self._lock:
                if pid not in self._cache:
                    self.conn.execute(
                        "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)",
                        (pid, lid, price, discount, brand, title[:200], now, now, 1)
                    )
                else:
                    self.conn.execute(
                        "UPDATE products SET listing_id=?, last_price=?, last_discount=?, "
                        "brand=?, title=?, last_notified=?, "
                        "notification_count=notification_count+1 "
                        "WHERE product_id=?",
                        (lid, price, discount, brand, title[:200], now, pid)
                    )
                self.conn.commit()
                self._cache[pid] = (price, discount)
        except:
            pass

    def save_batch(self, products: List[Dict]):
        """Save a batch of products in a single transaction."""
        if not products:
            return
        try:
            now = datetime.now().isoformat()
            with self._lock:
                for p in products:
                    pid      = p['product_id']
                    price    = p.get('current_price', '0')
                    discount = int(p.get('discount', 0))
                    lid      = p.get('listing_id', '')
                    brand    = p.get('brand', '')
                    title    = p.get('title', '')

                    if pid not in self._cache:
                        self.conn.execute(
                            "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?)",
                            (pid, lid, price, discount, brand, title[:200], now, now, 1)
                        )
                    else:
                        self.conn.execute(
                            "UPDATE products SET listing_id=?, last_price=?, last_discount=?, "
                            "brand=?, title=?, last_notified=?, "
                            "notification_count=notification_count+1 "
                            "WHERE product_id=?",
                            (lid, price, discount, brand, title[:200], now, pid)
                        )
                    self._cache[pid] = (price, discount)
                self.conn.commit()
        except:
            pass

    # ---- Spam word management ----

    def add_spam_word(self, word: str):
        self.spam_words.add(word.lower())

    def remove_spam_word(self, word: str):
        self.spam_words.discard(word.lower())

    def get_spam_words(self) -> List[str]:
        return sorted(self.spam_words)

    # ---- Stats ----

    def get_stats(self) -> Dict:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM products")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM products WHERE last_discount >= 70")
            hot = cur.fetchone()[0]
            cur.execute("SELECT SUM(notification_count) FROM products")
            notifs = cur.fetchone()[0] or 0
        except:
            total = hot = notifs = 0

        stats = {
            "total":                 total,
            "hot":                   hot,
            "notifications":         notifs,
            "blocked_sponsored":     self.filter_stats['blocked_sponsored'],
            "blocked_spam":          self.filter_stats['blocked_spam'],
            "blocked_wrong_brand":   self.filter_stats['blocked_wrong_brand'],
            "passed":                self.filter_stats['passed'],
        }
        if self.brand_validator:
            stats['brand_validator'] = self.brand_validator.stats.copy()
        return stats

    def close(self):
        try:
            self.conn.close()
        except:
            pass


# Backward-compat aliases
FilterEnhanced = Filter
