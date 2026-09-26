"""중복 방지
1) 로컬 SQLite 히스토리 — 내가 이미 올린 글과 비슷하면 버림
2) (선택) X API v2 최근 검색 — 핵심 키워드로 이미 X에서 퍼진 소재인지 확인
   * X API 검색은 유료 플랜(Basic 이상) 필요. 토큰 없으면 건너뜀.
"""
from __future__ import annotations

import os
import re
import sqlite3
import datetime as dt
from difflib import SequenceMatcher

import requests

DB = os.path.join(os.path.dirname(__file__), "history.db")


def _conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS posts(
        id INTEGER PRIMARY KEY, category TEXT, title TEXT, body TEXT,
        keywords TEXT, created TEXT)""")
    return c


def _norm(t: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", t or "").lower()


def is_duplicate(title: str, body: str, threshold=0.55) -> tuple[bool, str]:
    target = _norm(title + body[:200])
    with _conn() as c:
        rows = c.execute("SELECT title, body FROM posts ORDER BY id DESC LIMIT 500").fetchall()
    for t, b in rows:
        r = SequenceMatcher(None, target, _norm(t + (b or "")[:200])).ratio()
        if r >= threshold:
            return True, f"과거 글과 {r:.0%} 유사: {t}"
    return False, ""


def used_titles(limit=80) -> list[str]:
    with _conn() as c:
        return [r[0] for r in c.execute(
            "SELECT title FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def save(category: str, title: str, body: str, keywords: list[str]):
    with _conn() as c:
        c.execute("INSERT INTO posts(category,title,body,keywords,created) VALUES(?,?,?,?,?)",
                  (category, title, body, ",".join(keywords), dt.datetime.now().isoformat()))


def x_already_viral(keywords: list[str], min_likes=3000) -> tuple[bool, str]:
    """X에서 같은 키워드 조합으로 좋아요 min_likes 이상 글이 이미 있으면 True."""
    token = os.getenv("X_BEARER_TOKEN")
    if not token or not keywords:
        return False, "X 검사 생략(토큰 없음)"
    q = " ".join(f'"{k}"' if " " in k else k for k in keywords[:3]) + " lang:ko -is:retweet"
    try:
        r = requests.get(
            "https://api.x.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {token}"},
            params={"query": q, "max_results": 50, "tweet.fields": "public_metrics"},
            timeout=15,
        )
        if r.status_code != 200:
            return False, f"X 검사 실패({r.status_code})"
        for tw in r.json().get("data", []):
            likes = tw["public_metrics"]["like_count"]
            if likes >= min_likes:
                return True, f"X에 이미 좋아요 {likes:,}개 글 존재"
        return False, "X 최근 7일 내 대형 중복 없음"
    except Exception as e:  # noqa: BLE001
        return False, f"X 검사 오류: {e}"
