#!/usr/bin/env python3
"""Feed fictional posts to a running local engine so Discovery shows every signal type.

For demos and screen recordings. Handles, ticker and address are invented;
the address is a valid-format key derived from a hash, not a real token.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def sample_address():
    raw = hashlib.sha256(b'gem-search sample address').digest()
    number, out = int.from_bytes(raw, 'big'), ''
    while number:
        number, rest = divmod(number, 58)
        out = BASE58[rest] + out
    return '1' * (len(raw) - len(raw.lstrip(b'\0'))) + out


def sample_posts(now=None):
    now = now or time.time()
    address = sample_address()
    posts = []

    def add(author, text, hours_ago, links=()):
        stamp = datetime.fromtimestamp(now - hours_ago * 3600, timezone.utc).isoformat()
        posts.append({'url': f'https://x.com/{author}/status/{1900000000000000000 + len(posts)}',
                      'created_at': stamp, 'text': text + ' (sample)', 'links': list(links)})

    # A young narrative: two early mentions, then a burst in the last hours.
    add('sample_early_1', 'first time seeing rainbow spiders on the timeline, $WEBZ', 11)
    add('sample_early_2', 'rainbow spiders again? someone made $WEBZ', 14)
    for i in range(6):
        add(f'sample_scout_{i}', f'rainbow spiders are crawling everywhere. $WEBZ CA {address} take {i}',
            0.4 + i * 0.5, ['https://webz.example/'])
    for i in range(5):
        add(f'sample_dev_{i}', f'Open-source AI agent framework ships build {i}', 1 + i * 2, ['https://agents.example/'])
    for i in range(3):
        add(f'sample_lab_{i}', f'Quantum telescope paper number {i}', 16 + i)
    return posts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    key = (ROOT / 'data' / 'extension-key').read_text().strip()
    posts = sample_posts()
    for start in range(0, len(posts), 20):
        request = Request(f'http://127.0.0.1:{args.port}/api/extension/ingest',
                          json.dumps({'posts': posts[start:start + 20]}).encode(),
                          {'Content-Type': 'application/json', 'X-Gem-Extension': key})
        with urlopen(request, timeout=10) as response:
            print(response.read().decode())
    print('Sample posts queued. The spider loop picks them up within ~10 seconds.')


if __name__ == '__main__':
    main()
