import tempfile
from itertools import permutations
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from alerts import TokenAlerts
from DesktopStore import DesktopStore
from DexMonitor import DexMonitor, select_pairs
from DataQuality import current_cap, mint_status


ADDRESS = 'So11111111111111111111111111111111111111112'


def pair(liquidity=10000, cap=50000):
    return {'chainId': 'solana', 'baseToken': {'address': ADDRESS, 'name': 'Fixture'}, 'pairAddress': 'pair', 'priceUsd': '0.00000042', 'marketCap': cap, 'fdv': 900000, 'liquidity': {'usd': liquidity}, 'volume': {'m5': 200000, 'h24': 400000}, 'txns': {'m5': {'buys': 100, 'sells': 1}}, 'pairCreatedAt': 1700000000000}


class DexMonitorTests(unittest.TestCase):
    def test_most_liquid_pair_and_no_fabricated_metrics(self):
        result = select_pairs([pair(10, 100000), pair(100, None)], {ADDRESS}, time.time())[ADDRESS]
        self.assertIsNone(result['market_cap_usd'])
        self.assertIsNone(result['net_inflow_m5_usd'])
        self.assertIsNone(result['volume_m1_usd'])
        self.assertIsNone(result['token_created_at'])
        self.assertEqual(result['price_usd'], 0.00000042)
        self.assertEqual(result['buy_count_m5'], 100)

    def test_active_pool_metrics_stay_consistent_in_every_response_order(self):
        active = dict(pair(28203.32, 140567), pairAddress='active-pool', priceUsd='0.0001405', volume={'m5': 5000, 'h24': 1100000}, txns={'m5': {'buys': 120, 'sells': 75}})
        pools = [
            dict(pair(), pairAddress='old-pool', marketCap=28363.41, liquidity=None),
            dict(pair(1753.08, 146249), pairAddress='small-pool'),
            dict(pair(0.54, 145210), pairAddress='dust-pool'),
            dict(pair(999999, 9999999), chainId='base', pairAddress='wrong-chain'),
            active,
        ]
        for response in permutations(pools):
            with self.subTest(order=[p['pairAddress'] for p in response]):
                selected = select_pairs(list(response), {ADDRESS}, time.time())[ADDRESS]
                self.assertEqual(selected['market_pair'], 'active-pool')
                self.assertEqual(selected['market_cap_usd'], 140567)
                self.assertEqual(selected['price_usd'], 0.0001405)
                self.assertEqual(selected['liquidity_usd'], 28203.32)
                self.assertEqual(selected['volume_h24_usd'], 1100000)
                self.assertEqual(selected['buy_count_m5'], 120)
                self.assertEqual(selected['sell_count_m5'], 75)

    def test_scanner_excludes_missing_zero_and_below_minimum_pool_liquidity(self):
        from TokenFilters import DEFAULTS, matches
        for liquidity in [None, 0, 9999.99, 10000]:
            with self.subTest(liquidity=liquidity):
                selected = select_pairs([pair(liquidity, 50000)], {ADDRESS}, time.time())[ADDRESS]
                selected.update(chain='solana', address=ADDRESS)
                self.assertEqual(matches(selected, DEFAULTS), liquidity == 10000)

    def test_scanner_replaces_old_pool_with_active_pool(self):
        from TokenFilters import DEFAULTS, matches
        from TokenLookup import lookup_token
        old = dict(pair(), pairAddress='old-pool', marketCap=28363.41, liquidity=None)
        active = dict(pair(28203.32, 140567), pairAddress='active-pool')
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopStore(directory)
            store.record('solana', ADDRESS, {'name': 'Fixture', 'market_pair': 'old-pool', 'market_cap_usd': 28363.41})
            monitor = DexMonitor(TokenAlerts(store.connect), store.record, store.watchlist, store.tokens)
            monitor.discovery_at = time.monotonic()
            monitor.control(True)
            with patch('DexMonitor.request', return_value={'pairs': [old, active]}) as fetch, patch('DexMonitor.solana_supplies', return_value={}):
                monitor.poll()
                fetch.assert_called_once_with('latest/dex/tokens/' + ADDRESS)
            record = store.tokens()[0]
            self.assertEqual(record['market_pair'], 'active-pool')
            self.assertEqual(record['market_cap_usd'], 140567)
            self.assertTrue(matches(record, DEFAULTS))
            lookup = lookup_token(ADDRESS, fetch=lambda path: [old, active], verify_solana=lambda addresses: {})[0]
            self.assertEqual(lookup['market_pair'], record['market_pair'])
            self.assertEqual(lookup['market_cap_usd'], record['market_cap_usd'])

    def test_public_feed_to_store_and_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopStore(Path(directory))
            alerts = TokenAlerts(store.connect)
            monitor = DexMonitor(alerts, store.record, store.watchlist, store.tokens)
            monitor.control(True)
            sample = {'onchain_supply_sampled_at': time.time(), 'onchain_decimals': 9, 'onchain_supply': 1000}
            def response(path):
                return {'pairs': [pair()]} if path.startswith('latest/dex/tokens/') else [{'chainId': 'solana', 'tokenAddress': ADDRESS}]
            with patch('DexMonitor.request', side_effect=response) as request, patch('DexMonitor.solana_supplies', return_value={ADDRESS: sample}):
                monitor.poll()
                self.assertEqual(len(store.tokens()), 1)
                self.assertEqual(current_cap(store.tokens()[0]), 50000)
                self.assertEqual(mint_status(store.tokens()[0]), 'confirmed')
                self.assertEqual(alerts.recent(), [])
                count = request.call_count
                monitor.last_poll = 0
                monitor.control(False)
                monitor.poll()
                self.assertEqual(request.call_count, count)

    def test_stop_during_request_prevents_write(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopStore(directory)
            monitor = DexMonitor(TokenAlerts(store.connect), store.record, store.watchlist, store.tokens)
            monitor.discovered = [ADDRESS]
            monitor.discovery_at = time.monotonic()
            monitor.control(True)
            def response(path):
                monitor.control(False)
                return [pair()]
            with patch('DexMonitor.request', side_effect=response):
                monitor.poll()
            self.assertEqual(store.tokens(), [])
