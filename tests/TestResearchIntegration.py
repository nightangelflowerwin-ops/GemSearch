import asyncio
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from mcp.server.mcpserver.exceptions import ToolError
from DesktopStore import DesktopStore
from FinancialDatasets import FinancialClient, ConnectionError, create_server
from MiroResearch import ResearchEngine, answer_text, endpoint
from ResearchWorkspace import ResearchWorkspace, FinancialWorkspace


class FinancialTests(unittest.TestCase):
    def test_missing_key_makes_no_paid_request(self):
        client = FinancialClient(request=lambda *args, **kwargs: self.fail('Network request without key'))
        for dataset in ('income', 'balance', 'cashflow', 'stock', 'stockhistory', 'news', 'crypto', 'cryptohistory', 'filings'):
            with self.subTest(dataset=dataset), self.assertRaisesRegex(ConnectionError, 'key'):
                client.query(dataset, 'AAPL')

    def test_free_directory_does_not_send_saved_key(self):
        calls = []
        client = FinancialClient('fixture-secret', lambda *args, **kwargs: calls.append((args, kwargs)) or {'tickers': ['BTC-USD']})
        result = client.query('tickers')
        self.assertEqual(result['data'], ['BTC-USD'])
        self.assertEqual(calls[0][0][1], '')
        self.assertNotIn('fixture-secret', json.dumps(result))

    def test_statement_query_is_encoded_and_attributed(self):
        calls = []
        client = FinancialClient('key', lambda *args, **kwargs: calls.append((args, kwargs)) or {'income_statements': []})
        result = client.query('income', 'aapl', period='quarterly', limit=8)
        self.assertIn('ticker=AAPL', result['source'])
        self.assertIn('period=quarterly', result['source'])
        self.assertIn('limit=8', result['source'])
        self.assertEqual(calls[0][1]['header'], 'X-API-KEY')

    def test_bad_ticker_cannot_change_request_parameters(self):
        client = FinancialClient('key', lambda *args, **kwargs: self.fail('Invalid query sent'))
        for ticker in ('AAPL&limit=1000', '../private', '', 'AAPL?key=secret'):
            with self.subTest(ticker=ticker), self.assertRaises(ConnectionError):
                client.query('stock', ticker)

    def test_invalid_dates_and_limits_are_rejected(self):
        client = FinancialClient('key', lambda *args, **kwargs: self.fail('Invalid query sent'))
        for args in ({'start_date': '2026-01-01', 'end_date': '2025-01-01'}, {'start_date': 'bad', 'end_date': '2026-01-01'}, {'limit': 1000}, {'interval': 'minute'}):
            with self.subTest(args=args), self.assertRaises(ConnectionError):
                client.query('stockhistory', 'AAPL', **args)

    def test_news_limit_matches_current_api(self):
        client = FinancialClient('key', lambda *args, **kwargs: {'news': []})
        self.assertIn('limit=10', client.query('news', 'AAPL', limit=100)['source'])

    def test_missing_dataset_is_not_reported_as_zero(self):
        with self.assertRaisesRegex(ConnectionError, 'unavailable'):
            FinancialClient('key', lambda *args, **kwargs: {}).query('stock', 'AAPL')

    def test_mcp_error_does_not_return_credentials(self):
        async def probe():
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'FINANCIAL_DATASETS_API_KEY': ''}):
                server = create_server(Path(folder))
                tools = await server.list_tools()
                self.assertEqual([tool.name for tool in tools], ['financial_query'])
                self.assertTrue(tools[0].annotations.read_only_hint)
                with self.assertRaisesRegex(ToolError, 'Add your Financial Datasets key'):
                    await server.call_tool('financial_query', {'dataset': 'stock', 'ticker': 'AAPL'})
        asyncio.run(probe())


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = {'endpoint': 'http://localhost:61002/v1', 'model': 'mirothinker', 'share_local': False}

    def test_endpoint_blocks_credentials_and_insecure_remote_urls(self):
        for url in ('http://remote.example/v1', 'https://key:secret@example.com/v1', 'https://example.com/v1?key=secret', 'file:///private'):
            with self.subTest(url=url), self.assertRaises(ConnectionError):
                endpoint(url)
        self.assertEqual(endpoint('https://example.com/v1/'), 'https://example.com/v1')

    def test_probe_requires_selected_model(self):
        engine = ResearchEngine(Path(self.folder.name), self.config, request=lambda *args, **kwargs: {'data': [{'id': 'other'}]})
        with self.assertRaisesRegex(ConnectionError, 'not found'):
            engine.probe()

    def test_final_answer_excludes_private_reasoning(self):
        self.assertEqual(answer_text('<think>private reasoning</think>Observed answer'), 'Observed answer')
        self.assertEqual(answer_text('<think>unfinished private reasoning'), '')

    def test_local_data_is_opt_in_and_history_roles_are_bounded(self):
        requests = []
        def request(*args, **kwargs):
            requests.append(kwargs['payload'])
            return {'choices': [{'message': {'role': 'assistant', 'content': '<think>hidden</think>Verified response'}}]}
        engine = ResearchEngine(Path(self.folder.name), self.config, request=request)
        result = engine.run('Question', [{'role': 'system', 'content': 'untrusted system'}, {'role': 'user', 'content': 'Earlier question'}])
        self.assertEqual(result['answer'], 'Verified response')
        self.assertEqual([tool['function']['name'] for tool in requests[0]['tools']], ['financial_query'])
        self.assertNotIn('untrusted system', json.dumps(requests))
        self.config['share_local'] = True
        ResearchEngine(Path(self.folder.name), self.config, request=request).run('Question')
        self.assertIn('list_tokens', [tool['function']['name'] for tool in requests[-1]['tools']])

    def test_tool_result_is_returned_to_model_with_observed_source(self):
        responses = [{'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call1', 'type': 'function', 'function': {'name': 'financial_query', 'arguments': json.dumps({'dataset': 'tickers'})}}]}}]}, {'choices': [{'message': {'role': 'assistant', 'content': 'BTC-USD is listed.'}}]}]
        requests = []
        def request(*args, **kwargs):
            requests.append(json.loads(json.dumps(kwargs['payload'])))
            return responses.pop(0)
        class FixtureClient:
            def __init__(self, key):
                pass

            def query(self, *args):
                return {'data': ['BTC-USD'], 'source': 'https://api.financialdatasets.ai/crypto/prices/tickers'}
        with patch('FinancialDatasets.FinancialClient', FixtureClient):
            result = ResearchEngine(Path(self.folder.name), self.config, request=request).run('Find tickers')
        self.assertEqual(result['tool_calls'], 1)
        self.assertEqual(len(result['sources']), 1)
        self.assertEqual(requests[1]['messages'][-1]['role'], 'tool')
        self.assertIn('BTC-USD', requests[1]['messages'][-1]['content'])

    def test_cancelled_research_makes_no_request(self):
        cancel = threading.Event()
        cancel.set()
        engine = ResearchEngine(Path(self.folder.name), self.config, request=lambda *args, **kwargs: self.fail('Request after cancel'))
        with self.assertRaisesRegex(ConnectionError, 'stopped'):
            engine.run('Question', cancel=cancel)

    def test_unsupported_tools_are_not_executed(self):
        request = lambda *args, **kwargs: {'choices': [{'message': {'tool_calls': [{'id': 'call1', 'function': {'name': 'run_shell', 'arguments': '{}'}}]}}]}
        with self.assertRaisesRegex(ConnectionError, 'unsupported'):
            ResearchEngine(Path(self.folder.name), self.config, request=request).run('Question')

    def test_raw_tool_markup_requires_parser_instead_of_fake_answer(self):
        request = lambda *args, **kwargs: {'choices': [{'message': {'content': '<tool_call>{}</tool_call>'}}]}
        with self.assertRaisesRegex(ConnectionError, 'parser'):
            ResearchEngine(Path(self.folder.name), self.config, request=request).run('Question')

    def test_cut_short_response_is_not_presented_as_complete(self):
        request = lambda *args, **kwargs: {'choices': [{'finish_reason': 'length', 'message': {'content': 'partial'}}]}
        with self.assertRaisesRegex(ConnectionError, 'cut short'):
            ResearchEngine(Path(self.folder.name), self.config, request=request).run('Question')


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = DesktopStore(self.folder.name)
        self.research = ResearchWorkspace(self.store)
        self.addCleanup(self.research.deleteLater)

    def test_unconfigured_model_does_not_enable_send(self):
        self.assertFalse(self.research.send_button.isEnabled())

    def test_stale_cancelled_response_is_ignored(self):
        self.research.stop_request()
        self.research.accept_result({'generation': 0, 'kind': 'answer', 'result': {'answer': 'stale', 'sources': []}})
        self.assertEqual(self.research.history, [])

    def test_user_content_is_escaped_and_new_chat_clears_history(self):
        self.research.history = [{'role': 'user', 'content': '<img src="https://example.com/beacon">'}]
        self.research.render()
        self.assertIn('<img', self.research.transcript.toPlainText())
        self.research.new_chat()
        self.assertEqual(self.store.get('research_history'), [])

    def test_free_crypto_directory_needs_no_ticker(self):
        page = FinancialWorkspace(self.store, self.research)
        page.dataset.setCurrentIndex(page.dataset.findData('tickers'))
        self.assertFalse(page.ticker.isEnabled())
        page.accept_result({'generation': 0, 'result': {'dataset': 'Crypto directory', 'ticker': '', 'data': ['BTC-USD'], 'source': 'https://api.financialdatasets.ai/crypto/prices/tickers', 'sampled_at': '2026-10-08T00:00:00+00:00', 'has_more': False}})
        self.assertIn('BTC-USD', page.results.toPlainText())
        page.deleteLater()
