"""Local Codex editorial pipeline; Python 3.11+, no model API or cloud scheduler."""
import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

import digest as d

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get('AI_DIGEST_HOME') or Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'AiRdDigest')


def now():
    return dt.datetime.now(d.CN)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


class Lock:
    """OS-owned advisory lock: crash releases it; a second command fails closed."""
    def __enter__(self):
        HOME.mkdir(parents=True, exist_ok=True)
        self.f = (HOME / 'process.lock').open('a+b')
        if os.fstat(self.f.fileno()).st_size == 0:
            self.f.write(b'0')
            self.f.flush()
        self.f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            raise d.Failure('another digest command is running') from None
        return self

    def __exit__(self, *args):
        self.f.close()


class Store:
    def __init__(self, initialize=False):
        self.path = HOME / 'state.sqlite3'
        if not initialize and not self.path.is_file():
            raise d.Failure('persistent database missing; refusing to reset history')
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        if initialize:
            self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS receipts (delivery_key TEXT PRIMARY KEY, data TEXT NOT NULL)')
            self.db.execute('INSERT OR IGNORE INTO state VALUES (1, ?)', (json.dumps({
                'schema': 2, 'first_complete': False, 'first_cutoff': None, 'sent': [],
                'deliveries': {}, 'pending': None, 'legacy_test': None}),))
            self.db.commit()

    def load(self):
        row = self.db.execute('SELECT data FROM state WHERE id=1').fetchone()
        if not row:
            raise d.Failure('state missing; refusing to reset history')
        state = json.loads(row[0])
        if state.get('schema') != 2 or not isinstance(state.get('sent'), list):
            raise d.Failure('invalid state schema')
        pending = state.get('pending')
        if pending and self.db.execute('SELECT 1 FROM receipts WHERE delivery_key=?', (pending['key'],)).fetchone():
            self.confirm(state)
            self.save(state)
        return state

    def save(self, state):
        with self.db:
            self.db.execute('UPDATE state SET data=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))

    def receipt(self, key, value):
        with self.db:
            self.db.execute('INSERT INTO receipts VALUES (?, ?)', (key, json.dumps(value)))

    def confirm(self, state):
        p = state['pending']
        state['deliveries'][p['key']] = {'at': now().isoformat(), 'count': len(p['items']), 'status': 'accepted'}
        if not p['test']:
            state['sent'].extend(p['items'])
            if p['first']:
                state['first_complete'] = True
                state['first_cutoff'] = p['date']
        state['pending'] = None


def dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise d.Failure('Windows DPAPI required; on other OS use FEISHU_WEBHOOK environment variable')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, dest = Blob(len(data), buf), Blob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest))
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), 'AI RD Digest', None, None, None, 1, ctypes.byref(dest))
    if not ok:
        raise d.Failure('Windows secret protection failed')
    try:
        return ctypes.string_at(dest.pbData, dest.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(dest.pbData)


def validate_webhook(url):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != 'https' or p.hostname != 'open.feishu.cn' or p.username or p.password
        or not re.fullmatch(r'/open-apis/bot/v2/hook/[A-Za-z0-9-]+', p.path) or p.query or p.fragment):
        raise d.Failure('invalid Feishu webhook (value redacted)')
    return url


def send_http(payload):
    url = os.environ.get('FEISHU_WEBHOOK')
    if not url:
        url = dpapi((HOME / 'webhook.dpapi').read_bytes(), decrypt=True).decode('utf-8')
    validate_webhook(url)
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': d.UA}, method='POST')
    settings = read_json(HOME / 'settings.json') if (HOME / 'settings.json').exists() else {}
    feishu_proxy = settings.get('feishu_proxy')
    route = urllib.request.ProxyHandler({'https': feishu_proxy} if feishu_proxy else {})
    # One POST only: Feishu custom bots do not provide an idempotency key.
    try:
        with urllib.request.build_opener(route, d.NoRedirect()).open(req, timeout=25) as r:
            status = r.status
            result = json.loads(r.read(65536).decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise d.Failure(f'Feishu HTTP {e.code}; delivery outcome unresolved, no automatic retry') from None
    except Exception:
        raise d.Failure('Feishu transport/response failure; outcome unresolved, no automatic retry') from None
    code = result.get('code', result.get('StatusCode'))
    return {'http_status': status, 'code': code, 'accepted': type(code) is int and code == 0,
            'received_at': now().isoformat()}


def hosts(config, org):
    return set(config['sources'][org]['hosts'])


def validate_source(a, config, today):
    org = a.get('organization')
    if org not in config['sources']:
        raise d.Failure('unrecognized organization')
    url = a.get('url', '')
    p = urllib.parse.urlsplit(url)
    if not d.article_url(url, hosts(config, org)) or p.query or p.fragment:
        raise d.Failure('article URL is outside official allowlist')
    if d.day(a.get('published', '')) != a.get('published') or a['published'] > today:
        raise d.Failure('invalid/future publication date')
    if not a.get('date_source') or len(a.get('body', '')) < 500 or not a.get('title'):
        raise d.Failure('missing source body/title/publication evidence')
    a['url'] = d.canonical(url)
    a['aliases'] = [a['url']]
    return a


def collect(config, state, target):
    """Pure GET collection. Codex can import official web-tool evidence if blocked."""
    from concurrent.futures import ThreadPoolExecutor
    today = now().date().isoformat()
    # Discovery uses a fixed floor so delayed discoveries are not silently lost.
    sources, health = [], {}
    for org, cfg in config['sources'].items():
        try:
            urls, stats = d.discover(cfg, config['start_date'])
        except d.Failure:
            health[org] = {'status': 'blocked', 'needs_codex_web_fallback': True}
            continue
        entries = sorted(urls.items(), key=lambda x: (x[1].get('pub') or '', x[1].get('modified') or ''), reverse=True)
        truncated = len(entries) > 150
        entries = entries[:150]
        def fetch(entry):
            u, hint = entry
            try:
                return d.extract(u, d.http(u, retries=1, allowed_hosts=hosts(config, org)), org, hint['pub'], hosts(config, org))
            except d.Failure:
                return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            result = list(pool.map(fetch, entries))
        valid = [a for a in result if a and config['start_date'] <= a['published'] <= today and not d.duplicate(a, state['sent'])]
        sources.extend(valid)
        health[org] = {'status': 'ok', 'discovery': stats, 'candidate_count': len(valid),
                       'fetch_failures': sum(a is None for a in result),
                       'budget_truncated': truncated,
                       'needs_codex_web_fallback': truncated or any(a is None for a in result)}
        write_json(target, {'schema': 1, 'date': today, 'transport': 'local-http', 'coverage': health, 'sources': sources})
        print(json.dumps({'organization': org, 'candidates': len(valid), 'needs_web_fallback': health[org]['needs_codex_web_fallback']}), flush=True)
    report = {'schema': 1, 'date': today, 'transport': 'local-http', 'coverage': health, 'sources': sources}
    write_json(target, report)
    print(json.dumps({'collected': len(sources), 'coverage': health}, ensure_ascii=False))


def prepare(config, state, sources_path, review_path, target):
    src, review = read_json(sources_path), read_json(review_path)
    today = now().date().isoformat()
    if src.get('date') != today or review.get('date') != today:
        raise d.Failure('stale source/review report; refresh today before sending')
    first = not state['first_complete']
    if not first and 'daily:' + today in state['deliveries']:
        items = []
    else:
        all_sources = {}
        for original in src['sources']:
            a = validate_source(original, config, today)
            all_sources[a['url']] = a
        items = []
        for choice in review['items']:
            key = d.canonical(choice['url'])
            if key not in all_sources:
                raise d.Failure('review URL absent from source evidence')
            a = all_sources[key]
            if a['published'] < config['start_date']:
                raise d.Failure('article predates first-edition floor')
            if not first and a['published'] <= state['first_cutoff']:
                continue  # Never trickle unselected first-edition leftovers out later.
            required = ('category', 'summary', 'value', 'priority', 'score', 'story_key', 'evidence')
            if not all(k in choice for k in required):
                raise d.Failure('editorial review incomplete')
            if choice['priority'] not in ('P0', 'P1', 'P2') or type(choice['score']) not in (int, float):
                raise d.Failure('invalid editorial priority/score')
            if choice['score'] < 75 or choice['score'] > 100 or (choice['priority'] == 'P2' and choice['score'] < 95):
                raise d.Failure('relevance below threshold')
            n = len(re.findall(r'[\u4e00-\u9fff]', choice['summary'] + choice['value']))
            if not 50 <= n <= 100:
                raise d.Failure('summary/value must total 50-100 Chinese characters')
            if not choice['evidence'] or any(not isinstance(q, str) or len(q) < 15 or q not in a['body'] for q in choice['evidence']):
                raise d.Failure('evidence quote missing from official body')
            item = {k: v for k, v in a.items() if k != 'body'}
            item.update({k: choice[k] for k in required if k != 'evidence'})
            if not d.duplicate(item, state['sent'] + items):
                items.append(item)
        items.sort(key=lambda a: (a['priority'], -a['score']))
        items = items[:config['max_articles']]
    # Both organizations require a live official index check, even for a silent day.
    for org in config['sources']:
        if src.get('coverage', {}).get(org, {}).get('status') != 'ok':
            raise d.Failure('official coverage incomplete; do not mark a failed crawl as a quiet day')
    prepared = {'schema': 1, 'date': today, 'first': first, 'items': items,
        'coverage': src['coverage'], 'card': d.card(items, today, first=first) if items else None,
        'sources_path': str(Path(sources_path).resolve()), 'review_path': str(Path(review_path).resolve()),
        'sources_sha256': hashlib.sha256(Path(sources_path).read_bytes()).hexdigest(),
        'review_sha256': hashlib.sha256(Path(review_path).read_bytes()).hexdigest(),
        'prepared_at': now().isoformat()}
    write_json(target, prepared)
    print(json.dumps({'dry_run': True, 'selected': len(items), 'first': first, 'sent': False}, ensure_ascii=False))


def deliver(store, state, prepared=None, test=False):
    today = now().date().isoformat()
    if state['pending']:
        raise d.Failure('unresolved delivery; explicit reconciliation required before sending')
    if (state.get('legacy_test') or {}).get('status') == 'pending':
        raise d.Failure('legacy connectivity test unresolved')
    key = ('test:' if test else 'daily:') + today
    if key in state['deliveries']:
        print('already accepted today; silent')
        return
    if test:
        items, first, payload = [], False, d.card([], today, test=True)
    else:
        if prepared['date'] != today or prepared['first'] != (not state['first_complete']):
            raise d.Failure('stale edition; run prepare again')
        items, first = prepared['items'], prepared['first']
        for a in items:
            if d.duplicate(a, state['sent']):
                raise d.Failure('concurrent/previous send changed history; run prepare again')
        if not items:
            if first:
                state['first_complete'], state['first_cutoff'] = True, today
                store.save(state)
            print('no qualifying articles; silent')
            return
        payload = d.card(items, today, first=first)
    state['pending'] = {'key': key, 'date': today, 'items': items, 'first': first, 'test': test,
        'payload_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), 'at': now().isoformat()}
    store.save(state)  # Reserve durably before network mutation.
    result = send_http(payload)
    if not result['accepted']:
        # A numeric nonzero Feishu response is a definitive rejection, safe to retry later.
        if type(result['code']) is int:
            state['pending'] = None
            store.save(state)
        write_json(HOME / 'last-rejection.json', result)
        raise d.Failure('Feishu returned non-success code; no delivery recorded')
    store.receipt(key, result)  # Separate durable receipt recovers a later state-write crash.
    store.confirm(state)
    store.save(state)
    print(json.dumps({'delivery': key, 'articles': len(items), **result}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['initialize', 'install-secret', 'legacy-not-received', 'status', 'collect', 'prepare', 'test-send', 'send', 'reconcile-not-sent', 'reconcile-sent', 'backup'])
    p.add_argument('--file')
    p.add_argument('--sources')
    p.add_argument('--review')
    p.add_argument('--out')
    p.add_argument('--reason')
    args = p.parse_args()
    config = read_json(ROOT / 'config.json')
    settings_path = HOME / 'settings.json'
    if settings_path.exists():
        settings = read_json(settings_path)
        proxy = settings.get('https_proxy')
        if proxy:
            os.environ['https_proxy'] = proxy
            os.environ['http_proxy'] = proxy
    with Lock():
        store = Store(initialize=args.mode == 'initialize')
        state = store.load()
        if args.mode == 'initialize':
            print('local persistent state ready; idempotent initialization preserves history')
        elif args.mode == 'install-secret':
            secret = validate_webhook(Path(args.file).read_text(encoding='utf-8-sig').strip())
            path = HOME / 'webhook.dpapi'
            path.write_bytes(dpapi(secret.encode()))
            if dpapi(path.read_bytes(), decrypt=True).decode() != secret:
                raise d.Failure('secret roundtrip check failed')
            print('webhook encrypted with current Windows user DPAPI; roundtrip verified')
        elif args.mode == 'legacy-not-received':
            if not args.reason:
                raise d.Failure('explicit user confirmation reason required')
            original = read_json(args.file)
            state['legacy_test'] = {**original, 'status': 'confirmed_not_received', 'reason': args.reason, 'resolved_at': now().isoformat()}
            store.save(state)
            print('legacy test reconciled as not received; preserved original attempt metadata')
        elif args.mode == 'status':
            receipts = [json.loads(r[0]) for r in store.db.execute('SELECT data FROM receipts')]
            print(json.dumps({'state_home': str(HOME), 'first_complete': state['first_complete'],
                'first_cutoff': state['first_cutoff'], 'sent_count': len(state['sent']), 'sent_urls': [a['url'] for a in state['sent']],
                'pending': bool(state['pending']), 'legacy_test': state['legacy_test'],
                'deliveries': state['deliveries'], 'receipts': receipts}, ensure_ascii=False, indent=2))
        elif args.mode == 'collect':
            collect(config, state, args.out or ROOT / 'work/sources.json')
        elif args.mode == 'prepare':
            prepare(config, state, args.sources, args.review, args.out or ROOT / 'work/prepared.json')
        elif args.mode == 'test-send':
            deliver(store, state, test=True)
        elif args.mode == 'send':
            if 'daily:' + now().date().isoformat() in state['deliveries']:
                print('already accepted today; silent')
                return
            prepared = read_json(args.file)
            # Revalidate actual source, evidence, summaries, date window and history at send time.
            for field, hash_field in [('sources_path', 'sources_sha256'), ('review_path', 'review_sha256')]:
                if hashlib.sha256(Path(prepared[field]).read_bytes()).hexdigest() != prepared[hash_field]:
                    raise d.Failure('source/review changed after dry-run; prepare again')
            temp = HOME / 'revalidated.json'
            prepare(config, state, prepared['sources_path'], prepared['review_path'], temp)
            checked = read_json(temp)
            if any(checked[k] != prepared[k] for k in ('date', 'first', 'items', 'card')):
                raise d.Failure('preview/history changed; inspect a fresh dry-run before sending')
            deliver(store, state, checked)
        elif args.mode.startswith('reconcile-'):
            if not state['pending'] or not args.reason:
                raise d.Failure('pending delivery and explicit operator reason required')
            write_json(HOME / 'reconciliations' / (uuid.uuid4().hex + '.json'), {'pending': state['pending'], 'reason': args.reason, 'mode': args.mode})
            if args.mode == 'reconcile-sent':
                store.receipt(state['pending']['key'], {'accepted': True, 'operator_confirmed': True, 'at': now().isoformat()})
                store.confirm(state)
            else:
                state['pending'] = None
            store.save(state)
            print('delivery reconciled')
        elif args.mode == 'backup':
            path = HOME / 'backups' / (now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
            path.parent.mkdir(exist_ok=True)
            with sqlite3.connect(path) as target:
                store.db.backup(target)
            print('consistent SQLite backup saved')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('ERROR: ' + (str(e) if isinstance(e, d.Failure) else 'operation failed; sensitive details redacted'), file=sys.stderr)
        sys.exit(1)
