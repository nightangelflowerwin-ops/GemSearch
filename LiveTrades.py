import json
import math
import threading
import time
from decimal import Decimal
from websockets.sync.client import connect
from MeteoraSwaps import SOL, USDC, decode_swaps
from WalletIngestion import rpc
from DexMonitor import request, select_pairs


class LiveTrades:
    def __init__(self, store, alerts=None, fetch=rpc):
        self.store = store
        self.alerts = alerts
        self.fetch = fetch
        self.lock = threading.Lock()
        self.state = {'connected': False, 'pools': 0, 'error': None, 'last_event': None, 'received': 0}
        self.coverage = {}
        self.reference = None
        self.reference_at = 0
        self.backfill_at = 0
        with store.connect() as con:
            con.executescript('CREATE TABLE IF NOT EXISTS live_queue(signature TEXT,pool TEXT,state TEXT DEFAULT "pending",attempts INTEGER DEFAULT 0,retry_at REAL DEFAULT 0,PRIMARY KEY(signature,pool)); CREATE TABLE IF NOT EXISTS live_trades(signature TEXT,event_index INTEGER,pool TEXT,address TEXT,captured REAL,payload TEXT,PRIMARY KEY(signature,event_index)); CREATE INDEX IF NOT EXISTS live_trade_pool_time ON live_trades(pool,captured); CREATE TABLE IF NOT EXISTS live_cursors(pool TEXT PRIMARY KEY,tip TEXT);')
            columns = {row[1] for row in con.execute('PRAGMA table_info(live_cursors)')}
            for column in ['before_signature', 'pending_tip']:
                if column not in columns:
                    con.execute('ALTER TABLE live_cursors ADD COLUMN ' + column + ' TEXT')

    def pools(self):
        watched = {address for chain, address in self.store.watchlist() if chain == 'solana'}
        rows = [row for row in self.store.tokens() if row.get('chain') == 'solana' and row.get('dex_id') == 'meteora' and 'dyn2' in [str(label).lower() for label in row.get('pair_labels', [])] and row.get('market_pair')]
        selected = self.store.get('live_trade_token', '')
        rows.sort(key=lambda row: (row['address'] != selected, row['address'] not in watched, -(row.get('liquidity_usd') or 0)))
        return {row['market_pair']: row['address'] for row in rows[:5]}

    def enqueue(self, signature, pool, failed=False):
        if not isinstance(signature, str) or not 64 <= len(signature) <= 100:
            raise ValueError('Invalid transaction signature')
        with self.store.connect() as con:
            con.execute('INSERT OR IGNORE INTO live_queue(signature,pool,state) VALUES (?,?,?)', (signature, pool, 'failed' if failed else 'pending'))

    def notification(self, message, subscriptions):
        if message.get('method') != 'logsNotification':
            return
        params = message.get('params', {})
        pool = subscriptions.get(params.get('subscription'))
        value = params.get('result', {}).get('value', {})
        if pool:
            self.enqueue(value.get('signature'), pool, value.get('err') is not None)
            with self.lock:
                self.state['last_event'] = time.time()
                self.state['received'] += 1

    def listen(self, stop, active):
        delay = 1
        while not stop.is_set():
            if not active() or not self.pools():
                with self.lock:
                    self.state.update(connected=False, pools=0)
                    self.coverage.clear()
                stop.wait(1)
                continue
            try:
                pools = self.pools()
                with connect('wss://solana-rpc.publicnode.com', open_timeout=10, close_timeout=2, ping_interval=15, ping_timeout=15, max_size=1000000, max_queue=256, proxy=None) as socket:
                    subscriptions = {}
                    pending = {}
                    for identity, pool in enumerate(pools, 1):
                        pending[identity] = pool
                        socket.send(json.dumps({'jsonrpc': '2.0', 'id': identity, 'method': 'logsSubscribe', 'params': [{'mentions': [pool]}, {'commitment': 'confirmed'}]}))
                    with self.lock:
                        self.state.update(connected=False, pools=len(pools), error=None)
                    delay = 1
                    checked = time.monotonic()
                    while not stop.is_set() and active():
                        if time.monotonic() - checked >= 10:
                            if pools != self.pools():
                                break
                            checked = time.monotonic()
                        try:
                            message = json.loads(socket.recv(timeout=1))
                        except TimeoutError:
                            if pending and time.monotonic() - checked >= 8:
                                raise ValueError('Stream subscription acknowledgement timed out')
                            continue
                        if 'error' in message:
                            raise ValueError('Stream subscription rejected')
                        if message.get('id') in pending:
                            subscription = message.get('result')
                            if type(subscription) is not int:
                                raise ValueError('Invalid subscription response')
                            pool = pending.pop(message['id'])
                            subscriptions[subscription] = pool
                            with self.lock:
                                self.coverage[pool] = time.time()
                                self.state['connected'] = not pending
                        else:
                            self.notification(message, subscriptions)
            except Exception as error:
                with self.lock:
                    self.state['error'] = 'Live connection delayed: ' + type(error).__name__
                stop.wait(delay)
                delay = min(delay * 2, 30)
            finally:
                with self.lock:
                    self.state['connected'] = False
                    self.coverage.clear()

    def backfill(self, pool, active):
        with self.store.connect() as con:
            previous = con.execute('SELECT * FROM live_cursors WHERE pool=?', (pool,)).fetchone()
        cursor = dict(previous) if previous else {}
        tip = cursor.get('tip')
        options = {'commitment': 'confirmed', 'limit': 100 if tip else 25}
        if tip:
            options['until'] = tip
        if cursor.get('before_signature'):
            options['before'] = cursor['before_signature']
        newest = cursor.get('pending_tip')
        for page in range(10):
            if not active():
                return
            rows = self.fetch('getSignaturesForAddress', [pool, options])
            if not isinstance(rows, list):
                raise ValueError('Invalid backfill response')
            if newest is None and rows:
                newest = rows[0]['signature']
            for row in rows:
                self.enqueue(row['signature'], pool, row.get('err') is not None)
            if not tip or len(rows) < 100:
                if newest:
                    with self.store.connect() as con:
                        con.execute('INSERT OR REPLACE INTO live_cursors(pool,tip,before_signature,pending_tip) VALUES (?,?,NULL,NULL)', (pool, newest))
                return
            options['before'] = rows[-1]['signature']
            with self.store.connect() as con:
                con.execute('INSERT OR REPLACE INTO live_cursors(pool,tip,before_signature,pending_tip) VALUES (?,?,?,?)', (pool, tip, options['before'], newest))
        with self.lock:
            self.coverage.pop(pool, None)
            self.state['error'] = 'Live history backlog; recovery continues on next pass'

    def process(self, signature, pool):
        try:
            transaction = self.fetch('getTransaction', [signature, {'encoding': 'jsonParsed', 'commitment': 'confirmed', 'maxSupportedTransactionVersion': 1}])
            if transaction is None:
                raise ValueError('Transaction not available yet')
            if not isinstance(transaction, dict) or not isinstance(transaction.get('meta'), dict):
                raise ValueError('Invalid transaction response')
            trades = decode_swaps(transaction, signature, self.pools())
            with self.store.connect() as con:
                for trade in trades:
                    trade['received_at'] = time.time()
                    reference = self.reference if self.reference and 0 <= time.time() - self.reference[1] <= 120 else None
                    trade['quote_usd'] = str(reference[0]) if reference and trade['quote_mint'] == SOL and 0 <= time.time() - trade['event_time'] <= 60 else None
                    con.execute('INSERT OR IGNORE INTO live_trades VALUES (?,?,?,?,?,?)', (signature, trade['event_index'], trade['pool'], trade['address'], trade['event_time'], json.dumps(trade)))
                con.execute('UPDATE live_queue SET state=? WHERE signature=? AND pool=?', ('failed' if transaction.get('meta', {}).get('err') is not None else 'complete', signature, pool))
        except (OSError, ValueError, KeyError, TypeError) as error:
            with self.store.connect() as con:
                con.execute('UPDATE live_queue SET attempts=attempts+1,retry_at=? WHERE signature=? AND pool=?', (time.time() + 5, signature, pool))
            with self.lock:
                self.state['error'] = 'Trade decoding delayed: ' + type(error).__name__

    def finalize(self, active):
        pools = self.pools()
        if not pools:
            return
        with self.store.connect() as con:
            placeholders = ','.join('?' for pool in pools)
            rows = con.execute("SELECT signature FROM live_trades WHERE captured<? AND json_extract(payload,'$.confirmation')='confirmed' AND pool IN (" + placeholders + ") GROUP BY signature LIMIT 4", [time.time() - 40, *pools]).fetchall()
        for row in rows:
            if not active():
                return
            transaction = self.fetch('getTransaction', [row[0], {'encoding': 'jsonParsed', 'commitment': 'finalized', 'maxSupportedTransactionVersion': 1}])
            if transaction is None:
                continue
            trades = decode_swaps(transaction, row[0], self.pools())
            with self.store.connect() as con:
                saved = {event[0]: json.loads(event[1]) for event in con.execute('SELECT event_index,payload FROM live_trades WHERE signature=?', (row[0],))}
            with self.store.connect() as con:
                con.execute('DELETE FROM live_trades WHERE signature=?', (row[0],))
                for trade in trades:
                    trade['confirmation'] = 'finalized'
                    trade['quote_usd'] = saved.get(trade['event_index'], {}).get('quote_usd')
                    con.execute('INSERT OR REPLACE INTO live_trades VALUES (?,?,?,?,?,?)', (row[0], trade['event_index'], trade['pool'], trade['address'], trade['event_time'], json.dumps(trade)))

    def usd_reference(self):
        now = time.time()
        if now - self.reference_at >= 60:
            self.reference_at = now
            try:
                pairs = request('token-pairs/v1/solana/' + SOL)
                row = select_pairs(pairs, {SOL}, now).get(SOL, {})
                price = row.get('price_usd')
                if price and math.isfinite(price):
                    self.reference = (Decimal(str(price)), now)
            except (OSError, ValueError):
                pass
        return self.reference if self.reference and now - self.reference[1] <= 120 else None

    def snapshot(self):
        with self.store.connect() as con:
            trades = [json.loads(row[0]) for row in con.execute('SELECT payload FROM live_trades ORDER BY captured DESC,event_index DESC LIMIT 100')]
            queued = con.execute("SELECT COUNT(*) FROM live_queue WHERE state='pending'").fetchone()[0]
        with self.lock:
            state = dict(self.state)
            coverage = dict(self.coverage)
        for trade in trades:
            rate = Decimal(trade['quote_usd']) if trade.get('quote_usd') else None
            trade['quote_symbol'] = 'SOL' if trade['quote_mint'] == SOL else 'USDC'
            trade['value_usd'] = float(Decimal(trade['quote_amount']) * rate) if rate else None
        return {'status': state, 'queued': queued, 'trades': trades, 'coverage': coverage}

    def metrics(self, pool, now=None):
        now = time.time() if now is None else now
        with self.store.connect() as con:
            rows = [json.loads(row[0]) for row in con.execute('SELECT payload FROM live_trades WHERE pool=? AND captured>=? AND captured<=?', (pool, now - 345, now - 45))]
            pending = con.execute("SELECT COUNT(*) FROM live_queue WHERE pool=? AND state='pending'", (pool,)).fetchone()[0]
        with self.lock:
            since = self.coverage.get(pool)
        complete = since is not None and now - since >= 345 and pending == 0
        net = Decimal(0)
        for row in rows:
            if row['confirmation'] != 'finalized' or not row.get('quote_usd'):
                complete = False
                continue
            value = Decimal(row['quote_amount']) * Decimal(row['quote_usd'])
            net += value if row['side'] == 'Buy' else -value
        return {'complete': complete, 'net_usd': float(net) if complete else None, 'buys': sum(row['side'] == 'Buy' for row in rows), 'sells': sum(row['side'] == 'Sell' for row in rows)}

    def work(self, stop, active):
        while not stop.wait(0.5):
            if not active():
                continue
            try:
                pools = self.pools()
                if not pools:
                    continue
                if time.monotonic() - self.backfill_at >= 30:
                    self.backfill_at = time.monotonic()
                    for pool in pools:
                        if not active():
                            break
                        self.backfill(pool, active)
                with self.store.connect() as con:
                    placeholders = ','.join('?' for pool in pools)
                    query = "SELECT signature,pool FROM live_queue WHERE state='pending' AND retry_at<=? AND pool IN (" + placeholders + ") ORDER BY rowid "
                    newest = con.execute(query + 'DESC LIMIT 1', [time.time(), *pools]).fetchall()
                    oldest = con.execute(query + 'ASC LIMIT 1', [time.time(), *pools]).fetchall()
                    rows = list(dict.fromkeys(tuple(row) for row in newest + oldest))
                self.usd_reference()
                for signature, pool in rows:
                    if active():
                        self.process(signature, pool)
                self.finalize(active)
                self.usd_reference()
                for pool, address in pools.items():
                    metric = self.metrics(pool)
                    self.store.record('solana', address, {'live_net_inflow_m5_usd': metric['net_usd'], 'live_flow_updated_at': time.time(), 'live_flow_complete': metric['complete']})
                    if self.alerts and metric['complete'] and active():
                        self.alerts.evaluate('solana', address, {'net_inflow_m5_usd': metric['net_usd'], 'source': 'Live finalized swaps'})
            except Exception as error:
                with self.lock:
                    self.state['error'] = 'Live processing delayed: ' + type(error).__name__
