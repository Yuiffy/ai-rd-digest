import copy
import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import digest as d
import local_digest as l


def article(**kw):
    return dict(url='https://openai.com/index/agent-study', title='Agent study', organization='OpenAI',
        published='2026-10-02', date_source='publication metadata', aliases=[], category='Agent工程',
        summary='官方研究报告称，明确工具权限边界可降低自动化任务中的越权风险，相关结果来自受控实验。',
        value='研发团队可参考其测试方法，在业务环境中验证权限控制和审计机制。',
        priority='P0', score=90, story_key='agent-study') | kw


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.hp = patch.object(l, 'HOME', self.root)
        self.hp.start()
        self.np = patch.object(l, 'now', return_value=dt.datetime(2026, 10, 15, 10, tzinfo=d.CN))
        self.np.start()
        self.store = l.Store(initialize=True)
        self.state = self.store.load()
        self.config = dict(start_date='2026-10-01', max_articles=6, sources={
            'OpenAI': {'hosts': ['openai.com']}, 'Anthropic': {'hosts': ['www.anthropic.com']}})

    def tearDown(self):
        self.store.db.close()
        self.hp.stop()
        self.np.stop()
        self.tmp.cleanup()

    def prepared(self):
        return dict(date='2026-10-15', first=True, items=[article()])

    def files(self, **changes):
        quote = 'The evaluation used explicitly bounded tool permissions.'
        a = article(body=quote + ' Official research context.' * 40, **changes)
        src = dict(date='2026-10-15', sources=[a], coverage={x: {'status': 'ok'} for x in self.config['sources']})
        rev = dict(date='2026-10-15', items=[article(evidence=[quote])])
        sp, rp, out = [self.root / x for x in ('sources.json', 'review.json', 'prepared.json')]
        l.write_json(sp, src)
        l.write_json(rp, rev)
        return sp, rp, out

    def test_publication_not_modification(self):
        html = '<meta property="article:published_time" content="2026-09-30"><meta property="article:modified_time" content="2026-10-12"><main><h1>Old research</h1>' + 'research ' * 100 + '</main>'
        self.assertEqual(d.extract(article()['url'], html, 'OpenAI')['published'], '2026-09-30')

    def test_missing_date_and_external_canonical(self):
        html = '<main><h1>Research</h1>' + 'research ' * 100 + '</main>'
        with self.assertRaises(d.Failure): d.extract(article()['url'], html, 'OpenAI')
        html = '<link rel="canonical" href="https://evil.example/steal"><meta property="article:published_time" content="2026-10-01">' + html
        with self.assertRaises(d.Failure): d.extract(article()['url'], html, 'OpenAI', hosts={'openai.com'})

    def test_dedupe(self):
        self.assertEqual(d.canonical('https://www.openai.com/zh-Hans-CN/index/abc/?utm_source=x#top'), 'https://openai.com/index/abc')
        self.assertTrue(d.duplicate(article(title='Agent—study!'), [article()]))
        self.assertTrue(d.duplicate(article(title='Different', url='https://openai.com/index/alias'), [article()]))

    def test_restart_initialize_preserves_history(self):
        self.state.update(first_complete=True, sent=[article()])
        self.store.save(self.state)
        other = l.Store(initialize=True)
        self.assertEqual(len(other.load()['sent']), 1)
        self.assertTrue(other.load()['first_complete'])
        other.db.close()

    def test_lock(self):
        with l.Lock():
            with self.assertRaises(d.Failure):
                with l.Lock(): pass

    def test_dry_run_no_send_or_history_change(self):
        files = self.files()
        original = copy.deepcopy(self.state)
        with patch.object(l, 'send_http') as send:
            l.prepare(self.config, self.state, *files)
            send.assert_not_called()
        self.assertEqual(l.read_json(files[2])['items'][0]['published'], '2026-10-02')
        self.assertEqual(self.store.load(), original)

    def test_date_window(self):
        for pub in ('2026-09-30', '2026-10-16'):
            with self.assertRaises(d.Failure): l.prepare(self.config, self.state, *self.files(published=pub))

    def test_first_leftovers_not_sent_later(self):
        self.state.update(first_complete=True, first_cutoff='2026-10-15')
        files = self.files()
        l.prepare(self.config, self.state, *files)
        self.assertEqual(l.read_json(files[2])['items'], [])

    def test_bad_coverage_and_fabricated_evidence(self):
        sp, rp, out = self.files()
        src = l.read_json(sp)
        src['coverage']['OpenAI']['status'] = 'blocked'
        l.write_json(sp, src)
        with self.assertRaises(d.Failure): l.prepare(self.config, self.state, sp, rp, out)
        sp, rp, out = self.files()
        rev = l.read_json(rp)
        rev['items'][0]['evidence'] = ['Invented statement that never appeared.']
        l.write_json(rp, rev)
        with self.assertRaises(d.Failure): l.prepare(self.config, self.state, sp, rp, out)

    def test_ambiguous_post_blocks_retry(self):
        with patch.object(l, 'send_http', side_effect=d.Failure('timeout')) as send:
            with self.assertRaises(d.Failure): l.deliver(self.store, self.state, self.prepared())
            with self.assertRaises(d.Failure): l.deliver(self.store, self.store.load(), self.prepared())
            self.assertEqual(send.call_count, 1)
        self.assertIsNotNone(self.store.load()['pending'])
        self.assertEqual(self.store.load()['sent'], [])

    def test_disk_failure_prevents_post(self):
        with patch.object(self.store, 'save', side_effect=OSError('disk full')), patch.object(l, 'send_http') as send:
            with self.assertRaises(OSError): l.deliver(self.store, self.state, self.prepared())
            send.assert_not_called()

    def test_success_only_one_post(self):
        with patch.object(l, 'send_http', return_value={'accepted': True, 'code': 0}) as send:
            l.deliver(self.store, self.state, self.prepared())
            l.deliver(self.store, self.store.load(), self.prepared())
            self.assertEqual(send.call_count, 1)
        self.assertTrue(self.store.load()['first_complete'])
        self.assertEqual(len(self.store.load()['sent']), 1)

    def test_receipt_recovers_state_commit_crash(self):
        save = self.store.save
        def interrupted(s):
            if s['pending'] is None: raise OSError('disk interrupted')
            save(s)
        with patch.object(l, 'send_http', return_value={'accepted': True, 'code': 0}), patch.object(self.store, 'save', side_effect=interrupted):
            with self.assertRaises(OSError): l.deliver(self.store, self.state, self.prepared())
        state = self.store.load()
        self.assertIsNone(state['pending'])
        self.assertEqual(len(state['sent']), 1)

    def test_definitive_rejection_allows_retry(self):
        with patch.object(l, 'send_http', return_value={'accepted': False, 'code': 19024}):
            with self.assertRaises(d.Failure): l.deliver(self.store, self.state, self.prepared())
        self.assertIsNone(self.store.load()['pending'])
        self.assertFalse(self.store.load()['first_complete'])

    def test_empty_silent_first_only_once(self):
        p = self.prepared()
        p['items'] = []
        with patch.object(l, 'send_http') as send:
            l.deliver(self.store, self.state, p)
            send.assert_not_called()
        self.assertTrue(self.store.load()['first_complete'])


if __name__ == '__main__': unittest.main()
