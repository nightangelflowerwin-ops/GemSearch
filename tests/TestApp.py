import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_data, self.old_db = app.DATA, app.DB
        app.DATA = Path(self.temp.name)
        app.DB = app.DATA / 'test.sqlite'
        app.init()

    def tearDown(self):
        app.DATA, app.DB = self.old_data, self.old_db
        self.temp.cleanup()

    def test_demo_consensus_and_rejection(self):
        self.assertTrue(app.begin(app.demo_posts(), 'demo', background=False))
        with app.connect() as con:
            rows = {r['name']: r['status'] for r in con.execute('SELECT * FROM projects')}
        self.assertEqual(rows['Orbit Agents'], 'shortlisted')
        self.assertEqual(rows['Signal Garden'], 'held')
        self.assertEqual(rows['Moon Claim'], 'rejected')
        self.assertEqual(rows['Tiny Protocol'], 'held')

    def test_import_deduplication_persists(self):
        posts = app.demo_posts()[:2]
        with patch.object(app, 'crawl', return_value={'pages': [], 'errors': [], 'synthetic': False}):
            app.begin(posts + posts, 'import', background=False)
            app.begin(posts, 'import', background=False)
        with app.connect() as con:
            counts = [r['posts'] for r in con.execute('SELECT posts FROM runs ORDER BY id')]
        self.assertEqual(counts, [2, 0])

    def test_block_local_fetch(self):
        for url in ['http://127.0.0.1', 'http://169.254.169.254', 'http://[::1]']:
            with self.assertRaises(ValueError):
                app.fetch(url)

    def test_block_private_redirect(self):
        public = [(2, 1, 6, '', ('93.184.216.34', 80))]
        local = [(2, 1, 6, '', ('127.0.0.1', 80))]
        with patch.object(app.socket, 'getaddrinfo', side_effect=[public, local]), patch.object(app.socket, 'create_connection'), patch.object(app.http.client, 'HTTPConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 302
            response.getheader.return_value = 'http://localhost/'
            with self.assertRaises(ValueError):
                app.fetch('http://example.com')
            self.assertEqual(connection.call_count, 1)

    def test_validation(self):
        for value in [{}, [], [None], [{'id': 'a'}]]:
            with self.assertRaises(ValueError):
                app.validate_posts(value)
        post = app.demo_posts()[0]
        post['created_at'] = '2026-01-01T00:00:00'
        with self.assertRaises(ValueError):
            app.validate_posts([post])

    def test_no_baseline_is_unknown(self):
        sig = app.signals([app.demo_posts()[0]])
        self.assertIsNone(sig['growth'])

    def test_missing_evidence_never_shortlisted(self):
        sig = app.signals(app.demo_posts()[:12])
        evidence = {'pages': [], 'errors': [], 'synthetic': False}
        self.assertEqual(app.vote('maker', sig, evidence)['vote'], 'hold')
        self.assertEqual(app.vote('runner', sig, evidence)['vote'], 'hold')

    def test_launch_validation_and_persistence(self):
        draft = {'name': 'Test', 'symbol': 'test', 'description': 'Independent token', 'amount': 0, 'priority_fee': .00005}
        result = app.create_launch(draft)
        self.assertEqual(result['symbol'], 'TEST')
        checked = app.check_launch(result['id'])
        self.assertEqual(checked['status'], 'needs_connection')
        for value in [float('nan'), float('inf'), -1, 11, '0', True]:
            with self.assertRaises(ValueError):
                app.create_launch(dict(draft, amount=value))


if __name__ == '__main__':
    unittest.main()
