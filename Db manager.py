"""
Database Management Utility
Query, analyze, and export your product data
"""

import argparse
from storage import ProductStorage, AnalyticsEngine


def print_header(text):
    print("\n" + "="*70)
    print(f" {text} ".center(70, "="))
    print("="*70)


def show_stats(db_path: str = "data/products_archive.db"):
    """Show database statistics"""
    print_header("DATABASE STATISTICS")
    
    storage = ProductStorage(db_path)
    stats = storage.get_stats()
    
    print(f"\n📊 Total Records: {stats.get('total', 0):,}")
    print(f"🆔 Unique Products: {stats.get('unique', 0):,}")
    print(f"🔥 Hot Deals (70%+): {stats.get('hot_deals', 0):,}")
    
    if stats.get('top_brands'):
        print(f"\n🏆 Top Brands:")
        for i, (brand, count) in enumerate(stats['top_brands'], 1):
            print(f"   {i}. {brand}: {count:,} products")
    
    storage.close()


def export_csv(db_path: str = "data/products_archive.db", output: str = "export.csv", limit: int = None):
    """Export database to CSV"""
    print_header("EXPORT TO CSV")
    
    import asyncio
    
    storage = ProductStorage(db_path)
    
    async def _export():
        success = await storage.export_to_csv(output, limit)
        if success:
            print(f"\n✅ Exported to: {output}")
            if limit:
                print(f"   Limited to {limit} records")
        else:
            print(f"\n❌ Export failed")
    
    asyncio.run(_export())
    storage.close()


def query_hot_deals(db_path: str = "data/products_archive.db", min_discount: int = 70, limit: int = 20):
    """Query hot deals"""
    print_header(f"HOT DEALS ({min_discount}%+ OFF)")
    
    storage = ProductStorage(db_path)
    deals = storage.query_hot_deals(min_discount, limit)
    
    if not deals:
        print("\n❌ No deals found")
    else:
        print(f"\n🔥 Found {len(deals)} deals:\n")
        for i, deal in enumerate(deals, 1):
            print(f"{i}. {deal['discount']}% OFF - ₹{deal['current_price']}")
            print(f"   {deal['brand']} - {deal['title'][:60]}")
            print(f"   {deal['url']}\n")
    
    storage.close()


def query_brand(db_path: str = "data/products_archive.db", brand: str = "", limit: int = 20):
    """Query products by brand"""
    print_header(f"PRODUCTS: {brand.upper()}")
    
    storage = ProductStorage(db_path)
    products = storage.query_by_brand(brand, limit)
    
    if not products:
        print(f"\n❌ No products found for '{brand}'")
    else:
        print(f"\n📦 Found {len(products)} products:\n")
        for i, p in enumerate(products, 1):
            print(f"{i}. {p['discount']}% OFF - ₹{p['current_price']}")
            print(f"   {p['title'][:60]}")
            print(f"   {p['url']}\n")
    
    storage.close()


def analytics_brands(db_path: str = "data/products_archive.db", min_discount: int = 50):
    """Run brand analytics (requires DuckDB)"""
    print_header("BRAND ANALYTICS")
    
    try:
        analytics = AnalyticsEngine(db_path)
        brands = analytics.get_top_deals_by_brand(min_discount)
        
        if not brands:
            print(f"\n❌ No data found")
        else:
            print(f"\n🏆 Top Brands ({min_discount}%+ deals):\n")
            print(f"{'Rank':<6}{'Brand':<25}{'Deals':<10}{'Avg %':<10}{'Max %':<10}")
            print("-" * 60)
            for i, b in enumerate(brands, 1):
                print(f"{i:<6}{b['brand'][:24]:<25}{b['deal_count']:<10}{b['avg_discount']:<10}{b['max_discount']:<10}")
    
    except ImportError:
        print("\n❌ DuckDB not installed")
        print("   Install: pip install duckdb")
    except Exception as e:
        print(f"\n❌ Error: {e}")


def cleanup(db_path: str = "data/products_archive.db", days: int = 30):
    """Clean up old records"""
    print_header("DATABASE CLEANUP")
    
    print(f"\n⚠️  This will delete records older than {days} days")
    confirm = input("Continue? (yes/no): ").strip().lower()
    
    if confirm == 'yes':
        storage = ProductStorage(db_path)
        deleted = storage.cleanup_old_records(days)
        print(f"\n✅ Deleted {deleted} old records")
        storage.close()
    else:
        print("\n❌ Cancelled")


def main():
    parser = argparse.ArgumentParser(
        description="Flipkart Scraper Database Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show stats
  python db_manager.py stats
  
  # Export all data to CSV
  python db_manager.py export --output products.csv
  
  # Export latest 1000 records
  python db_manager.py export --output recent.csv --limit 1000
  
  # Query hot deals (70%+)
  python db_manager.py hot-deals --min-discount 70 --limit 50
  
  # Query by brand
  python db_manager.py brand --name "Samsung" --limit 30
  
  # Brand analytics (requires DuckDB)
  python db_manager.py analytics --min-discount 60
  
  # Clean old records
  python db_manager.py cleanup --days 30
        """
    )
    
    parser.add_argument('command', choices=['stats', 'export', 'hot-deals', 'brand', 'analytics', 'cleanup'],
                       help='Command to run')
    parser.add_argument('--db', default='data/products_archive.db', help='Database path')
    parser.add_argument('--output', help='Output CSV file')
    parser.add_argument('--limit', type=int, help='Limit number of records')
    parser.add_argument('--min-discount', type=int, default=70, help='Minimum discount percentage')
    parser.add_argument('--name', help='Brand name to search')
    parser.add_argument('--days', type=int, default=30, help='Days to keep')
    
    args = parser.parse_args()
    
    if args.command == 'stats':
        show_stats(args.db)
    
    elif args.command == 'export':
        if not args.output:
            print("❌ --output required for export")
            return
        export_csv(args.db, args.output, args.limit)
    
    elif args.command == 'hot-deals':
        query_hot_deals(args.db, args.min_discount, args.limit or 20)
    
    elif args.command == 'brand':
        if not args.name:
            print("❌ --name required for brand query")
            return
        query_brand(args.db, args.name, args.limit or 20)
    
    elif args.command == 'analytics':
        analytics_brands(args.db, args.min_discount)
    
    elif args.command == 'cleanup':
        cleanup(args.db, args.days)


if __name__ == "__main__":
    main()