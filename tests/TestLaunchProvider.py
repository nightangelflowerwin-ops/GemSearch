import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from LaunchProvider import configured_provider, bridge_missing, bridge_result, run_bridge, NoRedirect
import TestAutomation

ENV = {'LAUNCH_PROVIDER': 'bridge', 'LAUNCH_BRIDGE_URL': 'https://bridge.example',
       'LAUNCH_BRIDGE_NAME': 'Test platform', 'LAUNCH_BRIDGE_CHAIN': 'solana',
       'LAUNCH_BRIDGE_TOKEN': 'secret-not-in-job', 'LAUNCH_BRIDGE_TRUSTED': '1'}
IDENTITY = '0123456789abcdef01234567'


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.job = dict(id=IDENTITY, provider=configured_provider(), name='Test', symbol='TEST',
                        description='Independent experiment', image_base64='png', narrative='Agents',
                        source_url='https://example.com')

    def receipt(self, status='pending', **extra):
        return dict(protocol='gem-launch/1', job_id=IDENTITY, status=status, **extra)

    def test_dispatch_persisted_before_network_and_only_poll_after_restart(self):
        saved, calls = [], []
        def persist(value): saved.append(copy.deepcopy(value))
        def transport(method, url, token, body=None):
            self.assertTrue(saved[0]['bridge_dispatched'])
            calls.append(method)
            self.assertEqual(token, ENV['LAUNCH_BRIDGE_TOKEN'])
            if method == 'PUT':
                self.assertEqual(body['constraints'], {'max_total_lamports': 25000000, 'developer_buy_lamports': 0})
                self.assertNotIn(token, json.dumps(body))
                raise TimeoutError()
            return self.receipt()
        self.assertEqual(run_bridge(self.job, persist, transport)['status'], 'pending')
        run_bridge(saved[0], persist, transport)
        self.assertEqual(calls, ['PUT', 'GET'])
        self.assertNotIn(ENV['LAUNCH_BRIDGE_TOKEN'], json.dumps(saved))

    def test_changed_provider_does_not_retarget_job(self):
        with patch.dict(os.environ, {'LAUNCH_BRIDGE_URL': 'https://other.example'}), patch('LaunchProvider.request_json') as send:
            result = run_bridge(self.job, lambda _: None, send)
            self.assertEqual(result['status'], 'pending')
            send.assert_not_called()

    def test_invalid_receipts_cannot_finish_job(self):
        for value in [{}, self.receipt('unknown'), self.receipt('confirmed'),
                      self.receipt('confirmed', mint='1'*32, signature='1'*64, spent_lamports=25000001),
                      self.receipt('confirmed', mint='1'*32, signature='1'*64, spent_lamports=True),
                      dict(self.receipt(), job_id='another')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge_result(value, IDENTITY)
        good = bridge_result(self.receipt('confirmed', mint='1'*32, signature='1'*64, spent_lamports=20000), IDENTITY)
        self.assertEqual(good['actual_lamports'], 20000)
        self.assertIn('not independently verified', good['reason'])

    def test_rejection_and_definitive_failure(self):
        self.assertEqual(bridge_result(self.receipt('rejected'), IDENTITY)['status'], 'blocked')
        self.assertEqual(bridge_result(self.receipt('failed'), IDENTITY)['status'], 'failed')

    def test_no_redirect_and_invalid_config(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))
        for url in ['http://bridge.example', 'https://user:pass@bridge.example', 'https://bridge.example?key=secret', 'https://bridge.example/#x']:
            with patch.dict(os.environ, {'LAUNCH_BRIDGE_URL': url}), self.assertRaises(ValueError):
                configured_provider()
        with patch.dict(os.environ, {'LAUNCH_BRIDGE_CHAIN': 'ethereum'}), self.assertRaises(ValueError):
            configured_provider()

    def test_explicit_trust_required(self):
        with patch.dict(os.environ, {'LAUNCH_BRIDGE_TRUSTED': '0'}):
            self.assertIn('LAUNCH_BRIDGE_TRUSTED', bridge_missing())
            with patch('LaunchProvider.request_json') as send:
                run_bridge(self.job, lambda _: None, send)
                send.assert_not_called()


class BridgeQueueTests(TestAutomation.AutomationTests):
    def setUp(self):
        super().setUp()
        self.bridge_env = patch.dict(os.environ, ENV)
        self.bridge_env.start()

    def tearDown(self):
        self.bridge_env.stop()
        super().tearDown()

    # Inherited suite runs for bridge routing too; use a missing bridge token here.
    def test_live_has_separate_quota_and_requires_credentials(self):
        self.engine.enqueue(self.project(1))
        self.engine.tick()
        with patch.dict(os.environ, {'LAUNCH_MODE': 'live', 'LAUNCH_BRIDGE_TOKEN': ''}):
            self.engine.enqueue(self.project(1))
            self.engine.tick()
            self.assertEqual(self.engine.status()['used'], 0)

    def test_unknown_outcome_blocks_other_jobs(self):
        with patch.dict(os.environ, {'LAUNCH_MODE': 'live'}), patch('automation.run_bridge', return_value={'status':'pending'}):
            for i in range(2): self.engine.enqueue(self.project(i))
            self.engine.tick()
            self.engine.tick()
            self.assertEqual(self.engine.status()['used'], 1)
            self.assertEqual(sum(j['status']=='queued' for j in self.engine.status()['jobs']), 1)

    def test_dry_run_does_not_contact_bridge(self):
        self.engine.enqueue(self.project(1))
        with patch('automation.run_bridge') as send:
            self.engine.tick()
            send.assert_not_called()
        self.assertEqual(self.engine.status()['jobs'][0]['provider']['label'], 'Test platform')
        self.assertNotIn('endpoint', self.engine.status()['jobs'][0]['provider'])
        self.assertNotIn(ENV['LAUNCH_BRIDGE_TOKEN'], json.dumps(self.engine.status()))

    def test_switching_provider_does_not_reset_quota(self):
        for i in range(5):
            self.engine.enqueue(self.project(i))
            self.engine.tick()
        with patch.dict(os.environ, {'LAUNCH_PROVIDER': 'pumpportal'}):
            self.engine.enqueue(self.project(6))
            self.engine.tick()
            self.assertEqual(self.engine.status()['used'], 5)
            self.assertEqual(self.engine.status()['jobs'][0]['status'], 'queued')


if __name__ == '__main__': unittest.main()
