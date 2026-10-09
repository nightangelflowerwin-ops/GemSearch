import csv
import json
import re
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from KolscanDirectory import valid_address
from chains import address_key


SOURCE = 'https://dethective.com/kollector/'
MAX_BYTES = 20_000_000


def wallet_key(chain, address):
    if chain in ('sol', 'solana') and valid_address(address):
        return 'solana', address
    if chain == 'evm' and isinstance(address, str) and re.fullmatch(r'0x[0-9a-fA-F]{40}', address):
        return 'evm', address.lower()
    raise ValueError('A valid Solana or EVM wallet address is required')


def text(value, maximum=120):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError('Invalid directory text')
    return value.strip().replace(chr(0x2014), ':')


def query_key(query):
    query = text(query, 64).lstrip('@')
    return query if valid_address(query) else query.casefold()


def normalize_profiles(payload, source='KOLlector'):
    profiles = payload.get('profiles', [payload]) if isinstance(payload, dict) else payload
    if not isinstance(profiles, list) or len(profiles) > 100000:
        raise ValueError('Use a profile response or a list of directory records')
    rows = []
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError('Invalid directory record')
        if 'accounts' not in profile:
            key = wallet_key(profile.get('chain', 'solana'), profile.get('address', profile.get('wallet')))
            rows.append({'name': text(profile.get('name')), 'chain': key[0], 'address': key[1], 'handle': text(profile.get('handle', profile.get('name'))), 'platform': text(profile.get('platform', 'custom')), 'x_handle': str(profile.get('x_handle', '')).strip()[:64], 'proof': str(profile.get('proof', ''))[:120], 'x_link': str(profile.get('x_link', ''))[:120], 'source': source, 'built_at': str(profile.get('built_at', profile.get('captured', '')))[:64], 'tags': clean_tags(profile.get('tags', []))})
            continue
        accounts = profile['accounts']
        if not isinstance(accounts, list) or len(accounts) > 1000:
            raise ValueError('Invalid profile accounts')
        if not accounts:
            continue
        name = text(profile.get('name'))
        for account in accounts:
            if not isinstance(account, dict) or not isinstance(account.get('wallets'), list):
                raise ValueError('Invalid profile wallet list')
            for wallet in account['wallets']:
                if not isinstance(wallet, dict):
                    raise ValueError('Invalid wallet record')
                key = wallet_key(wallet.get('chain'), wallet.get('address'))
                rows.append({'name': name, 'chain': key[0], 'address': key[1], 'handle': text(account.get('handle')), 'platform': text(account.get('platform')), 'x_handle': str(account.get('x_handle') or '')[:64], 'proof': str(wallet.get('proof') or '')[:120], 'x_link': str(account.get('x_link') or '')[:120], 'source': source, 'built_at': str(profile.get('built_at') or '')[:64], 'tags': []})
        if len(rows) > 100000:
            raise ValueError('Directory exceeds 100,000 identity claims')
    return rows


def clean_tags(tags):
    if isinstance(tags, str):
        tags = tags.split(',')
    if not isinstance(tags, list) or len(tags) > 30:
        raise ValueError('Use up to 30 tags per wallet')
    return sorted({text(tag, 60) for tag in tags if isinstance(tag, str) and tag.strip()}, key=str.casefold)


def read_directory(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Directory files must be smaller than 20 MB')
    with path.open(encoding='utf-8-sig', newline='') as handle:
        payload = json.load(handle) if path.suffix.lower() == '.json' else list(csv.DictReader(handle))
    rows = normalize_profiles(payload, 'Imported')
    if not rows:
        raise ValueError('The directory contains no wallets')
    return rows


class KollectorClient:
    def __init__(self, opener=urlopen):
        self.opener = opener
        self.lock = threading.Lock()
        self.next_request = 0
        self.blocked_until = 0

    def lookup(self, query):
        query = text(query, 64).lstrip('@')
        with self.lock:
            if time.time() < self.blocked_until:
                raise ValueError('Directory provider cooldown is active')
            time.sleep(max(0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + 1
            request = Request(SOURCE + 'api/search?' + urlencode({'q': query, 'src': 'GemSearch'}), headers={'User-Agent': 'GemSearch', 'Accept': 'application/json', 'Referer': SOURCE})
            try:
                with self.opener(request, timeout=12) as response:
                    raw = response.read(MAX_BYTES + 1)
            except HTTPError as error:
                if error.code in (403, 429):
                    try:
                        cooldown = max(3600, min(86400, int(error.headers.get('Retry-After', 3600))))
                    except (TypeError, ValueError):
                        cooldown = 3600
                    self.blocked_until = time.time() + cooldown
                raise ValueError('Directory provider returned HTTP ' + str(error.code)) from None
            if len(raw) > MAX_BYTES:
                raise ValueError('Directory response exceeds the size limit')
            payload = json.loads(raw)
            if not isinstance(payload, dict) or 'accounts' not in payload:
                raise ValueError('Directory provider returned an invalid response')
            normalize_profiles(payload)
            return payload


class WalletDirectory:
    def __init__(self, store, client=None):
        self.store = store
        self.client = client or KollectorClient()
        with store.connect() as connection:
            connection.executescript('CREATE TABLE IF NOT EXISTS identity_claims(query TEXT,source TEXT,platform TEXT,handle TEXT,chain TEXT,address TEXT,payload TEXT,captured REAL,active INTEGER,PRIMARY KEY(query,source,platform,handle,chain,address)); CREATE INDEX IF NOT EXISTS identity_wallet ON identity_claims(chain,address,active); CREATE TABLE IF NOT EXISTS identity_queries(query TEXT PRIMARY KEY,checked REAL DEFAULT 0,attempted REAL DEFAULT 0,error TEXT); CREATE TABLE IF NOT EXISTS identity_tags(chain TEXT,address TEXT,payload TEXT,PRIMARY KEY(chain,address)); CREATE TABLE IF NOT EXISTS identity_coins(wallet_chain TEXT,wallet TEXT,token_chain TEXT,token TEXT,label TEXT,PRIMARY KEY(wallet_chain,wallet,token_chain,token));')

    def apply(self, rows, query, replace=False):
        query = query_key(query)
        now = time.time()
        with self.store.connect() as connection:
            if replace:
                connection.execute("UPDATE identity_claims SET active=0 WHERE query=? AND source='KOLlector'", (query,))
            for row in rows:
                wallet_key(row['chain'], row['address'])
                connection.execute('INSERT OR REPLACE INTO identity_claims VALUES (?,?,?,?,?,?,?,?,1)', (query, row['source'], row['platform'], row['handle'], row['chain'], row['address'], json.dumps(row), now))
            if replace:
                connection.execute('INSERT OR REPLACE INTO identity_queries VALUES (?,?,?,NULL)', (query, now, now))
        return len({(row['chain'], row['address']) for row in rows})

    def lookup(self, query):
        query = text(query, 64).lstrip('@')
        try:
            rows = normalize_profiles(self.client.lookup(query))
            return self.apply(rows, query, replace=True)
        except (OSError, ValueError) as error:
            with self.store.connect() as connection:
                connection.execute('INSERT INTO identity_queries(query,attempted,error) VALUES (?,?,?) ON CONFLICT(query) DO UPDATE SET attempted=excluded.attempted,error=excluded.error', (query_key(query), time.time(), str(error)[:200]))
            raise

    def import_file(self, path):
        return self.apply(read_directory(path), 'import')

    def set_tags(self, chain, address, tags):
        chain, address = wallet_key(chain, address)
        with self.store.connect() as connection:
            connection.execute('INSERT OR REPLACE INTO identity_tags VALUES (?,?,?)', (chain, address, json.dumps(clean_tags(tags))))

    def link_coin(self, wallet_chain, wallet, token_chain, token, label):
        wallet_chain, wallet = wallet_key(wallet_chain, wallet)
        if not address_key(token_chain, token) or (token_chain == 'solana' and not valid_address(token)):
            raise ValueError('Enter a valid token network and contract address')
        token = address_key(token_chain, token)[1]
        with self.store.connect() as connection:
            connection.execute('INSERT OR REPLACE INTO identity_coins VALUES (?,?,?,?,?)', (wallet_chain, wallet, token_chain, token, text(label, 80)))

    def rows(self):
        with self.store.connect() as connection:
            claims = [(json.loads(row[0]), row[1]) for row in connection.execute('SELECT payload,captured FROM identity_claims WHERE active=1 ORDER BY captured DESC')]
            tags = {(row[0], row[1]): json.loads(row[2]) for row in connection.execute('SELECT * FROM identity_tags')}
            coins = {}
            for row in connection.execute('SELECT * FROM identity_coins'):
                coins.setdefault((row[0], row[1]), []).append({'chain': row[2], 'address': row[3], 'label': row[4], 'relation': 'User label'})
        wallets = {}
        for claim, captured in claims:
            key = claim['chain'], claim['address']
            row = wallets.setdefault(key, {'name': claim['name'], 'address': key[1], 'chain': key[0], 'source': claim['source'], 'captured': time.strftime('%Y-%m-%d', time.gmtime(captured)), 'claims': [], 'aliases': [], 'tags': [], 'coins': coins.get(key, [])})
            row['claims'].append(claim)
            row['aliases'].extend([claim['name'], claim['handle'], claim['x_handle']])
            row['tags'].extend([claim['platform'], *claim.get('tags', [])])
        for key, row in wallets.items():
            row['aliases'] = sorted(set(filter(None, row['aliases'])), key=str.casefold)
            row['tags'] = sorted(set(row['tags'] + tags.get(key, [])), key=str.casefold)
            row['evidence'] = 'Source attributed' if any(claim['source'] == 'KOLlector' and claim['proof'] for claim in row['claims']) else 'Saved attribution' if any(claim['source'] == 'Kolscan' for claim in row['claims']) else 'Imported claim'
            row['identity_verified'] = False
        return list(wallets.values())

    def refresh_one(self, active=lambda: True):
        if not active():
            return False
        with self.store.connect() as connection:
            row = connection.execute('SELECT query FROM identity_queries WHERE checked<? AND attempted<? ORDER BY checked,attempted LIMIT 1', (time.time() - 86400, time.time() - 3600)).fetchone()
        if row and active():
            self.lookup(row[0])
            return True
        return False

    def work(self, stop, active):
        while not stop.wait(15):
            if active():
                try:
                    self.refresh_one(active)
                except (OSError, ValueError):
                    pass
