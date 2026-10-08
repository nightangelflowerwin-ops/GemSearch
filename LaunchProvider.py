"""Provider routing and a versioned, key-free launch bridge protocol."""
import json
import os
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def configured_provider():
    kind = os.getenv('LAUNCH_PROVIDER', 'pumpportal')
    if kind == 'pumpportal':
        return {'kind': kind, 'label': 'Solana / Pump.fun', 'chain': 'solana'}
    if kind != 'bridge':
        raise ValueError('LAUNCH_PROVIDER must be pumpportal or bridge')
    endpoint = os.getenv('LAUNCH_BRIDGE_URL', '').rstrip('/')
    url = urlsplit(endpoint)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment):
        raise ValueError('LAUNCH_BRIDGE_URL must be HTTPS without credentials, query or fragment')
    chain = os.getenv('LAUNCH_BRIDGE_CHAIN', 'solana')
    # The existing budget is denominated in SOL; do not silently apply it to other chains.
    if chain != 'solana':
        raise ValueError('Only Solana is supported by the current SOL budget policy')
    label = os.getenv('LAUNCH_BRIDGE_NAME', 'Custom launch bridge')[:80]
    return {'kind': kind, 'label': label, 'chain': chain, 'endpoint': endpoint}


def bridge_missing():
    return [name for name in ('LAUNCH_BRIDGE_TOKEN', 'LAUNCH_BRIDGE_TRUSTED')
            if not os.getenv(name) or (name == 'LAUNCH_BRIDGE_TRUSTED' and os.getenv(name) != '1')]


def request_json(method, url, token, body=None):
    raw = None if body is None else json.dumps(body).encode()
    req = Request(url, data=raw, method=method, headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
        'Accept': 'application/json', 'User-Agent': 'GemSearch-LaunchBridge/1'})
    with build_opener(NoRedirect()).open(req, timeout=20) as response:
        raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('Bridge response too large')
        return json.loads(raw)


def bridge_result(value, identity):
    if not isinstance(value, dict) or value.get('protocol') != 'gem-launch/1' or value.get('job_id') != identity:
        raise ValueError('Bridge identity mismatch')
    status = value.get('status')
    if status not in ('pending', 'confirmed', 'failed', 'rejected'):
        raise ValueError('Invalid bridge status')
    result = {'status': 'blocked' if status == 'rejected' else status,
              'reason': 'External bridge reports: ' + status + '. On-chain result is not independently verified by Gem Search.'}
    if status == 'confirmed':
        mint, signature, spent = value.get('mint'), value.get('signature'), value.get('spent_lamports')
        if (not isinstance(mint, str) or not re.fullmatch('[1-9A-HJ-NP-Za-km-z]{32,44}', mint)
                or not isinstance(signature, str) or not re.fullmatch('[1-9A-HJ-NP-Za-km-z]{64,88}', signature)
                or type(spent) is not int or not 0 <= spent <= 25_000_000):
            raise ValueError('Invalid or over-budget bridge receipt')
        result.update(mint=mint, signature=signature, actual_lamports=spent)
    return result


def run_bridge(draft, persist, transport=request_json):
    """Persist dispatch BEFORE I/O. Once dispatched, only poll; never recreate."""
    provider = draft['provider']
    # Credentials are never persisted in jobs. A route change cannot retarget an old job.
    try:
        current = configured_provider()
    except ValueError:
        current = None
    if current != provider or bridge_missing():
        return {'status': 'pending', 'reason': 'Restore the original bridge configuration to reconcile this job.'}
    url = provider['endpoint'] + '/v1/launches/' + draft['id']
    try:
        if not draft.get('bridge_dispatched'):
            draft['bridge_dispatched'] = True
            persist(draft)
            body = {'protocol': 'gem-launch/1', 'job_id': draft['id'], 'chain': 'solana',
                    'token': {key: draft[key] for key in ('name', 'symbol', 'description', 'image_base64')},
                    'constraints': {'max_total_lamports': 25_000_000, 'developer_buy_lamports': 0},
                    'source': {'narrative': draft['narrative'], 'url': draft['source_url']}}
            value = transport('PUT', url, os.environ['LAUNCH_BRIDGE_TOKEN'], body)
        else:
            value = transport('GET', url, os.environ['LAUNCH_BRIDGE_TOKEN'])
        return bridge_result(value, draft['id'])
    except Exception:
        # Do not expose upstream responses, tokens or URLs in public logs.
        return {'status': 'pending', 'reason': 'Bridge outcome unknown. Only status polling is allowed; new allocations remain paused.'}
