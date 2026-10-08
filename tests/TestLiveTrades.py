import copy
import json
import struct
import tempfile
import time
import unittest
from decimal import Decimal
from DesktopStore import DesktopStore
from LiveTrades import LiveTrades
from MeteoraSwaps import PROGRAM, SOL, EVENT, SWAPS, encode58, decode58, decode_swaps


POOL = encode58(bytes([2]) * 32)
BASE = encode58(bytes([3]) * 32)
WALLET = encode58(bytes([4]) * 32)
SIGNATURE = encode58(bytes([5]) * 64)


def fixture(direction=0, timestamp=1000):
    event = EVENT + decode58(POOL) + bytes([direction, 0, 0]) + bytes(17) + bytes(32) + (2 ** 64).to_bytes(16, 'little') + bytes(32) + struct.pack('<QQQQQQ', 2000000, 1000000, 900000, timestamp, 10000000, 20000000)
    swap = {'programId': PROGRAM, 'accounts': [WALLET, POOL, WALLET, WALLET, WALLET, WALLET, BASE, SOL, WALLET], 'data': encode58(sorted(SWAPS)[0])}
    return {'slot': 42, 'blockTime': timestamp, 'transaction': {'signatures': [SIGNATURE], 'message': {'instructions': [swap]}}, 'meta': {'err': None, 'preTokenBalances': [{'mint': BASE, 'uiTokenAmount': {'decimals': 6}}], 'postTokenBalances': [], 'innerInstructions': [{'index': 0, 'instructions': [{'programId': PROGRAM, 'data': encode58(event)}]}]}}


class DecoderTests(unittest.TestCase):
    def test_sell_uses_net_output_and_exact_decimals(self):
        row = decode_swaps(fixture(), SIGNATURE, {POOL: BASE})[0]
        self.assertEqual(row['side'], 'Sell')
        self.assertEqual(Decimal(row['base_amount']), Decimal('2'))
        self.assertEqual(Decimal(row['quote_amount']), Decimal('.0009'))
        self.assertEqual(Decimal(row['price_quote']), Decimal('.001'))
        self.assertEqual(row['wallet'], WALLET)

    def test_buy_reverses_amounts(self):
        row = decode_swaps(fixture(1), SIGNATURE, {POOL: BASE})[0]
        self.assertEqual(row['side'], 'Buy')
        self.assertEqual(Decimal(row['base_amount']), Decimal('.9'))
        self.assertEqual(Decimal(row['quote_amount']), Decimal('.002'))

    def test_failed_transaction_is_not_trade(self):
        transaction = fixture()
        transaction['meta']['err'] = {'InstructionError': [0, 'Failed']}
        self.assertEqual(decode_swaps(transaction, SIGNATURE, {POOL: BASE}), [])

    def test_untracked_pool_is_not_trade(self):
        self.assertEqual(decode_swaps(fixture(), SIGNATURE, {}), [])

    def test_missing_event_fails_closed(self):
        transaction = fixture()
        transaction['meta']['innerInstructions'] = []
        with self.assertRaises(ValueError):
            decode_swaps(transaction, SIGNATURE, {POOL: BASE})

    def test_signature_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            decode_swaps(fixture(), encode58(bytes([6]) * 64), {POOL: BASE})

    def test_inconsistent_decimals_rejected(self):
        transaction = fixture()
        transaction['meta']['postTokenBalances'] = [{'mint': BASE, 'uiTokenAmount': {'decimals': 9}}]
        with self.assertRaises(ValueError):
            decode_swaps(transaction, SIGNATURE, {POOL: BASE})

    def test_multiple_swaps_have_distinct_event_indices(self):
        transaction = fixture()
        transaction['transaction']['message']['instructions'].append(copy.deepcopy(transaction['transaction']['message']['instructions'][0]))
        group = copy.deepcopy(transaction['meta']['innerInstructions'][0])
        group['index'] = 1
        transaction['meta']['innerInstructions'].append(group)
        self.assertEqual([row['event_index'] for row in decode_swaps(transaction, SIGNATURE, {POOL: BASE})], [0, 1])


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = DesktopStore(self.directory.name)
        self.store.record('solana', BASE, {'dex_id': 'meteora', 'pair_labels': ['DYN2'], 'market_pair': POOL, 'liquidity_usd': 20000})
        self.transaction = fixture(timestamp=int(time.time()) - 50)
        self.calls = []
        def fetch(method, params):
            self.calls.append((method, params))
            return self.transaction if method == 'getTransaction' else []
        self.collector = LiveTrades(self.store, fetch=fetch)

    def tearDown(self):
        self.directory.cleanup()

    def test_queue_and_trade_duplicates_are_idempotent(self):
        self.collector.enqueue(SIGNATURE, POOL)
        self.collector.enqueue(SIGNATURE, POOL)
        self.collector.reference = (Decimal('100'), time.time())
        self.collector.process(SIGNATURE, POOL)
        self.collector.process(SIGNATURE, POOL)
        self.assertEqual(len(self.collector.snapshot()['trades']), 1)
        self.assertEqual(self.collector.snapshot()['queued'], 0)

    def test_finalization_preserves_captured_quote(self):
        self.collector.enqueue(SIGNATURE, POOL)
        self.collector.reference = (Decimal('100'), time.time())
        self.collector.process(SIGNATURE, POOL)
        self.collector.reference = (Decimal('200'), time.time())
        self.collector.finalize(lambda: True)
        row = self.collector.snapshot()['trades'][0]
        self.assertEqual(row['confirmation'], 'finalized')
        self.assertAlmostEqual(row['value_usd'], .09)
        self.collector.coverage[POOL] = time.time() - 400
        self.assertAlmostEqual(self.collector.metrics(POOL)['net_usd'], -.09)

    def test_warmup_prevents_partial_net_flow(self):
        self.collector.coverage[POOL] = time.time() - 30
        self.assertIsNone(self.collector.metrics(POOL)['net_usd'])

    def test_pending_transactions_prevent_zero_flow(self):
        self.collector.coverage[POOL] = time.time() - 400
        self.collector.enqueue(SIGNATURE, POOL)
        self.assertFalse(self.collector.metrics(POOL)['complete'])

    def test_missing_price_prevents_usd_claim(self):
        self.collector.enqueue(SIGNATURE, POOL)
        self.collector.process(SIGNATURE, POOL)
        self.collector.finalize(lambda: True)
        self.collector.coverage[POOL] = time.time() - 400
        self.assertIsNone(self.collector.metrics(POOL)['net_usd'])

    def test_stop_prevents_recovery_network_calls(self):
        self.collector.backfill(POOL, lambda: False)
        self.collector.finalize(lambda: False)
        self.assertEqual(self.calls, [])

    def test_unavailable_transaction_is_retained_for_retry(self):
        self.transaction = None
        self.collector.enqueue(SIGNATURE, POOL)
        self.collector.process(SIGNATURE, POOL)
        self.assertEqual(self.collector.snapshot()['queued'], 1)
        with self.store.connect() as connection:
            row = connection.execute('SELECT attempts,retry_at FROM live_queue').fetchone()
        self.assertEqual(row[0], 1)
        self.assertGreater(row[1], time.time())

    def test_backfill_checkpoint_survives_restart(self):
        tip = encode58(bytes([7]) * 64)
        with self.store.connect() as connection:
            connection.execute('INSERT INTO live_cursors(pool,tip) VALUES (?,?)', (POOL, tip))
        signatures = [encode58(index.to_bytes(64, 'little')) for index in range(1, 1001)]
        pages = [[{'signature': signature, 'err': None} for signature in signatures[index:index + 100]] for index in range(0, 1000, 100)]
        self.collector.fetch = lambda method, params: pages.pop(0)
        self.collector.backfill(POOL, lambda: True)
        restored = LiveTrades(self.store, fetch=lambda method, params: self.calls.append(params) or [])
        restored.backfill(POOL, lambda: True)
        self.assertEqual(self.calls[-1][1]['before'], signatures[-1])
        with self.store.connect() as connection:
            row = connection.execute('SELECT tip,before_signature FROM live_cursors').fetchone()
        self.assertEqual(tuple(row), (signatures[0], None))

    def test_desktop_shows_live_trade_amounts_and_price(self):
        from PySide6.QtWidgets import QApplication
        from desktop import DesktopWindow
        application = QApplication.instance() or QApplication([])
        self.collector.enqueue(SIGNATURE, POOL)
        self.collector.process(SIGNATURE, POOL)
        window = DesktopWindow(self.store, background=False)
        try:
            window.refresh()
            model = window.live_table.model()
            self.assertEqual(model.rowCount(), 1)
            self.assertEqual(model.data(model.index(0, 2)), 'Sell')
            self.assertIn('SOL', model.data(model.index(0, 5)))
            self.assertEqual(window.tabs.tabText(window.tabs.indexOf(window.live_table.parentWidget())), 'Live trades')
        finally:
            window.close()
            application.processEvents()


if __name__ == '__main__':
    unittest.main()
