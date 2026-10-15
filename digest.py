"""Official-source AI digest. Python 3.11+, standard library only.

No article text, LLM output, or URL is ever evaluated as executable code.
Transport exceptions deliberately omit URLs, request bodies and credentials.
"""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import difflib
import json
from pathlib import Path
import re
import time
import unicodedata
import urllib.error
import urllib.parse as up
import urllib.request as ur
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent
CN = dt.timezone(dt.timedelta(hours=8))
UA = "Mozilla/5.0"


class Failure(Exception):
    pass


class NoRedirect(ur.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http(url, payload=None, headers=None, retries=2, allowed_hosts=None):
    """GET retries are safe. POST callers decide whether a retry is safe."""
    headers = {"User-Agent": UA, **(headers or {})}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    for attempt in range(retries):
        current = url
        try:
            for _ in range(6):
                p = up.urlsplit(current)
                if p.scheme != "https" or p.username or p.password or (allowed_hosts and p.hostname not in allowed_hosts):
                    raise Failure("unsafe destination rejected")
                try:
                    with ur.build_opener(NoRedirect()).open(ur.Request(current, data=raw, headers=headers), timeout=18) as r:
                        data = r.read(8_000_001)
                        if len(data) > 8_000_000:
                            raise Failure("response exceeds size limit")
                        return data.decode("utf-8", errors="replace")
                except urllib.error.HTTPError as e:
                    if payload is None and e.code in (301, 302, 303, 307, 308):
                        current = up.urljoin(current, e.headers.get("Location", ""))
                        continue
                    raise
            raise Failure("redirect limit exceeded")
        except Failure:
            raise
        except Exception:
            if attempt + 1 == retries:
                raise Failure("network request failed (details redacted)") from None
            time.sleep(2 ** attempt)


def canonical(url):
    p = up.urlsplit(url)
    host = (p.hostname or "").lower()
    if host == "anthropic.com":
        host = "www.anthropic.com"
    if host == "www.openai.com":
        host = "openai.com"
    path = re.sub(r"/+", "/", p.path).rstrip("/") or "/"
    path = re.sub(r"^/(?:en-US|en|zh-Hans-CN|zh-CN|ja-JP)(?=/)", "", path)
    return up.urlunsplit(("https", host, path, "", ""))


def norm(text):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", text).casefold())


def day(value):
    value = value.strip()
    try:
        return dt.date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (ValueError, TypeError):
        pass
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.meta, self.links, self.ld = {}, [], []
        self.title, self.main, self.all_text, self.times = [], [], [], []
        self.script = []
        self.canon = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            self.meta[a.get("property", a.get("name", ""))] = a.get("content", "")
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "link" and "canonical" in a.get("rel", ""):
            self.canon = a.get("href")
        if tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        if tag not in {"meta", "link", "img", "br", "hr", "input", "source", "wbr", "area", "base", "embed"}:
            self.stack.append((tag, a))
        if tag == "script":
            self.script = []

    def handle_endtag(self, tag):
        if tag == "script" and self.stack and self.stack[-1][1].get("type") == "application/ld+json":
            try:
                self.ld.append(json.loads("".join(self.script)))
            except ValueError:
                pass
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, value):
        tags = {x[0] for x in self.stack}
        if "script" in tags:
            self.script.append(value)
            return
        if tags & {"style", "nav", "footer", "header", "noscript"}:
            return
        value = re.sub(r"\s+", " ", value).strip()
        if not value:
            return
        self.all_text.append(value)
        if tags & {"main", "article"}:
            self.main.append(value)
        if "h1" in tags:
            self.title.append(value)


def ld_articles(obj):
    if isinstance(obj, list):
        for item in obj:
            yield from ld_articles(item)
    elif isinstance(obj, dict):
        typ = str(obj.get("@type", ""))
        if any(x in typ for x in ("Article", "BlogPosting", "Report")):
            yield obj
        if "@graph" in obj:
            yield from ld_articles(obj["@graph"])


def extract(url, html, org, feed_date=None, hosts=None):
    p = Page(html)
    title = " ".join(p.title) or p.meta.get("og:title", "")
    text = "\n".join(p.main or p.all_text)
    text = re.split(r"\n(?:Related content|Related articles|Read more)\n", text, maxsplit=1)[0]
    if not title or len(text) < 500:
        raise Failure("article missing title or substantive body")
    publication = None
    date_source = None
    for key in ("article:published_time", "datePublished", "publish_date"):
        publication = day(p.meta.get(key, ""))
        if publication:
            date_source = "publication metadata"
            break
    for obj in ld_articles(p.ld):
        if not publication:
            publication = day(str(obj.get("datePublished", "")))
            date_source = "JSON-LD datePublished" if publication else None
    if not publication:
        # Only near the article heading; never infer publication from sitemap lastmod.
        pos = text.find(title)
        head = text[max(pos, 0):max(pos, 0)+700]
        m = re.search(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?) \d{1,2}, \d{4}\b", head)
        if m:
            publication, date_source = day(m[0]), "visible article date"
    if not publication and feed_date:
        publication, date_source = day(feed_date), "official RSS pubDate"
    if not publication:
        raise Failure("publication date unverified")
    target = canonical(up.urljoin(url, p.canon or url))
    if hosts and up.urlsplit(target).hostname not in hosts:
        raise Failure("external canonical URL rejected")
    return {"url": target, "aliases": [canonical(url)], "title": title, "organization": org,
            "published": publication, "date_source": date_source, "body": text[:32000]}


def article_url(url, hosts):
    p = up.urlsplit(url)
    if p.hostname not in hosts or p.scheme != "https" or p.username or p.password:
        return False
    path = p.path
    if re.search(r"\.(pdf|png|svg|jpg|xml|zip|js|css)$", path, re.I):
        return False
    if re.match(r"^/[a-z]{2}(?:-[A-Za-z]{2,4})?/(index|news|research)/", path):
        return False
    if re.search(r"/(careers|jobs|legal|policies|privacy|events|customers|pricing)(/|$)", path):
        return False
    if p.hostname in ("openai.com", "www.openai.com"):
        return bool(re.match(r"^/(index|research)/[^/]+/?$", path))
    if p.hostname in ("www.anthropic.com", "anthropic.com"):
        # Includes future top-level research columns; LLM determines substance.
        return len([x for x in path.split("/") if x]) >= 2
    return len(path.strip("/")) > 3


def discover(source, floor):
    """Concurrent, bounded discovery; publication is still checked on article pages."""
    hosts = set(source['hosts'])
    candidates = {}
    health = dict(index_ok=0, feed_ok=0, sitemap_ok=0, failures=0, failed_urls=[], checked_urls=[])
    def add(url, pub=None, modified=None):
        if article_url(url, hosts):
            key = canonical(url)
            old = candidates.get(key, {})
            candidates[key] = {'pub': pub or old.get('pub'), 'modified': modified or old.get('modified')}
    def fetch(entry):
        kind, url = entry
        try:
            return kind, url, http(url, retries=1, allowed_hosts=hosts)
        except Failure:
            return kind, url, None
    entries = [('index', u) for u in source['indexes']] + [('feed', u) for u in source['feeds']] + [('sitemap', u) for u in source['sitemaps']]
    children = []
    def consume(results):
        for kind, url, body in results:
            if body is None:
                health['failures'] += 1
                health['failed_urls'].append(url)
                continue
            try:
                if kind == 'index':
                    for link in Page(body).links:
                        add(up.urljoin(url, link))
                else:
                    root = ET.fromstring(body)
                    if kind == 'feed':
                        for item in root.findall('.//item'):
                            pub = day(item.findtext('pubDate', ''))
                            if pub and pub >= floor:
                                add(item.findtext('link', ''), pub)
                    else:
                        for node in root:
                            vals = {x.tag.split('}')[-1]: x.text or '' for x in node}
                            loc, modified = vals.get('loc', ''), day(vals.get('lastmod', ''))
                            if node.tag.endswith('sitemap'):
                                if up.urlsplit(loc).hostname in hosts and not re.search(r'/(?:[a-z]{2}-[a-z]{2}|zh-hans|ja|ko|fr|de|es)/', loc, re.I):
                                    children.append(('sitemap', loc))
                            elif not modified or modified >= floor:
                                add(loc, modified=modified)
                health[kind + '_ok'] += 1
                health['checked_urls'].append(url)
            except (ValueError, ET.ParseError):
                health['failures'] += 1
                health['failed_urls'].append(url)
    with ThreadPoolExecutor(max_workers=8) as pool:
        consume(pool.map(fetch, entries))
        # One child level, English/default only; Codex checks coverage gaps via its web tool.
        children = list(dict.fromkeys(children))
        if len(children) > 8:
            health['sitemap_budget_truncated'] = True
        consume(pool.map(fetch, children[:8]))
    if not candidates:
        raise Failure('official discovery unavailable')
    return candidates, health


def duplicate(a, history):
    for b in history:
        if set([a["url"], *a.get("aliases", [])]) & set([b["url"], *b.get("aliases", [])]):
            return True
        if norm(a["title"]) == norm(b["title"]):
            return True
        if a.get("story_key") and norm(a["story_key"]) == norm(b.get("story_key", "")):
            return True
        if a["organization"] == b["organization"] and difflib.SequenceMatcher(None, norm(a["title"]), norm(b["title"])).ratio() > 0.94:
            return True
    return False


def card(items, today, first=False, test=False):
    title = "AI 研发情报｜10 月首期精选" if first else "🤖 AI 研发情报日报｜" + today
    if test:
        title = "AI 研发情报｜部署连通性测试"
    elements = []
    if test:
        elements.append({"tag": "markdown", "content": "飞书发送链路测试。此消息不代表每日调度已启用，也不计入文章去重记录。"})
    for i, a in enumerate(items, 1):
        def esc(s):
            return re.sub(r"([\\`*_\[\]<>])", r"\\\1", s).replace("\n", " ")
        elements.append({"tag": "markdown", "content":
            f"**{i}. {a['organization']}｜{esc(a['category'])}**\n**{esc(a['title'])}**\n官方发布：{a['published']}\n"
            f"{esc(a['summary'])}\n{esc(a['value'])}\n[🔗 官方原文]({a['url']})"})
    payload = {"msg_type": "interactive", "card": {"config": {"wide_screen_mode": True},
               "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"}, "elements": elements}}
    if len(json.dumps(payload, ensure_ascii=False).encode()) > 26000:
        raise Failure("card too large")
    return payload
