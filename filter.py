"""
Duplicate Filter
"""

import sqlite3
import os
from datetime import datetime
from typing import Tuple, Dict


class Filter:
    
    def __init__(self, db_path: str = "data/products.db", min_new: int = 0, min_exist: int = 15, min_change: int = 2):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data", exist_ok=True)
        
        self.db = db_path
        self.min_new = min_new
        self.min_exist = min_exist
        self.min_change = min_change
        
        self._init()
        
        print(f"📊 Filter Ready")
        print(f"   New: {min_new}%+")
        print(f"   Existing: {min_exist}%+")
        print(f"   Change: {min_change}%+")
    
    def _init(self):
        conn = sqlite3.connect(self.db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                listing_id TEXT,
                last_price TEXT,
                last_discount INTEGER,
                brand TEXT,
                title TEXT,
                first_seen TEXT,
                last_notified TEXT,
                notification_count INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
    
    def should_notify(self, pid: str, price: str, mrp: str, discount: int) -> Tuple[bool, str]:
        try:
            p = float(str(price).replace('₹', '').replace(',', ''))
            m = float(str(mrp).replace('₹', '').replace(',', ''))
            if p >= m or p <= 0:
                return False, "❌ Invalid"
        except:
            return False, "❌ Format"
        
        conn = sqlite3.connect(self.db)
        cur = conn.cursor()
        cur.execute("SELECT last_price, last_discount FROM products WHERE product_id=?", (pid,))
        result = cur.fetchone()
        conn.close()
        
        if not result:
            if discount < self.min_new:
                return False, f"🚫 New {discount}%"
            return True, f"🆕 {discount}%"
        
        old_price, old_disc = result
        
        if discount < self.min_exist:
            return False, f"🗑️ Low {discount}%"
        
        if str(price) == old_price and discount == old_disc:
            return False, f"📋 Dup {discount}%"
        
        change = discount - old_disc
        
        if change < 0:
            return False, f"⬇️ Down {old_disc}→{discount}%"
        
        if change < self.min_change:
            return False, f"📊 +{change}%"
        
        return True, f"📈 {old_disc}→{discount}% (+{change}%)"
    
    def save(self, pid: str, lid: str, price: str, discount: int, brand: str = "", title: str = ""):
        try:
            conn = sqlite3.connect(self.db)
            cur = conn.cursor()
            cur.execute("SELECT notification_count FROM products WHERE product_id=?", (pid,))
            result = cur.fetchone()
            
            now = datetime.now().isoformat()
            
            if not result:
                conn.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)",
                    (pid, lid, price, discount, brand, title[:200], now, now, 1))
            else:
                cnt = result[0] + 1
                conn.execute("UPDATE products SET listing_id=?, last_price=?, last_discount=?, brand=?, title=?, last_notified=?, notification_count=? WHERE product_id=?",
                    (lid, price, discount, brand, title[:200], now, cnt, pid))
            
            conn.commit()
            conn.close()
        except:
            pass
    
    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db)
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM products")
        total = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM products WHERE last_discount >= 70")
        hot = cur.fetchone()[0]
        
        cur.execute("SELECT SUM(notification_count) FROM products")
        notifs = cur.fetchone()[0] or 0
        
        conn.close()
        
        return {
            "total": total,
            "hot": hot,
            "notifications": notifs
        }
    
    def close(self):
        pass
