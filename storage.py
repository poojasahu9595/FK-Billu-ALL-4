"""
Storage Module - FIXED VERSION with Zero-Division Protection
Handles product archiving with proper error handling
"""

import sqlite3
import os
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import threading


class ProductStorage:
    """Persistent storage for scraped products"""
    
    def __init__(self, db_path: str = "data/products_archive.db", use_duckdb: bool = False):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data", exist_ok=True)
        
        self.db_path = db_path
        self.use_duckdb = use_duckdb
        self._lock = threading.Lock()
        
        # SQLite connection
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-16000")
        
        self._init_tables()
        
        print(f"💾 Storage Ready")
        print(f"   Database: {db_path}")
        print(f"   DuckDB: {'Enabled' if use_duckdb else 'Disabled'}")
    
    def _init_tables(self):
        """Initialize database tables"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                listing_id TEXT,
                brand TEXT,
                title TEXT,
                current_price TEXT,
                original_price TEXT,
                discount INTEGER,
                url TEXT,
                scraped_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_id, current_price, discount)
            )
        """)
        # FIX 4: Safe migration — add unique index if upgrading old DB
        try:
            self.conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_product_price_discount
                ON products(product_id, current_price, discount)
            """)
        except:
            pass
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_product_id ON products(product_id)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_discount ON products(discount)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scraped_at ON products(scraped_at)
        """)
        
        self.conn.commit()
    
    async def save_products(self, products: List[Dict]):
        """Save products to database (async wrapper)"""
        if not products:
            return
        
        try:
            with self._lock:
                now = datetime.now().isoformat()
                
                data = []
                for p in products:
                    data.append((
                        p.get('product_id', ''),
                        p.get('listing_id', ''),
                        p.get('brand', ''),
                        p.get('title', '')[:500],
                        p.get('current_price', '0'),
                        p.get('original_price', '0'),
                        int(p.get('discount', 0)),
                        p.get('url', '')[:1000],
                        p.get('scraped_at', now)
                    ))
                
                # FIX 4: INSERT OR IGNORE — same product+price+discount combo skip
                self.conn.executemany(
                    "INSERT OR IGNORE INTO products (product_id, listing_id, brand, title, current_price, original_price, discount, url, scraped_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    data
                )
                self.conn.commit()
        
        except Exception as e:
            print(f"⚠️ Storage error: {e}")
    
    def get_stats(self) -> Dict:
        """Get database statistics - FIXED with zero-division protection"""
        try:
            cur = self.conn.cursor()
            
            # Total records
            cur.execute("SELECT COUNT(*) FROM products")
            total = cur.fetchone()[0]
            
            # Unique products
            cur.execute("SELECT COUNT(DISTINCT product_id) FROM products")
            unique = cur.fetchone()[0]
            
            # Hot deals (70%+)
            cur.execute("SELECT COUNT(*) FROM products WHERE discount >= 70")
            hot_deals = cur.fetchone()[0]
            
            # Average discount - FIXED
            cur.execute("SELECT AVG(discount) FROM products WHERE discount > 0")
            avg_result = cur.fetchone()[0]
            avg_discount = float(avg_result) if avg_result else 0.0
            
            # Top brands - FIXED with LIMIT to prevent errors
            cur.execute("""
                SELECT brand, COUNT(*) as cnt 
                FROM products 
                WHERE brand != '' 
                GROUP BY brand 
                ORDER BY cnt DESC 
                LIMIT 10
            """)
            top_brands = cur.fetchall()
            
            return {
                'total': total,
                'unique': unique,
                'hot_deals': hot_deals,
                'avg_discount': avg_discount,
                'top_brands': top_brands
            }
        
        except Exception as e:
            print(f"⚠️ Stats error: {e}")
            return {
                'total': 0,
                'unique': 0,
                'hot_deals': 0,
                'avg_discount': 0.0,
                'top_brands': []
            }
    
    async def export_to_csv(self, output_file: str, limit: Optional[int] = None) -> bool:
        """Export database to CSV"""
        try:
            import csv
            
            query = "SELECT product_id, listing_id, brand, title, current_price, original_price, discount, url, scraped_at FROM products ORDER BY scraped_at DESC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            cur = self.conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            
            if not rows:
                return False
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['product_id', 'listing_id', 'brand', 'title', 'current_price', 'original_price', 'discount', 'url', 'scraped_at'])
                writer.writerows(rows)
            
            return True
        
        except Exception as e:
            print(f"⚠️ Export error: {e}")
            return False
    
    def query_hot_deals(self, min_discount: int = 70, limit: int = 20) -> List[Dict]:
        """Query hot deals"""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT product_id, brand, title, current_price, original_price, discount, url
                FROM products
                WHERE discount >= ?
                ORDER BY discount DESC, scraped_at DESC
                LIMIT ?
            """, (min_discount, limit))
            
            rows = cur.fetchall()
            
            return [
                {
                    'product_id': r[0],
                    'brand': r[1],
                    'title': r[2],
                    'current_price': r[3],
                    'original_price': r[4],
                    'discount': r[5],
                    'url': r[6]
                }
                for r in rows
            ]
        
        except Exception as e:
            print(f"⚠️ Query error: {e}")
            return []
    
    def query_by_brand(self, brand: str, limit: int = 20) -> List[Dict]:
        """Query products by brand"""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT product_id, brand, title, current_price, original_price, discount, url
                FROM products
                WHERE brand LIKE ?
                ORDER BY discount DESC, scraped_at DESC
                LIMIT ?
            """, (f"%{brand}%", limit))
            
            rows = cur.fetchall()
            
            return [
                {
                    'product_id': r[0],
                    'brand': r[1],
                    'title': r[2],
                    'current_price': r[3],
                    'original_price': r[4],
                    'discount': r[5],
                    'url': r[6]
                }
                for r in rows
            ]
        
        except Exception as e:
            print(f"⚠️ Query error: {e}")
            return []
    
    def cleanup_old_records(self, days: int = 30) -> int:
        """Delete records older than specified days"""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            
            with self._lock:
                cur = self.conn.cursor()
                cur.execute("DELETE FROM products WHERE scraped_at < ?", (cutoff,))
                deleted = cur.rowcount
                self.conn.commit()
                
                # Vacuum to reclaim space
                self.conn.execute("VACUUM")
                
                return deleted
        
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")
            return 0
    
    def close(self):
        """Close database connection"""
        try:
            self.conn.close()
        except:
            pass


class AnalyticsEngine:
    """Advanced analytics using DuckDB (optional)"""
    
    def __init__(self, db_path: str):
        try:
            import duckdb
            self.duck = duckdb.connect(':memory:')
            
            # Load SQLite data into DuckDB
            self.duck.execute(f"INSTALL sqlite; LOAD sqlite;")
            self.duck.execute(f"ATTACH '{db_path}' AS sqlite_db (TYPE sqlite);")
            
            print("📊 Analytics Engine Ready (DuckDB)")
        
        except ImportError:
            print("⚠️ DuckDB not installed - analytics disabled")
            self.duck = None
    
    def get_top_deals_by_brand(self, min_discount: int = 50, limit: int = 20) -> List[Dict]:
        """Get top brands by deal count and avg discount"""
        if not self.duck:
            return []
        
        try:
            result = self.duck.execute(f"""
                SELECT 
                    brand,
                    COUNT(*) as deal_count,
                    ROUND(AVG(discount), 1) as avg_discount,
                    MAX(discount) as max_discount
                FROM sqlite_db.products
                WHERE discount >= {min_discount}
                AND brand != ''
                GROUP BY brand
                ORDER BY deal_count DESC
                LIMIT {limit}
            """).fetchall()
            
            return [
                {
                    'brand': r[0],
                    'deal_count': r[1],
                    'avg_discount': r[2],
                    'max_discount': r[3]
                }
                for r in result
            ]
        
        except Exception as e:
            print(f"⚠️ Analytics error: {e}")
            return []
    
    def get_price_trends(self, product_id: str) -> List[Dict]:
        """Get price history for a product"""
        if not self.duck:
            return []
        
        try:
            result = self.duck.execute(f"""
                SELECT 
                    scraped_at,
                    current_price,
                    discount
                FROM sqlite_db.products
                WHERE product_id = '{product_id}'
                ORDER BY scraped_at DESC
                LIMIT 100
            """).fetchall()
            
            return [
                {
                    'timestamp': r[0],
                    'price': r[1],
                    'discount': r[2]
                }
                for r in result
            ]
        
        except Exception as e:
            print(f"⚠️ Trend analysis error: {e}")
            return []
