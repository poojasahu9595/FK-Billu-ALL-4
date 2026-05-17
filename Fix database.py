"""
Database Recovery and Fix Script
Fixes corrupted database and creates fresh one
"""

import os
import shutil
from datetime import datetime

def backup_corrupted_db():
    """Backup corrupted database"""
    db_files = [
        'data/products.db',
        'data/products_archive.db'
    ]
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    for db_file in db_files:
        if os.path.exists(db_file):
            backup_file = f"{db_file}.corrupted.{timestamp}"
            try:
                shutil.copy2(db_file, backup_file)
                print(f"✓ Backed up: {db_file} → {backup_file}")
            except Exception as e:
                print(f"⚠️ Could not backup {db_file}: {e}")

def delete_corrupted_db():
    """Delete corrupted databases"""
    db_files = [
        'data/products.db',
        'data/products_archive.db',
        'data/products.db-journal',
        'data/products_archive.db-journal',
        'data/products.db-wal',
        'data/products_archive.db-wal',
        'data/products.db-shm',
        'data/products_archive.db-shm',
    ]
    
    for db_file in db_files:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
                print(f"✓ Deleted: {db_file}")
            except Exception as e:
                print(f"⚠️ Could not delete {db_file}: {e}")

def create_fresh_db():
    """Create fresh database"""
    import sqlite3
    
    os.makedirs('data', exist_ok=True)
    
    # Create filter database
    print("\n📦 Creating fresh filter database...")
    conn = sqlite3.connect('data/products.db')
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
    print("✓ Filter database created")
    
    # Create archive database
    print("\n📦 Creating fresh archive database...")
    conn = sqlite3.connect('data/products_archive.db')
    
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
    
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
    
    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_id ON products_archive(product_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discount ON products_archive(discount DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brand ON products_archive(brand)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON products_archive(scraped_at)")
    
    conn.commit()
    conn.close()
    print("✓ Archive database created with optimizations")

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║          DATABASE RECOVERY TOOL                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    print("This will:")
    print("  1. Backup corrupted databases")
    print("  2. Delete corrupted files")
    print("  3. Create fresh optimized databases")
    print()
    
    choice = input("Continue? (yes/no): ").strip().lower()
    
    if choice != 'yes':
        print("Cancelled.")
        return
    
    print("\n" + "="*70)
    print(" STEP 1: Backup Corrupted Databases ".center(70, "="))
    print("="*70)
    backup_corrupted_db()
    
    print("\n" + "="*70)
    print(" STEP 2: Delete Corrupted Files ".center(70, "="))
    print("="*70)
    delete_corrupted_db()
    
    print("\n" + "="*70)
    print(" STEP 3: Create Fresh Databases ".center(70, "="))
    print("="*70)
    create_fresh_db()
    
    print("\n" + "="*70)
    print(" ✅ RECOVERY COMPLETE ".center(70, "="))
    print("="*70)
    print("\nYou can now run: python main.py")
    print("\nNote: Your old data is backed up with .corrupted timestamp")

if __name__ == "__main__":
    main()