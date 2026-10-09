import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError
from DesktopStore import DesktopStore
from KollectorDirectory import WalletDirectory, KollectorClient, normalize_profiles, read_directory, wallet_key
from MeteoraSwaps import encode58


ADDRESS = encode58(bytes([8]) * 32)
TOKEN = encode58(bytes([9]) * 32)


def profile(name='example', address=ADDRESS):
    return {'name': name, 'built_at': '2026-10-04T12:00:00Z', 'accounts': [{'platform': 'pump', 'handle': name, 'x_handle': 'ExampleX', 'x_link': 'pump_stated', 'wallets': [{'chain': 'sol', 'address': address, 'proof': 'pump_profile'}]}]}


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = DesktopStore(self.temporary.name)
        self.client = Mock()
        self.directory = WalletDirectory(self.store, self.client)

    def tearDown(self):
        self.temporary.cleanup()

    def test_source_attribution_is_not_independent_verification(self):
        self.client.lookup.return_value = profile()
        self.directory.lookup('@example')
        row = self.directory.rows()[0]
        self.assertEqual(row['evidence'], 'Source attributed')
        self.assertFalse(row['identity_verified'])
        self.assertIn('ExampleX', row['aliases'])
        self.assertEqual(row['claims'][0]['proof'], 'pump_profile')

    def test_5000_unique_wallets_import_without_duplication(self):
        records = [{'name': 'Person ' + str(index), 'address': encode58(index.to_bytes(32, 'big')), 'tags': ['research']} for index in range(1, 5001)]
        path = Path(self.temporary.name) / 'Directory.json'
        path.write_text(json.dumps(records), encoding='utf-8')
        self.assertEqual(self.directory.import_file(path), 5000)
        self.directory.import_file(path)
        rows = self.directory.rows()
        self.assertEqual(len(rows), 5000)
        self.assertTrue(all(not row['identity_verified'] for row in rows))
        from PySide6.QtWidgets import QApplication
        from desktop import KOLWalletPage
        application = QApplication.instance() or QApplication([])
        page = KOLWalletPage(self.temporary.name)
        page.search.setText('research')
        self.assertIn('5000 matching', page.count.text())
        self.assertLess(page.table.model().rowCount(), 100)
        page.deleteLater()
        application.processEvents()

    def test_refresh_preserves_user_tags_and_coin_labels(self):
        self.client.lookup.return_value = profile()
        self.directory.lookup('example')
        self.directory.set_tags('solana', ADDRESS, ['priority', 'priority'])
        self.directory.link_coin('solana', ADDRESS, 'solana', TOKEN, 'Research candidate')
        self.directory.lookup('example')
        row = WalletDirectory(self.store).rows()[0]
        self.assertIn('priority', row['tags'])
        self.assertEqual(row['coins'][0]['relation'], 'User label')
        self.assertEqual(row['coins'][0]['address'], TOKEN)

    def test_conflicting_names_remain_separate_claims(self):
        self.directory.apply(normalize_profiles(profile('first')), 'first')
        self.directory.apply(normalize_profiles(profile('second')), 'second')
        row = self.directory.rows()[0]
        self.assertEqual(len(row['claims']), 2)
        self.assertIn('first', row['aliases'])
        self.assertIn('second', row['aliases'])

    def test_refresh_retires_only_claims_for_that_query(self):
        self.client.lookup.return_value = profile()
        self.directory.lookup('example')
        self.directory.apply(normalize_profiles(profile('another')), 'another')
        self.client.lookup.return_value = {'accounts': []}
        self.directory.lookup('example')
        self.assertEqual(len(self.directory.rows()[0]['claims']), 1)
        with self.store.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM identity_claims WHERE active=0').fetchone()[0], 1)

    def test_invalid_bulk_file_does_not_partially_import(self):
        path = Path(self.temporary.name) / 'Directory.json'
        path.write_text(json.dumps([{'name': 'valid', 'address': ADDRESS}, {'name': 'invalid', 'address': 'notawallet'}]))
        with self.assertRaises(ValueError):
            self.directory.import_file(path)
        self.assertEqual(self.directory.rows(), [])

    def test_evm_family_does_not_invent_network(self):
        record = {'name': 'Example', 'chain': 'evm', 'address': '0x' + 'A' * 40}
        self.directory.apply(normalize_profiles([record]), 'example')
        row = self.directory.rows()[0]
        self.assertEqual(row['chain'], 'evm')
        self.assertEqual(row['address'], '0x' + 'a' * 40)
        with self.assertRaises(ValueError):
            wallet_key('ethereum', record['address'])

    def test_failed_refresh_preserves_prior_identity(self):
        self.client.lookup.return_value = profile()
        self.directory.lookup('example')
        self.client.lookup.side_effect = OSError('Offline')
        with self.assertRaises(OSError):
            self.directory.lookup('example')
        self.assertEqual(len(self.directory.rows()), 1)

    def test_refresh_is_daily_and_respects_stop(self):
        self.client.lookup.return_value = profile()
        self.directory.lookup('example')
        self.client.lookup.reset_mock()
        self.assertFalse(self.directory.refresh_one())
        with self.store.connect() as connection:
            connection.execute('UPDATE identity_queries SET checked=0,attempted=0')
        self.assertFalse(self.directory.refresh_one(lambda: False))
        self.client.lookup.assert_not_called()
        self.assertTrue(self.directory.refresh_one())
        self.client.lookup.assert_called_once()

    def test_solana_address_case_survives_refresh(self):
        self.client.lookup.return_value = profile()
        self.directory.lookup(ADDRESS)
        with self.store.connect() as connection:
            connection.execute('UPDATE identity_queries SET checked=0,attempted=0')
        self.directory.refresh_one()
        self.client.lookup.assert_called_with(ADDRESS)

    def test_directory_search_finds_coin_address_and_alias(self):
        from PySide6.QtWidgets import QApplication
        from desktop import KOLWalletPage
        application = QApplication.instance() or QApplication([])
        self.directory.apply(normalize_profiles(profile()), 'example')
        self.directory.link_coin('solana', ADDRESS, 'solana', TOKEN, 'Research candidate')
        page = KOLWalletPage(self.temporary.name)
        page.search.setText(TOKEN)
        self.assertEqual(page.table.model().rowCount(), 1)
        page.search.setText('ExampleX')
        self.assertEqual(page.table.model().rowCount(), 1)
        page.deleteLater()
        application.processEvents()

    def test_coin_link_rejects_invalid_network(self):
        with self.assertRaises(ValueError):
            self.directory.link_coin('solana', ADDRESS, 'unknown', TOKEN, 'Research')

    def test_client_uses_public_search_and_validates_response(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(profile()).encode()
        opener = Mock(return_value=response)
        self.assertEqual(KollectorClient(opener).lookup('@example')['name'], 'example')
        self.assertIn('api/search?q=example', opener.call_args[0][0].full_url)
        self.assertNotIn('api/event', opener.call_args[0][0].full_url)

    def test_provider_rate_limit_stops_additional_requests(self):
        opener = Mock(side_effect=HTTPError('https://dethective.com/kollector/api/search', 429, 'Limit', {'Retry-After': '120'}, None))
        client = KollectorClient(opener)
        with self.assertRaises(ValueError):
            client.lookup('example')
        with self.assertRaises(ValueError):
            client.lookup('another')
        self.assertGreater(client.blocked_until, time.time())
        self.assertEqual(opener.call_count, 1)


if __name__ == '__main__':
    unittest.main()
