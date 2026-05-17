"""
OPTIMIZED Storage Module with WAL mode and error recovery
Fixes database corruption issues
"""

import asyncio
import sqlite3
import os
import time
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    import duckdb
    HAS_DUCKDB = True
except:
    HAS_DUCKDB = False

try:
    import aiofiles
    HAS_AIOFILES = True
except:
    HAS_AIOFILES = False


class ProductStorage:
    """
    High-performance product storage with WAL mode and error recovery
    """
    
    def __init__(self, db_path: str = "data/products_archive.db", use_duckdb: bool = False):
        self.db_path = db_path
        self.use_duckdb = use_duckdb and HAS_DUCKDB
        
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data", exist_ok=True)
        
        # Thread pool for async operations
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Stats
        self.stats = {
            'total_saved': 0,
            'batches': 0,
            'last_save_time': 0.0,
            'errors': 0,
        }
        
        # Initialize database with optimizations
        self._init_db()
        
        engine = "DuckDB" if self.use_duckdb else "SQLite"
        print(f"💾 Storage Ready ({engine})")
        print(f"   DB: {db_path}")
        
        # Show current count
        count = self.get_total_count()
        print(f"   Records: {count:,}")
    
    def _init_db(self):
        """Initialize database with WAL mode and optimizations"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            
            # ✅ Enable WAL mode for better concurrency and corruption prevention
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe
            conn.execute("PRAGMA cache_size=-64000")   # 64MB cache
            conn.execute("PRAGMA temp_store=MEMORY")   # Temp tables in memory
            conn.execute("PRAGMA mmap_size=268435456") # 256MB memory-mapped I/O
            
            # Main products table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products_archive (
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
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Create indexes for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_product_id ON products_archive(product_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_discount ON products_archive(discount DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_brand ON products_archive(brand)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON products_archive(scraped_at)")
            
            # Metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS storage_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            conn.commit()
            conn.close()
            
        except sqlite3.DatabaseError as e:
            print(f"⚠️ Database error during init: {e}")
            print(f"   Run: python fix_database.py")
            raise
        
        # Initialize DuckDB if enabled
        if self.use_duckdb:
            self._init_duckdb()
    
    def _init_duckdb(self):
        """Initialize DuckDB for fast analytics"""
        try:
            duck_path = self.db_path.replace('.db', '_analytics.duckdb')
            conn = duckdb.connect(duck_path)
            
            # Create view of SQLite data
            conn.execute(f"""
                CREATE OR REPLACE VIEW products AS 
                SELECT * FROM sqlite_scan('{self.db_path}', 'products_archive')
            """)
            
            conn.close()
            print(f"   Analytics: {duck_path}")
        except Exception as e:
            print(f"   ⚠️ DuckDB init failed: {e}")
            self.use_duckdb = False
    
    async def save_products(self, products: List[Dict]) -> bool:
        """
        Async bulk insert with error recovery
        """
        if not products:
            return True
        
        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            self.executor,
            self._save_products_sync,
            products
        )
        
        return success
    
    def _save_products_sync(self, products: List[Dict]) -> bool:
        """Synchronous bulk insert with transaction and error recovery"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                start = time.time()
                
                conn = sqlite3.connect(self.db_path, timeout=30)
                cursor = conn.cursor()
                
                # Prepare data for bulk insert
                rows = []
                for p in products:
                    try:
                        rows.append((
                            p.get('product_id', ''),
                            p.get('listing_id', ''),
                            p.get('brand', ''),
                            p.get('title', '')[:500],  # Limit title length
                            p.get('current_price', ''),
                            p.get('original_price', ''),
                            int(p.get('discount', 0)),
                            p.get('url', ''),
                            p.get('scraped_at', datetime.now().isoformat()),
                        ))
                    except Exception as e:
                        # Skip invalid products
                        continue
                
                if not rows:
                    conn.close()
                    return False
                
                # Bulk insert with transaction (MUCH faster)
                cursor.executemany("""
                    INSERT INTO products_archive 
                    (product_id, listing_id, brand, title, current_price, original_price, discount, url, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
                
                conn.commit()
                conn.close()
                
                elapsed = time.time() - start
                
                self.stats['total_saved'] += len(rows)
                self.stats['batches'] += 1
                self.stats['last_save_time'] = elapsed
                
                # Only print occasionally to reduce output
                if self.stats['batches'] % 5 == 0 or len(rows) > 100:
                    print(f"💾 Saved {len(rows)} products to DB in {elapsed:.2f}s ({len(rows)/elapsed:.0f}/s)")
                
                return True
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(0.5 * retry_count)  # Exponential backoff
                        continue
                    else:
                        print(f"⚠️ Database locked after {max_retries} retries")
                        self.stats['errors'] += 1
                        return False
                else:
                    print(f"⚠️ Database error: {e}")
                    self.stats['errors'] += 1
                    return False
                    
            except sqlite3.DatabaseError as e:
                print(f"⚠️ Database corrupted: {e}")
                print(f"   Run: python fix_database.py")
                self.stats['errors'] += 1
                return False
                
            except Exception as e:
                print(f"⚠️ Storage error: {e}")
                self.stats['errors'] += 1
                return False
        
        return False
    
    def get_total_count(self) -> int:
        """Get total number of archived products"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM products_archive")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except:
            return 0
    
    def get_stats(self) -> Dict:
        """Get storage statistics"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            cursor = conn.cursor()
            
            # Total products
            cursor.execute("SELECT COUNT(*) FROM products_archive")
            total = cursor.fetchone()[0]
            
            # Unique products
            cursor.execute("SELECT COUNT(DISTINCT product_id) FROM products_archive")
            unique = cursor.fetchone()[0]
            
            # Hot deals (70%+)
            cursor.execute("SELECT COUNT(*) FROM products_archive WHERE discount >= 70")
            hot = cursor.fetchone()[0]
            
            # Top brands
            cursor.execute("""
                SELECT brand, COUNT(*) as count 
                FROM products_archive 
                WHERE brand != '' 
                GROUP BY brand 
                ORDER BY count DESC 
                LIMIT 5
            """)
            top_brands = cursor.fetchall()
            
            conn.close()
            
            return {
                'total': total,
                'unique': unique,
                'hot_deals': hot,
                'top_brands': top_brands,
                'saved': self.stats['total_saved'],
                'batches': self.stats['batches'],
                'errors': self.stats['errors'],
            }
        except:
            return {
                'total': 0,
                'saved': self.stats['total_saved'],
                'batches': self.stats['batches'],
                'errors': self.stats['errors'],
            }
    
    async def export_to_csv(self, output_file: str, limit: Optional[int] = None) -> bool:
        """Export data to CSV on demand"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._export_to_csv_sync,
            output_file,
            limit
        )
    
    def _export_to_csv_sync(self, output_file: str, limit: Optional[int] = None) -> bool:
        """Synchronous CSV export"""
        try:
            import csv
            
            conn = sqlite3.connect(self.db_path, timeout=10)
            cursor = conn.cursor()
            
            query = "SELECT product_id, listing_id, brand, title, current_price, original_price, discount, url, scraped_at FROM products_archive ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['product_id', 'listing_id', 'brand', 'title', 'current_price', 'original_price', 'discount', 'url', 'scraped_at'])
                writer.writerows(cursor.fetchall())
            
            conn.close()
            
            print(f"📊 Exported to {output_file}")
            return True
            
        except Exception as e:
            print(f"⚠️ CSV export error: {e}")
            return False
    
    def query_hot_deals(self, min_discount: int = 70, limit: int = 100) -> List[Dict]:
        """Query hot deals"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT product_id, brand, title, current_price, discount, url, scraped_at
                FROM products_archive
                WHERE discount >= ?
                ORDER BY discount DESC, scraped_at DESC
                LIMIT ?
            """, (min_discount, limit))
            
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return results
        except:
            return []
    
    def query_by_brand(self, brand: str, limit: int = 100) -> List[Dict]:
        """Query products by brand"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT product_id, brand, title, current_price, discount, url, scraped_at
                FROM products_archive
                WHERE brand LIKE ?
                ORDER BY discount DESC, scraped_at DESC
                LIMIT ?
            """, (f"%{brand}%", limit))
            
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return results
        except:
            return []
    
    def cleanup_old_records(self, days: int = 30) -> int:
        """Remove records older than N days"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM products_archive 
                WHERE created_at < strftime('%s', 'now', '-{} days')
            """.format(days))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            print(f"🧹 Cleaned {deleted} old records")
            return deleted
        except:
            return 0
    
    def vacuum_database(self):
        """Optimize database (run after cleanup)"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=60)
            conn.execute("VACUUM")
            conn.close()
            print("✓ Database optimized")
        except Exception as e:
            print(f"⚠️ Vacuum failed: {e}")
    
    def close(self):
        """Cleanup resources"""
        self.executor.shutdown(wait=True)


# Convenience function
async def quick_save(products: List[Dict], db_path: str = "data/products_archive.db"):
    """Quick save function"""
    storage = ProductStorage(db_path)
    await storage.save_products(products)
    return storage.get_stats()