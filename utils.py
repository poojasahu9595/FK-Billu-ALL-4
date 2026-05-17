"""
Utils
"""

import csv
from typing import List, Dict


def load_urls(file: str = "links.txt") -> List[str]:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            urls = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if line.startswith('http') or line.startswith('/'):
                        urls.append(line)
            return urls
    except:
        with open(file, 'w') as f:
            f.write("# Add URLs here\n")
        return []


def save_csv(products: List[Dict], filename: str):
    if not products:
        return
    
    try:
        fields = ['product_id', 'listing_id', 'brand', 'title', 'current_price', 'original_price', 'discount', 'url', 'scraped_at']
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(products)
        
        print(f"💾 Saved {len(products)} to {filename}")
    except:
        pass


def format_time(sec: int) -> str:
    if sec < 60:
        return f"{sec}s"
    elif sec < 3600:
        return f"{sec//60}m {sec%60}s"
    else:
        return f"{sec//3600}h {(sec%3600)//60}m"
