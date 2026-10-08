"""Actual HTTPS scaffold + client smoke test. No real platform, wallet or spending."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from LaunchProvider import request_json
ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        cert, key = base/'cert.pem', base/'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=DNS:localhost'], check=True, capture_output=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        token = 'test-only-' + 'a'*32
        process = subprocess.Popen([sys.executable, 'examples/LaunchBridge.py', '--cert', str(cert),
                                    '--key', str(key), '--database', str(base/'jobs.sqlite'), '--port', str(port)],
                                   cwd=ROOT, env=dict(os.environ, BRIDGE_API_TOKEN=token),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            url = f'https://localhost:{port}/v1/launches/0123456789abcdef01234567'
            with patch.dict(os.environ, {'SSL_CERT_FILE': str(cert)}):
                for _ in range(100):
                    try:
                        request_json('GET', url, token)
                    except HTTPError as error:
                        if error.code == 404: break
                        raise
                    except OSError:
                        time.sleep(.05)
                else:
                    raise AssertionError('Bridge did not start')
                body = {'protocol':'gem-launch/1', 'job_id':'0123456789abcdef01234567', 'chain':'solana',
                        'constraints':{'max_total_lamports':25000000,'developer_buy_lamports':0},
                        'token':{'name':'Test'}, 'source':{}}
                first = request_json('PUT', url, token, body)
                assert first['status'] == 'rejected', first
                assert request_json('PUT', url, token, body) == first
                assert request_json('GET', url, token) == first
                try:
                    request_json('PUT', url, token, dict(body, token={'name':'Different'}))
                    raise AssertionError('Conflicting payload accepted')
                except HTTPError as error:
                    assert error.code == 409
                try:
                    request_json('GET', url, 'wrong-token')
                    raise AssertionError('Invalid token accepted')
                except HTTPError as error:
                    assert error.code == 401
            print('HTTPS bridge OK: certificate verification, bearer auth, durable receipt, idempotency, conflict rejection. No transaction.')
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stderr.close()


if __name__ == '__main__': main()
