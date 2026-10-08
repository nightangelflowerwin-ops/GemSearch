"""Run against an already running DRY-RUN localhost server only."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE='http://127.0.0.1:8787'
def request(path, body=None, token=''):
    req=Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Gem-Token':token})
    with urlopen(req,timeout=5) as response:
        return response.status,response.read()

status,page=request('/')
assert status==200 and b'automation-panel' in page and b'auto-jobs' in page
for path in ['/style.css','/app.js']:
    assert request(path)[0]==200
_,body=request('/api/state')
state=json.loads(body)
assert state['automation']['mode']=='dry_run'
assert state['automation']['max_sol']==.025 and state['automation']['daily_max']==5
assert state['automation']['daily_sol']==.125
assert state['connections']['x'] is False
try:
    request('/api/launch-control',{'enabled':False},'wrong-token')
    raise AssertionError('Missing CSRF protection')
except HTTPError as error:
    assert error.code==403
enabled=state['automation']['enabled']
token=state['token']
try:
    assert request('/api/launch-control',{'enabled':False},token)[0]==200
    assert json.loads(request('/api/state')[1])['automation']['enabled'] is False
finally:
    request('/api/launch-control',{'enabled':enabled},token)
print('HTTP OK: dashboard/assets, economy caps, dry-run, disabled paid X, CSRF, pause/resume.')
