"""HTTPS adapter scaffold. Default implementation rejects launches without spending.

Implement launch_on_platform() and reconcile_on_platform() for your chosen API.
Never use this scaffold's default rejection as evidence of a live integration.
"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl


def launch_on_platform(job):
    # Use job['job_id'] as the platform idempotency key. Persist any platform
    # operation identifier BEFORE returning. Enforce constraints BEFORE signing.
    return {'status': 'rejected'}  # No platform is configured in this scaffold.


def reconcile_on_platform(job):
    # Query the platform using its persisted operation ID. NEVER launch again.
    return {'status': 'pending'}


def serve(cert, key, database, port):
    token = os.environ.get('BRIDGE_API_TOKEN', '')
    if len(token) < 32:
        raise ValueError('Set BRIDGE_API_TOKEN to a random secret of at least 32 characters')
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as con:
        con.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, request TEXT, response TEXT)')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, body):
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.handle_job(False)

        def do_PUT(self):
            self.handle_job(True)

        def handle_job(self, create):
            supplied = self.headers.get('Authorization', '')
            if not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
                return self.reply(401, {'error': 'Unauthorized'})
            match = re.fullmatch(r'/v1/launches/([a-f0-9]{24})', self.path)
            if not match:
                return self.reply(404, {'error': 'Unknown route'})
            identity = match[1]
            with sqlite3.connect(database) as con:
                row = con.execute('SELECT request,response FROM jobs WHERE id=?', (identity,)).fetchone()
                if not row and not create:
                    return self.reply(404, {'error': 'Unknown job; do not recreate automatically'})
                if create:
                    try:
                        size = int(self.headers.get('Content-Length', '0'))
                        if not 0 < size <= 100000:
                            raise ValueError()
                        job = json.loads(self.rfile.read(size))
                        if (job['protocol'] != 'gem-launch/1' or job['job_id'] != identity
                                or job['chain'] != 'solana' or job['constraints'] != {
                                    'max_total_lamports': 25000000, 'developer_buy_lamports': 0}):
                            raise ValueError()
                        encoded = json.dumps(job, sort_keys=True)
                    except (ValueError, KeyError, TypeError):
                        return self.reply(400, {'error': 'Invalid launch request'})
                    if row and row[0] != encoded:
                        return self.reply(409, {'error': 'Idempotency conflict'})
                else:
                    job = json.loads(row[0])
                if row:
                    receipt = json.loads(row[1])
                    if receipt['status'] == 'pending':
                        try:
                            receipt = dict(reconcile_on_platform(job), protocol='gem-launch/1', job_id=identity)
                        except Exception:
                            pass
                else:
                    receipt = {'protocol': 'gem-launch/1', 'job_id': identity, 'status': 'pending'}
                    con.execute('INSERT INTO jobs VALUES (?,?,?)', (identity, encoded, json.dumps(receipt)))
                    con.commit()  # Durable before the platform operation, including process crashes.
                    try:
                        receipt = dict(launch_on_platform(job), protocol='gem-launch/1', job_id=identity)
                    except Exception:
                        pass  # Unknown outcome stays pending; do not issue a second launch.
                con.execute('UPDATE jobs SET response=? WHERE id=?', (json.dumps(receipt), identity))
            self.reply(200, receipt)

    server = HTTPServer(('127.0.0.1', port), Handler)
    server.timeout = 30
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cert', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--database', type=Path, default=Path('data/bridge.sqlite'))
    parser.add_argument('--port', type=int, default=9443)
    args = parser.parse_args()
    os.umask(0o077)
    serve(args.cert, args.key, args.database, args.port)
