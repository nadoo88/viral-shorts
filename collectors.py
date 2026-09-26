"""트렌드 수집기
- Google News RSS (한국/해외 키워드 검색)
- Google Trends 일간 급상승 RSS (KR/US/JP)
- Reddit 공개 JSON (주간 top) — 영어권에서 먼저 터진 소재
- YouTube Data API (조회수순 Shorts) — 유튜브에서 폭발한 소재
- references.txt — 쓰레드/인스타에서 직접 본 링크·메모 (공개 트렌드 API 없음)

각 수집기는 실패해도 전체가 멈추지 않도록 빈 리스트를 돌려줍니다.
"""
from __future__ import annotations

import os
import re
import html
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict

import requests

UA = {"User-Agent": "Mozilla/5.0 (viral-shorts-bot; +https://github.com/nadoo88)"}
TIMEOUT = 15


@dataclass
class Signal:
    category: str
    title: str
    url: str = ""
    source: str = ""          # google_news / reddit / youtube / trends / reference
    score: float = 0.0        # 플랫폼 내 인기 지표 (업보트, 조회수 등)
    summary: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def _clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


# ── Google News RSS ─────────────────────────────────────────
def google_news(category: str, query: str, lang="en", country="US", limit=8):
    q = urllib.parse.quote(f"{query} when:7d")
    url = f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={country}&ceid={country}:{lang}"
    return _parse_rss(category, url, "google_news", limit)


def rss_feed(category: str, url: str, limit=10):
    return _parse_rss(category, url, "google_news", limit)


def _parse_rss(category, url, source, limit):
    try:
        root = ET.fromstring(_get(url).content)
    except Exception as e:  # noqa: BLE001
        print(f"  [rss 실패] {url[:70]}… {e}")
        return []
    out = []
    for item in root.iter("item"):
        title = _clean(item.findtext("title", ""))
        link = item.findtext("link", "")
        desc = _clean(item.findtext("description", ""))
        if title:
            out.append(Signal(category, title, link, source, 0, desc[:300]))
        if len(out) >= limit:
            break
    return out


# ── Google Trends 일간 급상승 ─────────────────────────────────
def google_trends(category: str, geo="KR", limit=15):
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    try:
        root = ET.fromstring(_get(url).content)
    except Exception as e:  # noqa: BLE001
        print(f"  [trends 실패] {geo}: {e}")
        return []
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        traffic = item.findtext("ht:approx_traffic", "0", ns).replace("+", "").replace(",", "")
        try:
            score = float(traffic)
        except ValueError:
            score = 0
        news = item.find("ht:news_item", ns)
        link = news.findtext("ht:news_item_url", "", ns) if news is not None else ""
        out.append(Signal(category, title, link, f"trends_{geo}", score))
        if len(out) >= limit:
            break
    return out


# ── Reddit ─────────────────────────────────────────────────
def reddit_top(category: str, subreddit: str, limit=10):
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=week&limit={limit}"
    try:
        data = _get(url).json()
    except Exception as e:  # noqa: BLE001
        print(f"  [reddit 실패] r/{subreddit}: {e}")
        return []
    out = []
    for child in data.get("data", {}).get("children", []):
        d = child["data"]
        if d.get("over_18") or d.get("stickied"):
            continue
        out.append(Signal(
            category, d["title"], "https://www.reddit.com" + d["permalink"],
            f"reddit/r/{subreddit}", float(d.get("ups", 0)),
            _clean(d.get("selftext", ""))[:400],
        ))
    return out


# ── YouTube Shorts (Data API v3) ───────────────────────────
def youtube_shorts(category: str, query: str, limit=10):
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return []
    try:
        s = _get("https://www.googleapis.com/youtube/v3/search", params={
            "part": "snippet", "q": query, "type": "video", "videoDuration": "short",
            "order": "viewCount", "maxResults": limit, "key": key,
            "publishedAfter": _days_ago_iso(14),
        }).json()
        ids = [i["id"]["videoId"] for i in s.get("items", [])]
        if not ids:
            return []
        v = _get("https://www.googleapis.com/youtube/v3/videos", params={
            "part": "statistics,snippet", "id": ",".join(ids), "key": key,
        }).json()
    except Exception as e:  # noqa: BLE001
        print(f"  [youtube 실패] {query}: {e}")
        return []
    out = []
    for it in v.get("items", []):
        views = float(it["statistics"].get("viewCount", 0))
        sn = it["snippet"]
        out.append(Signal(
            category, sn["title"], f"https://www.youtube.com/shorts/{it['id']}",
            "youtube_shorts", views, _clean(sn.get("description", ""))[:300],
            {"channel": sn.get("channelTitle")},
        ))
    return out


def _days_ago_iso(days):
    import datetime as dt
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 쓰레드/인스타 레퍼런스 (수동) ─────────────────────────
def references(path: str):
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        cat, body = line.split("|", 1)
        url = body if body.startswith("http") else ""
        src = "threads" if "threads" in body else "instagram" if "instagram" in body else "reference"
        out.append(Signal(cat.strip(), body.strip()[:200], url, src, 1e6))
    return out


# ── 전체 수집 ───────────────────────────────────────────────
def collect_all(cfg: dict) -> dict[str, list[Signal]]:
    by_cat: dict[str, list[Signal]] = {}
    for cat, c in cfg["categories"].items():
        print(f"▶ [{c['label']}] 수집 중…")
        sig: list[Signal] = []
        for kw in c.get("en_keywords", [])[:3]:
            sig += google_news(cat, kw, "en", "US", 6)
        for kw in c.get("ko_keywords", [])[:2]:
            sig += google_news(cat, kw, "ko", "KR", 5)
        for feed in c.get("google_news_feeds", []):
            sig += rss_feed(cat, feed, 10)
        for sub in c.get("subreddits", []):
            sig += reddit_top(cat, sub, 8)
        for q in c.get("youtube_queries", []):
            sig += youtube_shorts(cat, q, 8)
        by_cat[cat] = sig
        print(f"   └ {len(sig)}개 신호")
    for s in references(cfg.get("references_file", "references.txt")):
        by_cat.setdefault(s.category, []).append(s)
    return by_cat


def rank(signals: list[Signal], top=12) -> list[Signal]:
    """플랫폼별 점수를 정규화해 상위 신호만 작성기에 넘김."""
    by_src: dict[str, float] = {}
    for s in signals:
        key = s.source.split("/")[0]
        by_src[key] = max(by_src.get(key, 0), s.score)
    weight = {"youtube_shorts": 1.3, "reddit": 1.2, "threads": 1.4, "instagram": 1.4,
              "reference": 1.4, "google_news": 1.0}
    def norm(s):
        key = s.source.split("/")[0]
        m = by_src.get(key) or 1
        base = s.score / m if m else 0.5
        return (base + 0.3) * weight.get(key, 1.0)
    seen, out = set(), []
    for s in sorted(signals, key=norm, reverse=True):
        k = s.title.lower()[:60]
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= top:
            break
    return out
