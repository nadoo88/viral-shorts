"""결과 내보내기: posts.json / posts.md / index.html(복사·게시 버튼 달린 미리보기)"""
from __future__ import annotations

import html
import json
import os
import urllib.parse

LABEL = {"diet": "다이어트", "workout": "살빼는운동", "world": "해외이슈", "home": "살림꿀템", "health": "건강"}


def x_len(s: str) -> int:
    """X 글자수 규칙: CJK는 2, 나머지 1 (280 한도)."""
    return sum(2 if ord(c) > 0x10FF else 1 for c in s)


def export(posts: list[dict], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "posts.json"), "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    _md(posts, os.path.join(out_dir, "posts.md"))
    _html(posts, os.path.join(out_dir, "index.html"))


def _full_post(p):
    tags = " ".join(p.get("hashtags", [])[:2])
    return f"{p['x_post']}\n\n{tags}".strip()


def _md(posts, path):
    L = ["# 오늘의 바이럴 쇼츠 패키지\n"]
    for i, p in enumerate(posts, 1):
        L += [f"## {i}. [{LABEL.get(p['category'])}] {p['title']}",
              f"**후킹:** {p['hook']}\n", "### X 단문", "```", _full_post(p), "```",
              "### X 스레드"]
        L += [f"{j}. {t}" for j, t in enumerate(p.get("x_thread", []), 1)]
        L += ["", "### 쇼츠 장면", "| # | 자막 | 강조 | 비주얼 |", "|---|---|---|---|"]
        L += [f"| {j} | {s['text'].replace(chr(10), ' / ')} | {s.get('highlight','')} | {s.get('visual','')} |"
              for j, s in enumerate(p["scenes"], 1)]
        L += ["", f"**촬영/생성 가이드:** {p.get('shooting_guide','')}"]
        if p.get("sources"):
            L += ["", "**출처:** " + " · ".join(f"[{s['title']}]({s['url']})" for s in p["sources"])]
        if p.get("credits"):
            L += ["", "**미디어 크레딧:** " + ", ".join(sorted(set(p["credits"])))]
        L += [f"\n_왜 터지나:_ {p.get('why_viral','')}", "\n---\n"]
    open(path, "w", encoding="utf-8").write("\n".join(L))


def _html(posts, path):
    cards = []
    for i, p in enumerate(posts):
        body = _full_post(p)
        n = x_len(body)
        intent = "https://x.com/intent/post?text=" + urllib.parse.quote(body)
        thread = "".join(f"<li>{html.escape(t)}</li>" for t in p.get("x_thread", []))
        src = "".join(f'<a href="{html.escape(s["url"])}" target="_blank">{html.escape(s["title"])}</a>'
                      for s in p.get("sources", []))
        media = ""
        if p.get("video"):
            media = f'<video src="{html.escape(p["video"])}" controls playsinline loop></video>'
        elif p.get("thumbnail"):
            media = f'<img src="{html.escape(p["thumbnail"])}">'
        cards.append(f"""
<article class="card">
  <div class="media">{media}</div>
  <div class="body">
    <span class="badge {p['category']}">{LABEL.get(p['category'])}</span>
    <h2>{html.escape(p['title'])}</h2>
    <pre id="p{i}">{html.escape(body)}</pre>
    <div class="row"><span class="cnt {'over' if n > 280 else ''}">{len(body)}자{' · X 프리미엄 필요' if n > 280 else ''}</span>
      <button onclick="cp('p{i}',this)">복사</button>
      <a class="btn" href="{intent}" target="_blank">X에 올리기</a></div>
    <details><summary>스레드 {len(p.get('x_thread', []))}개</summary><ol>{thread}</ol></details>
    <p class="meta">{html.escape(p.get('why_viral',''))}</p>
    <div class="src">{src}</div>
  </div>
</article>""")
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>바이럴 쇼츠 패키지</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f4f4f1;--card:#fff;--ink:#141414;--sub:#6b6b6b;--line:#e4e4e0;--acc:#ffdd00}}
@media (prefers-color-scheme:dark){{:root{{--bg:#101010;--card:#1b1b1b;--ink:#f1f1f1;--sub:#9a9a9a;--line:#2b2b2b}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:'Noto Sans KR',sans-serif}}
header{{padding:28px 16px 8px;max-width:1100px;margin:auto}}h1{{font-weight:900;font-size:26px;margin:0}}
header p{{color:var(--sub);margin:6px 0 0}}
main{{max-width:1100px;margin:auto;padding:16px;display:grid;gap:18px;grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;display:flex;flex-direction:column}}
.media video,.media img{{width:100%;aspect-ratio:9/16;object-fit:cover;background:#000;display:block}}
.media img{{aspect-ratio:1}}.body{{padding:16px}}
.badge{{font-size:12px;font-weight:700;padding:4px 10px;border-radius:99px;color:#fff}}
.diet{{background:#ff465a}}.workout{{background:#0096ff}}.world{{background:#8250ff}}.home{{background:#00aa78}}.health{{background:#e33c3c}}
h2{{font-size:18px;margin:10px 0}}pre{{white-space:pre-wrap;font-family:inherit;font-size:15px;line-height:1.55;
background:var(--bg);padding:12px;border-radius:12px;margin:0}}
.row{{display:flex;gap:8px;align-items:center;margin:10px 0}}.cnt{{color:var(--sub);font-size:13px;margin-right:auto}}
.over{{color:#e33}}button,.btn{{border:0;border-radius:10px;padding:8px 14px;font:700 14px 'Noto Sans KR';cursor:pointer;
text-decoration:none}}button{{background:var(--line);color:var(--ink)}}.btn{{background:var(--ink);color:var(--card)}}
details{{font-size:14px;color:var(--sub)}}ol{{padding-left:18px;color:var(--ink)}}.meta{{font-size:13px;color:var(--sub)}}
.src a{{display:block;font-size:12px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
</style></head><body>
<header><h1>오늘의 바이럴 쇼츠 패키지</h1><p>{len(posts)}개 · 복사 → X에 올리기 · 영상은 길게 눌러 저장</p></header>
<main>{''.join(cards)}</main>
<script>function cp(id,b){{navigator.clipboard.writeText(document.getElementById(id).innerText);b.textContent='복사됨';
setTimeout(()=>b.textContent='복사',1200)}}</script></body></html>"""
    open(path, "w", encoding="utf-8").write(page)
