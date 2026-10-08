import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from automation import Automation, discover_free, token_icon


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = app.DATA, app.DB
        app.DATA = Path(self.temp.name)
        app.DB = app.DATA / 'test.sqlite'
        app.init()
        self.env = patch.dict(os.environ, {'LAUNCH_MODE': 'dry_run'})
        self.env.start()
        self.engine = Automation(app.ROOT, app.DATA, app.connect, app.event)

    def tearDown(self):
        self.env.stop()
        app.DATA, app.DB = self.previous
        self.temp.cleanup()

    def project(self, i, **kw):
        return dict({'source': 'import', 'status': 'shortlisted', 'url': f'https://example.com/{i}', 'name': f'Project {i}', 'observed_at': time.time()}, **kw)

    def test_budget_survives_restart_and_counts_attempts(self):
        for i in range(8):
            self.engine.enqueue(self.project(i))
        for i in range(8):
            self.engine.tick()
        self.assertEqual(self.engine.status()['used'], 5)
        self.assertEqual(self.engine.status()['reserved_sol'], .125)
        restarted = Automation(app.ROOT, app.DATA, app.connect, app.event)
        restarted.tick()
        self.assertEqual(sum(j['status'] == 'queued' for j in restarted.status()['jobs']), 3)

    def test_reject_demo_stale_future_and_hold(self):
        for p in [self.project(1, source='demo'), self.project(2, observed_at=0), self.project(3, observed_at=time.time()+3600), self.project(4,status='held')]:
            self.assertFalse(self.engine.enqueue(p))

    def test_duplicate_narrative_never_enqueued_twice(self):
        self.assertTrue(self.engine.enqueue(self.project(1,topic='agents')))
        self.assertFalse(self.engine.enqueue(self.project(2,topic='agents')))

    def test_live_has_separate_quota_and_requires_credentials(self):
        self.engine.enqueue(self.project(1))
        self.engine.tick()
        with patch.dict(os.environ, {'LAUNCH_MODE':'live', 'PINATA_JWT':''}):
            self.engine.enqueue(self.project(1))
            self.engine.tick()
            self.assertEqual(self.engine.status()['used'],0)

    def test_unknown_outcome_blocks_other_jobs(self):
        with patch.dict(os.environ, {'LAUNCH_MODE':'live'}), patch.object(self.engine, 'missing', return_value=[]):
            for i in range(2):self.engine.enqueue(self.project(i))
            with app.connect() as con:
                identity=con.execute('SELECT id FROM launch_jobs LIMIT 1').fetchone()[0]
                con.execute("UPDATE launch_jobs SET status='pending',reserved=? WHERE id=?",(time.time(),identity))
            with patch('automation.subprocess.run', side_effect=OSError):
                self.engine.tick()
            self.assertEqual(self.engine.status()['used'],1)
            self.assertEqual(sum(j['status']=='queued' for j in self.engine.status()['jobs']),1)

    def test_pause_and_dry_run_never_call_signer(self):
        self.engine.enqueue(self.project(1))
        self.engine.enabled=False
        self.engine.tick()
        self.assertEqual(self.engine.status()['used'],0)
        self.engine.enabled=True
        with patch('automation.subprocess.run') as execute:
            self.engine.tick()
            execute.assert_not_called()
        self.assertEqual(self.engine.status()['jobs'][0]['status'],'dry_run_complete')

    def test_icon_png(self):
        self.assertTrue(token_icon('test').startswith(b'\x89PNG'))
        self.assertEqual(token_icon('test'),token_icon('test'))

    def test_free_feed_uses_independent_domains_and_cache(self):
        def fetch(url):
            if 'topstories' in url:return url,json.dumps([1,2,3])
            i=int(url.split('/')[-1].split('.')[0])
            return url,json.dumps({'id':i,'type':'story','title':'AI agents release','time':time.time(),'score':50,'descendants':10,'url':f'https://source{i}.example','by':f'user{i}'})
        projects=discover_free(self.engine,fetch)
        self.assertEqual(projects[0]['status'],'shortlisted')
        self.assertEqual(discover_free(self.engine,fetch),[])


if __name__=='__main__':unittest.main()
