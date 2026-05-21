"""
config.py — Unified configuration
===================================
Single file: no more config_enhanced.py split.
Edit SPEED_PRESET to change performance tier.
"""

import os

# ============================================================
# TELEGRAM
# ============================================================
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
    "chat_id": "-1003794266110",
}

CHANNEL_RULES = {
    "routing": [
        (90, ["all", "70plus", "90plus"]),
        (70, ["all", "70plus"]),
        (0,  ["all"]),
    ]
}

# ============================================================
# SPEED PRESET  →  "safe" | "balanced" | "fast" | "aggressive"
# ============================================================
SPEED_PRESET = "fast"

SPEED_PRESETS = {
    # max_concurrent_pages: total in-flight HTTP requests at once
    # parallel_batch_size:  how many URLs run simultaneously
    # num_sessions:         Flipkart auth sessions in the pool
    "safe": {
        "num_sessions":          10,
        "max_concurrent_pages":  30,
        "parallel_batch_size":   20,
        "max_pages_per_url":     30,
        "telegram_workers":      15,
        "loop_delay":            20,
    },
    "balanced": {
        "num_sessions":          12,
        "max_concurrent_pages":  50,
        "parallel_batch_size":   40,
        "max_pages_per_url":     50,
        "telegram_workers":      20,
        "loop_delay":            60,
    },
    "fast": {
        "num_sessions":          15,
        "max_concurrent_pages":  120,
        "parallel_batch_size":   139,   # up to 60 URLs at once
        "max_pages_per_url":     8,
        "telegram_workers":      30,
        "loop_delay":            3,
    },
    "aggressive": {
        "num_sessions":          15,
        "max_concurrent_pages":  120,
        "parallel_batch_size":   139,  # all 139 URLs simultaneously
        "max_pages_per_url":     80,
        "telegram_workers":      30,
        "loop_delay":            900,
    },
}

_p = SPEED_PRESETS[SPEED_PRESET]

SCRAPER_CONFIG = {
    # Core tuning (all driven by preset above)
    "num_sessions":          _p["num_sessions"],
    "max_concurrent_pages":  _p["max_concurrent_pages"],
    "parallel_batch_size":   _p["parallel_batch_size"],
    "max_pages_per_url":     _p["max_pages_per_url"],
    "telegram_workers":      _p["telegram_workers"],
    "loop_delay":            _p["loop_delay"],

    # Files
    "links_file":            "links.txt",
    "database_path":         "data/products.db",
    "output_dir":            "data/output",
    "archive_db_path":       "data/products_archive.db",

    # Misc
    "min_products_per_page": 5,
    "stop_on_consecutive_empty": 2,
    "connection_pool_size":  200,
    "cache_ttl":             600,
}

# ============================================================
# USER AGENTS
# ============================================================
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.178 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.178 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.178 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.99 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-A525F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
]

# ============================================================
# FILTER / DUPLICATE CONFIG
# ============================================================
DUPLICATE_CONFIG = {
    "min_discount_new":      0,
    "min_discount_existing": 20,
    "min_change_percent":    5,
    "db_path":               "data/products.db",
}

# ============================================================
# SPAM FILTER
# ============================================================
SPAM_FILTER_CONFIG = {
    "block_sponsored":          True,
    "enable_brand_validation":  True,
    "spam_words": [
        "sponsored", "advertisement", "promo code", "limited time",
        "buy now", "hurry up", "flash sale", "exclusive offer",
        "refurbished", "open box", "damaged box",
        "unbranded", "generic", "duplicate", "imitation", "replica",
        "factory second", "b-grade", "c-grade",
        # Add your own below:
    ],
}

# ============================================================
# OUTPUT
# ============================================================
OUTPUT_CONFIG = {
    "telegram_format": "{emoji} {discount}% OFF | ₹{price} | ₹{mrp}\n{brand} {title}\n{url}",
}

# ============================================================
# FEATURES
# ============================================================
FEATURES = {
    "enable_scraping":               True,
    "enable_telegram_notifications": True,
    "enable_duplicate_filter":       True,
    "save_to_csv":                   False,
    "enable_storage":                True,
    "enable_duckdb_analytics":       False,
    "enable_spam_filter":            True,
}

# ============================================================
# HELPERS
# ============================================================

def get_discount_emoji(discount: int) -> str:
    if discount >= 90: return "🔥💎"
    if discount >= 70: return "🔥"
    if discount >= 50: return "⚡"
    return "✨"


def initialize_directories():
    os.makedirs("data", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs(SCRAPER_CONFIG["output_dir"], exist_ok=True)


def change_speed_preset(preset: str):
    global SPEED_PRESET, _p
    if preset not in SPEED_PRESETS:
        print(f"❌ Unknown preset. Choose from: {list(SPEED_PRESETS)}")
        return
    SPEED_PRESET = preset
    _p = SPEED_PRESETS[preset]
    for k in _p:
        SCRAPER_CONFIG[k] = _p[k]
    print(f"✅ Speed preset → {preset.upper()}")
    print_config()


def add_spam_word(word: str):
    w = word.lower()
    if w not in SPAM_FILTER_CONFIG['spam_words']:
        SPAM_FILTER_CONFIG['spam_words'].append(w)
        print(f"✅ Added: {w}")


def remove_spam_word(word: str):
    SPAM_FILTER_CONFIG['spam_words'] = [
        x for x in SPAM_FILTER_CONFIG['spam_words'] if x.lower() != word.lower()
    ]
    print(f"✅ Removed: {word}")


def print_config():
    perf = {
        "safe":       "~5-8 min / 139 URLs  | Very Low risk",
        "balanced":   "~3-5 min / 139 URLs  | Low risk",
        "fast":       "~2-3 min / 139 URLs  | Low risk  ← default",
        "aggressive": "~1-2 min / 139 URLs  | Medium risk ⚠️",
    }
    print(f"\n{'='*60}")
    print(f" CONFIG: {SPEED_PRESET.upper()} ".center(60, "="))
    print(f"{'='*60}")
    print(f"  Sessions         : {SCRAPER_CONFIG['num_sessions']}")
    print(f"  Concurrent reqs  : {SCRAPER_CONFIG['max_concurrent_pages']}")
    print(f"  Parallel URLs    : {SCRAPER_CONFIG['parallel_batch_size']}")
    print(f"  Max pages/URL    : {SCRAPER_CONFIG['max_pages_per_url']}")
    print(f"  Telegram workers : {SCRAPER_CONFIG['telegram_workers']}")
    print(f"  Expected speed   : {perf.get(SPEED_PRESET,'')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print_config()
else:
    print(f"⚙️  Config: {SPEED_PRESET.upper()} | "
          f"{SCRAPER_CONFIG['num_sessions']} sessions | "
          f"{SCRAPER_CONFIG['max_concurrent_pages']} concurrent | "
          f"{SCRAPER_CONFIG['parallel_batch_size']} parallel URLs")
