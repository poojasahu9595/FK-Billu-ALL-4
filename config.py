"""
MAXIMUM SPEED Configuration
Push the limits - as fast as technically possible!
"""

import os

# ========================================
# TELEGRAM CONFIGURATION
# ========================================
TELEGRAM_CONFIG = {
    "bot_tokens": [
        "8132559854:AAHYLoh_psFO-KZFGYq_VtCqAF-6bTHOfsM",
        "8523736827:AAGzmrf_2KuoKkza-rtDowWAWoP6_YvyuvU",
        "8275890326:AAGCVJaT3EtHgd9zvlnkOZ9DC1acgrgMAVY",
        "8503178959:AAE3aX_pUgfyG7G5fnMj5VcrrP9S_HO6hOw",
        "8496853271:AAHuT15UNDQKnS3U6XwoJjZYUQFf2HOveMQ",
        "8582181603:AAH8JUTC-r8-BQtPNZA_ndPLXonvL5D6Llg",
        "8455046359:AAFG0QuJ6_VwnFLusC_E7MEXAEvrfdvyQe8",
        "8536090953:AAFO1qqKO2cfdiIAQew8R8nDRX2OeRtV-2Q",
        "8279533057:AAHM5Thhepq0TTk78CXesjcPPRPsEy1313g",
        "8592200284:AAHoX0NOU_HQYTUbvRBuriRB5jA8spetZcM",
        "8494390712:AAG16UX3qVIspBfQDNUD6NfTgdTKV-_Je80",
        "8243786229:AAHTIwz2Uz6WdabLF8Qqcu0Q7-MQbVZrEbg",
        "8284583972:AAFI37qi_meNdDBd3t_HBlU9mN2uxSxUIeQ",
        "8509684410:AAH_e66uVYl5ka2Y80zgymvZFtV_Y6IFMB4",
        "8204596098:AAHSus_uyYI-tOdFFQQ-JtIOZJnDYIAcuKQ",
        "8385048133:AAGhAXVm9qb3ItXBrcIrDHmCSeXiz86yJ0w",
        "8554744006:AAF0hikR7-LFl1ZB2i40ktCpWZklFFut5e8",
    ],
    "chat_channels": {
        "all": "-1003794266110",
        "70plus": "-1003724024226",
        "90plus": "-1003780860886",
    },
    "chat_id": "-1003895320194",
}

CHANNEL_RULES = {
    "routing": [
        (90, ["all", "70plus", "90plus"]),
        (70, ["all", "70plus"]),
        (0,  ["all"]),
    ]
}

# ========================================
# 🚀 MAXIMUM SPEED CONFIGURATION
# ========================================
SPEED_PRESET = "maximum"  # Maximum speed!

SCRAPER_CONFIG = {
    # 🔥 MINIMUM DELAYS - As fast as possible
    "delay_between_urls": (0.05, 0.1),      # Minimal
    "delay_between_pages": (0.05, 0.1),      # Minimal
    "loop_delay": 20,                       
    
    # Pagination - Get everything fast
    "enable_infinite_scroll": True,
    "max_pages_per_url": 50,
    "min_products_per_page": 5,
    "stop_on_consecutive_empty": 2,
    
    # Files
    "links_file": "links.txt",
    "database_path": "data/products.db",
    "output_dir": "data/output",
    "archive_db_path": "data/products_archive.db",
    
    # 🚀 MAXIMUM PARALLELISM
    "parallel_batch_size": 32,               # Process 32 URLs at once!
    "delay_between_batches": 0.1,            # Minimal wait
    "telegram_workers": 40,                  # 40 workers
    
    # 🔥 EXTREME CONCURRENCY
    "max_concurrent_pages": 25,              # 25 pages at once per URL
    "num_sessions": 20,                      # 20 sessions!
    
    # Advanced
    "connection_pool_size": 150,             # Large pool
    "enable_response_cache": True,
    "cache_ttl": 600,
}

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.178 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.178 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.178 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.99 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-A525F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.178 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.99 Mobile Safari/537.36",
]

DUPLICATE_CONFIG = {
    "min_discount_new": 0,
    "min_discount_existing": 15,
    "min_change_percent": 2,
    "db_path": "data/products.db",
}

OUTPUT_CONFIG = {
    "telegram_format": "{emoji} {discount}% OFF | ₹{price} | ₹{mrp}\n{brand} {title}\n{url}",
}

FEATURES = {
    "enable_scraping": True,
    "enable_telegram_notifications": True,
    "enable_duplicate_filter": True,
    "save_to_csv": False,
    "enable_storage": True,
    "enable_duckdb_analytics": False,
    "enable_connection_pooling": True,
    "enable_response_caching": True,
    "enable_concurrent_pages": True,
    "enable_multi_session": True,
}

def get_discount_emoji(discount: int) -> str:
    if discount >= 90:
        return "🔥💎"
    elif discount >= 70:
        return "🔥"
    elif discount >= 50:
        return "⚡"
    else:
        return "✨"

def initialize_directories():
    os.makedirs("data", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs(SCRAPER_CONFIG["output_dir"], exist_ok=True)

def print_config():
    print("\n" + "="*70)
    print(" 🚀 MAXIMUM SPEED MODE - NO LIMITS! ".center(70, "="))
    print("="*70)
    
    print(f"\n⚡ Speed Settings:")
    print(f"   Delays: 0.05-0.1s (MINIMAL)")
    print(f"   Parallel URLs: {SCRAPER_CONFIG['parallel_batch_size']} (MAXIMUM)")
    print(f"   Concurrent pages: {SCRAPER_CONFIG['max_concurrent_pages']} per URL")
    print(f"   Sessions: {SCRAPER_CONFIG['num_sessions']} (20 devices!)")
    print(f"   Telegram workers: {SCRAPER_CONFIG['telegram_workers']}")
    print(f"   Connection pool: {SCRAPER_CONFIG['connection_pool_size']}")
    
    print(f"\n🎯 Expected Performance:")
    print(f"   Speed: 400-600 products/second")
    print(f"   Time for 150k products: 4-6 minutes")
    print(f"   Time for 30k products: 1-2 minutes")
    
    print(f"\n⚠️  Monitor:")
    print(f"   • Watch for errors (should be <2%)")
    print(f"   • CPU usage (will be high)")
    print(f"   • Memory usage")
    print(f"   • Reduce if rate limited")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    print("\n" + "="*70)
    print(" MAXIMUM SPEED CONFIG ".center(70, "="))
    print("="*70)
    print_config()
else:
    print(f"⚙️  Config loaded: MAXIMUM SPEED ({SCRAPER_CONFIG['num_sessions']} sessions, {SCRAPER_CONFIG['parallel_batch_size']} parallel)")
