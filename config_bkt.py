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
        "8387836965:AAEjNrFO3C4fhu4SSTrJhfWizZahz4D5C30",
        "8216473425:AAF5-hWJtK_hFJeaez-VH_VMfQGC290ye9k",
        "7762202885:AAGIdNd0zWwh-gT-ALVL9mJyJT4nrL-e4DQ",
        "8004897278:AAE6Fp4_XkKZyPnb-GwrRFyQThC1zwP5ixY",
        "8371602197:AAGZUDZq0-HjYXxk8JFx_JrRd-NfpIQEpH0",
        "8261499779:AAHsCrjl3lrnZtHmhPhtzJwX4o3naMeu0U0",
        "8203838078:AAG84Pr2Q363QwsJqTXUa_dTChsLG3IOsy0",
        "8023610574:AAFJHBVAKbTWuIUwWmJvGhsWRw89P_2fdFc",
        "8478467059:AAGpUP3hGSAZNH5CK_SCn6mGS9mY1dtCsAA",
        "8450932401:AAGzHp2KuVC43gp_kpqvW0yonSjyahljQDI",
    ],
    "chat_channels": {
        "all":    "-1003736885960",
        "70plus": "-1003098460680",
        "90plus": "-1003082104501",
    },
    "chat_id": "-1003736885960",
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
        "max_concurrent_pages":  80,
        "parallel_batch_size":   60,   # up to 60 URLs at once
        "max_pages_per_url":     60,
        "telegram_workers":      25,
        "loop_delay":            20,
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
