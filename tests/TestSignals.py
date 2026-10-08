import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import automation
import jev
from jev import Jev

USDC='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=app.DATA,app.DB
        app.DATA=Path(self.temp.name);app.DB=app.DATA/'test.sqlite';app.init()
        self.jev=Jev(app.connect)

    def tearDown(self):
        app.DATA,app.DB=self.old;self.temp.cleanup()

    def post(self,i,text,hours_ago=0,links=()):
        stamp=datetime.fromtimestamp(time.time()-hours_ago*3600,timezone.utc).isoformat()
        return {'url':f'https://x.com/scout{i}/status/{500+i}','created_at':stamp,'text':text,'links':list(links)}

    def by_kind(self,kind):
        return [p for p in self.jev.narratives() if p.get('kind')==kind]

    def test_cashtags_skip_majors_prices_and_glued_text(self):
        self.assertEqual(jev.cashtags('early on $wif and $GEMS, not $BTC, $SOL, $100 or a$b'),{'WIF','GEMS'})

    def test_contract_address_must_decode_to_32_bytes(self):
        self.assertTrue(jev.is_solana_address(USDC))
        self.assertEqual(jev.solana_addresses(f'CA: {USDC} and {"1"*44} and {USDC[:-3]}'),{USDC})

    def test_ticker_and_contract_become_separate_research_only_leads(self):
        self.jev.ingest({'posts':[self.post(i,f'quiet launch $SPDR {USDC} looks organic {i}',links=['https://spdr.example']) for i in range(5)]})
        ticker,=self.by_kind('ticker');contract,=self.by_kind('contract')
        self.assertEqual((ticker['id'],ticker['key'],ticker['status']),('spider-ticker-SPDR','SPDR','shortlisted'))
        self.assertEqual(contract['key'],USDC)
        self.assertTrue(ticker['research_only'] and contract['research_only'])
        self.assertNotIn('topic',ticker)
        queue=automation.Automation.__new__(automation.Automation)
        self.assertFalse(queue.enqueue(ticker))

    def test_emerging_phrase_needs_three_authors_outside_known_topics(self):
        posts=[self.post(i,f'Rainbow spiders everywhere today, take {i}') for i in range(3)]
        posts+=[self.post(9,'AI agent swarm is live'),self.post(10,'agent swarm demo'),self.post(11,'agent swarm docs')]
        self.jev.ingest({'posts':posts})
        names={p['key'] for p in self.by_kind('phrase')}
        self.assertEqual(names,{'rainbow spiders'})
        self.jev.ingest({'posts':[self.post(20,'only two say quantum frogs'),self.post(21,'quantum frogs again')]})
        self.assertNotIn('quantum frogs',{p['key'] for p in self.by_kind('phrase')})

    def test_overlapping_bigrams_from_one_sentence_count_once(self):
        self.jev.ingest({'posts':[self.post(i,f'purple moon garden opens {i}') for i in range(4)]})
        self.assertEqual(len(self.by_kind('phrase')),1)

    def test_velocity_compares_last_six_hours_with_previous_eighteen(self):
        now=time.time()
        group=[{'author':f'a{i}','timestamp':now-3600,'captured_at':now-60} for i in range(6)]
        group+=[{'author':'old','timestamp':now-10*3600,'captured_at':now-600} for _ in range(3)]
        v=jev.velocity(group,now)
        self.assertEqual((v['recent'],v['previous'],v['growth'],v['recent_authors']),(6,3,6.0,6))
        self.assertEqual(v['first_seen'],now-600)
        self.assertIsNone(jev.velocity(group[:6],now)['growth'])

    def test_topic_narratives_carry_growth_and_stay_launch_compatible(self):
        self.jev.ingest({'posts':[self.post(i,f'AI agent release {i}',hours_ago=1,links=['https://a.example']) for i in range(5)]})
        topic,=self.by_kind('topic')
        self.assertEqual((topic['id'],topic['topic']),('spider-agents','agents'))
        self.assertEqual(topic['signals']['recent'],5);self.assertNotIn('research_only',topic)

    def test_topics_file_overrides_and_bad_file_falls_back(self):
        path=Path(self.temp.name)/'topics.json'
        path.write_text(json.dumps({'depin':r'\b(depin|hotspot)\b'}))
        self.assertEqual(list(automation.load_topics(path)),['depin'])
        for bad in [{'Bad Name':'x'},{'ok':'('},[],{}]:
            path.write_text(json.dumps(bad))
            with patch('sys.stderr'):self.assertEqual(automation.load_topics(path),automation.DEFAULT_TOPICS)
        self.assertEqual(automation.load_topics(Path(self.temp.name)/'missing.json'),automation.DEFAULT_TOPICS)

    def test_example_topics_file_is_valid(self):
        example=Path(__file__).resolve().parents[1]/'topics.example.json'
        self.assertIn('depin',automation.load_topics(example))

    def test_sample_script_produces_every_signal_type(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        import SampleSignals
        self.assertTrue(jev.is_solana_address(SampleSignals.sample_address()))
        self.jev.ingest({'posts':SampleSignals.sample_posts()})
        kinds={p.get('kind') for p in self.jev.narratives()}
        self.assertEqual(kinds,{'topic','ticker','contract','phrase'})


if __name__=='__main__':unittest.main()
