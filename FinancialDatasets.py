import datetime
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from typing import Any, Literal

from mcp import types
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from DesktopCredentials import load_key


DATASETS = {
    'income': ('Income statements', '/financials/income-statements/', 'income_statements'),
    'balance': ('Balance sheets', '/financials/balance-sheets/', 'balance_sheets'),
    'cashflow': ('Cash flow', '/financials/cash-flow-statements/', 'cash_flow_statements'),
    'stock': ('Stock price', '/prices/snapshot/', 'snapshot'),
    'stockhistory': ('Stock history', '/prices/', 'prices'),
    'news': ('Company news', '/news/', 'news'),
    'tickers': ('Crypto directory', '/crypto/prices/tickers', 'tickers'),
    'crypto': ('Crypto price', '/crypto/prices/snapshot/', 'snapshot'),
    'cryptohistory': ('Crypto history', '/crypto/prices/', 'prices'),
    'filings': ('SEC filings', '/filings/', 'filings')
}


class ConnectionError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConnectionError('The service redirected this request. Check the connection address.')


def fetch_json(url, key='', payload=None, header='Authorization', timeout=30):
    headers = {'Accept': 'application/json', 'User-Agent': 'GemSearch'}
    if key:
        headers[header] = 'Bearer ' + key if header == 'Authorization' else key
    body = json.dumps(payload).encode() if payload is not None else None
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with build_opener(NoRedirect()).open(Request(url, data=body, headers=headers), timeout=timeout) as response:
            raw = response.read(4000001)
    except HTTPError as error:
        messages = {401: 'The key was not accepted. Check your connection.', 403: 'This account cannot access the requested data.', 402: 'This data requires paid access or available credits.', 429: 'The service is busy or the request limit was reached. Try again later.'}
        raise ConnectionError(messages.get(error.code, 'The service could not complete this request. Try again later.')) from None
    except (URLError, TimeoutError, OSError):
        raise ConnectionError('Could not reach the service. Check the address and try again.') from None
    if len(raw) > 4000000:
        raise ConnectionError('The response is too large. Request fewer records.')
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ConnectionError('The service returned an unreadable response.') from None
    if not isinstance(result, dict):
        raise ConnectionError('The service returned an unexpected response.')
    return result


class FinancialClient:
    def __init__(self, key='', request=fetch_json):
        self.key = key
        self.request = request

    def query(self, dataset, ticker='', period='annual', limit=4, start_date='', end_date='', interval='day', filing_type=''):
        if dataset not in DATASETS:
            raise ConnectionError('Choose an available dataset.')
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ConnectionError('Choose between 1 and 100 records.')
        if period not in ('annual', 'quarterly', 'ttm'):
            raise ConnectionError('Choose annual, quarterly or trailing twelve months.')
        if interval not in ('day', 'week', 'month', 'year'):
            raise ConnectionError('Choose a daily, weekly, monthly or yearly interval.')
        params = {}
        if dataset != 'tickers':
            if not self.key:
                raise ConnectionError('Add your Financial Datasets key in Connections first. Market data may require paid credits.')
            ticker = ticker.strip().upper()
            if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-:]{0,24}', ticker):
                raise ConnectionError('Enter a ticker such as AAPL or BTC-USD.')
            params['ticker'] = ticker
        if dataset in ('income', 'balance', 'cashflow'):
            params.update(period=period, limit=limit)
        if dataset in ('news', 'filings'):
            params['limit'] = min(limit, 10) if dataset == 'news' else limit
        if dataset == 'filings' and filing_type:
            if filing_type not in ('10-K', '10-Q', '8-K', '20-F', '6-K'):
                raise ConnectionError('Choose a supported SEC filing type.')
            params['filing_type'] = filing_type
        if dataset in ('stockhistory', 'cryptohistory'):
            try:
                start = datetime.date.fromisoformat(start_date)
                end = datetime.date.fromisoformat(end_date)
            except (ValueError, TypeError):
                raise ConnectionError('Enter valid start and end dates.') from None
            if start > end or (end - start).days > 3660:
                raise ConnectionError('Choose a date range of up to ten years with the start before the end.')
            params.update(start_date=start_date, end_date=end_date, interval=interval, interval_multiplier=1)
        label, route, result_key = DATASETS[dataset]
        url = 'https://api.financialdatasets.ai' + route + ('?' + urlencode(params) if params else '')
        response = self.request(url, self.key if dataset != 'tickers' else '', header='X-API-KEY')
        if result_key not in response:
            raise ConnectionError('This dataset is unavailable for the requested ticker.')
        return {'dataset': label, 'ticker': ticker if dataset != 'tickers' else '', 'data': response[result_key], 'source': url, 'sampled_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'has_more': bool(response.get('next_page_url'))}


def create_server(directory):
    server = MCPServer('GemSearch Financial Data', log_level='ERROR', instructions='Read-only Financial Datasets queries. Each data query may consume the user account credits. Credentials are never returned. Data access rights are separate from software licensing.')
    annotations = types.ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)

    @server.tool(description='Query financial statements, stock and crypto prices, historical prices, company news, SEC filings or the free crypto ticker directory. Data queries other than tickers require the user API key and may consume paid credits. Dates use YYYY-MM-DD.', annotations=annotations, structured_output=True)
    def financial_query(dataset: Literal['income', 'balance', 'cashflow', 'stock', 'stockhistory', 'news', 'tickers', 'crypto', 'cryptohistory', 'filings'], ticker: str = '', period: Literal['annual', 'quarterly', 'ttm'] = 'annual', limit: int = 4, start_date: str = '', end_date: str = '', interval: Literal['day', 'week', 'month', 'year'] = 'day', filing_type: str = '') -> dict[str, Any]:
        try:
            return FinancialClient(load_key(directory, 'financial')).query(dataset, ticker, period, limit, start_date, end_date, interval, filing_type)
        except ConnectionError as error:
            raise ToolError(str(error)) from None

    return server
