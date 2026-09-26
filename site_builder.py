"""GitHub Pages 웹사이트 빌더

archive/<실행시각>/posts.json (+ jpg 썸네일)  ← 매 실행마다 커밋되는 가벼운 기록
output/<실행시각>/*.mp4                      ← 이번 실행에서 새로 만든 영상
→ _site/  (index.html + 썸네일 + 최근 영상)   ← Pages 로 배포

영상은 저장소를 무겁게 만들지 않도록 git에 커밋하지 않고,
이전 영상은 이미 배포된 사이트에서 다시 받아 최근 KEEP_VIDEO_RUNS 회차만 유지합니다.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(ROOT, "archive")
SITE = os.path.join(ROOT, "_site")
KEEP_VIDEO_RUNS = 10

LABEL = {"diet": "다이어트", "workout": "살빼는운동", "world": "해외이슈", "home": "살림꿀템", "health": "건강"}


def x_len(s: str) -> int:
    return sum(2 if ord(c) > 0x10FF else 1 for c in s)


def archive_run(out_dir: str) -> str:
    """이번 실행 결과(글·썸네일)를 archive/ 로 옮김. 영상은 _site 에만."""
    stamp = os.path.basename(os.path.normpath(out_dir))
    dst = os.path.join(ARCHIVE, stamp)
    os.makedirs(dst, exist_ok=True)
    shutil.copy(os.path.join(out_dir, "posts.json"), dst)
    for f in os.listdir(out_dir):
        if f.endswith(".jpg"):
            shutil.copy(os.path.join(out_dir, f), dst)
    return stamp


def fetch(url: str, path: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
            shutil.copyfileobj(r, f)
        return True
    except Exception:  # noqa: BLE001
        return False


def build(base_url: str = "", new_out: str | None = None, repo: str = ""):
    if new_out:
        archive_run(new_out)
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)

    runs = sorted([d for d in os.listdir(ARCHIVE) if os.path.isdir(os.path.join(ARCHIVE, d))],
                  reverse=True) if os.path.exists(ARCHIVE) else []
    data = []
    for ri, stamp in enumerate(runs):
        src = os.path.join(ARCHIVE, stamp)
        posts = json.load(open(os.path.join(src, "posts.json"), encoding="utf-8"))
        tdir = os.path.join(SITE, "r", stamp)
        os.makedirs(tdir, exist_ok=True)
        for p in posts:
            p["_run"] = stamp
            if p.get("thumbnail") and os.path.exists(os.path.join(src, p["thumbnail"])):
                shutil.copy(os.path.join(src, p["thumbnail"]), tdir)
                p["thumbnail"] = f"r/{stamp}/{p['thumbnail']}"
            else:
                p["thumbnail"] = ""
            if p.get("poster") and os.path.exists(os.path.join(src, p["poster"])):
                shutil.copy(os.path.join(src, p["poster"]), tdir)
                p["poster"] = f"r/{stamp}/{p['poster']}"
            else:
                p["poster"] = p["thumbnail"]
            vid = p.get("video")
            p["video"] = ""
            if vid and ri < KEEP_VIDEO_RUNS:
                dst = os.path.join(tdir, vid)
                ok = False
                for cand in ([os.path.join(new_out, vid)] if new_out and stamp == os.path.basename(os.path.normpath(new_out)) else []) \
                        + [os.path.join(src, vid)]:
                    if os.path.exists(cand):
                        shutil.copy(cand, dst)
                        ok = True
                        break
                if not ok and base_url:
                    ok = fetch(f"{base_url.rstrip('/')}/r/{stamp}/{urllib.parse.quote(vid)}", dst)
                if ok:
                    p["video"] = f"r/{stamp}/{vid}"
            data.append(p)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(page(data, repo))
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    print(f"✅ 사이트 빌드: 회차 {len(runs)}개 · 글 {len(data)}개 → {SITE}")


def run_label(stamp: str) -> str:
    # 20260926_1612 → 9월 26일 16:12
    try:
        return f"{int(stamp[4:6])}월 {int(stamp[6:8])}일 {stamp[9:11]}:{stamp[11:13]}"
    except (ValueError, IndexError):
        return stamp


def card(p: dict, i: int) -> str:
    tags = " ".join(p.get("hashtags", [])[:2])
    body = f"{p.get('x_post', '')}\n\n{tags}".strip()
    n = x_len(body)
    intent = "https://x.com/intent/post?text=" + urllib.parse.quote(body)
    thread = "\n\n".join(f"{j}/ {t}" for j, t in enumerate(p.get("x_thread", []), 1))
    if p.get("video"):
        media = (f'<video src="{p["video"]}" poster="{p.get("poster", "")}" controls playsinline '
                 f'preload="none"></video>')
    elif p.get("thumbnail"):
        media = f'<img src="{p["thumbnail"]}" alt="" loading="lazy" class="sq">'
    else:
        media = ""
    src = "".join(f'<a href="{html.escape(s.get("url", ""))}" target="_blank" rel="noopener">'
                  f'{html.escape(s.get("title", ""))}</a>' for s in p.get("sources", []) if s.get("url"))
    dl = (f'<a class="ghost" href="{p["video"]}" download>영상 저장</a>' if p.get("video") else "")
    offline = '<span class="warn">초안 · 번호 목록 채우고 게시</span>' if p.get("_writer") == "offline" else ""
    cat = p.get("category", "home")
    return f"""<article class="card" data-cat="{cat}">
  <div class="media">{media}</div>
  <div class="body">
    <div class="meta"><span class="badge {cat}">{LABEL.get(cat, cat)}</span>{offline}</div>
    <h3>{html.escape(p.get('title', ''))}</h3>
    <pre id="b{i}">{html.escape(body)}</pre>
    <div class="row">
      <span class="cnt{' over' if n > 280 else ''}">{len(body)}자{' · 프리미엄' if n > 280 else ''}</span>
      <button onclick="cp('b{i}',this)">복사</button>
      <a class="solid" href="{intent}" target="_blank" rel="noopener">X에 올리기</a>
    </div>
    <details><summary>스레드 {len(p.get('x_thread', []))}개</summary>
      <pre id="t{i}">{html.escape(thread)}</pre>
      <div class="row"><button onclick="cp('t{i}',this)">스레드 복사</button>{dl}</div>
    </details>
    <div class="src">{src}</div>
  </div>
</article>"""


def page(data: list, repo: str) -> str:
    groups, order = {}, []
    for p in data:
        if p["_run"] not in groups:
            groups[p["_run"]] = []
            order.append(p["_run"])
        groups[p["_run"]].append(p)
    sections, i = [], 0
    for k, stamp in enumerate(order):
        cards = []
        for p in groups[stamp]:
            cards.append(card(p, i))
            i += 1
        sections.append(f'<section class="run"><h2>{"최신 · " if k == 0 else ""}{run_label(stamp)}'
                        f'<span>{len(cards)}개</span></h2><div class="grid">{"".join(cards)}</div></section>')
    empty = '<p class="empty">아직 생성된 글이 없어요. 아래 "새로 만들기"로 첫 글을 만들어보세요.</p>'
    run_url = f"https://github.com/{repo}/actions/workflows/viral-shorts.yml" if repo else "#"
    chips = "".join(f'<button class="chip" data-f="{c}">{l}</button>' for c, l in LABEL.items())
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>바이럴 쇼츠 데일리</title>
<meta name="description" content="매일 자동 생성되는 X 바이럴글 + 쇼츠 영상">
<meta name="theme-color" content="#111111">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f5f4ef;--card:#fff;--ink:#111;--sub:#6d6d68;--line:#e5e3dc;--acc:#ffd400;--accInk:#111;
--diet:#ff465a;--workout:#1a8cff;--world:#7b4dff;--home:#00a676;--health:#e0433a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0e0e0e;--card:#181818;--ink:#f2f2f2;--sub:#9b9b96;--line:#2a2a2a}}}}
*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'Noto Sans KR',system-ui,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:0 16px}}
header{{padding:28px 0 12px}}
.brand{{display:flex;align-items:center;gap:10px}}
.dot{{width:14px;height:14px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 4px color-mix(in srgb,var(--acc) 35%,transparent)}}
h1{{font-size:clamp(24px,5vw,34px);font-weight:900;letter-spacing:-.02em;margin:0}}
.lead{{color:var(--sub);margin:8px 0 0;font-size:15px}}
nav{{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);
padding:10px 0;border-bottom:1px solid var(--line)}}
.chips{{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}}.chips::-webkit-scrollbar{{display:none}}
.chip{{flex:none;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:99px;padding:7px 14px;
font:500 14px 'Noto Sans KR';cursor:pointer}}.chip.on{{background:var(--ink);color:var(--bg);border-color:var(--ink)}}
.run h2{{font-size:17px;font-weight:700;margin:26px 0 12px;display:flex;align-items:baseline;gap:8px}}
.run h2 span{{color:var(--sub);font-size:13px;font-weight:500}}
.grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:20px;overflow:hidden;display:flex;flex-direction:column}}
.media video{{width:100%;aspect-ratio:9/16;object-fit:cover;background:#000;display:block}}
.media img.sq{{width:100%;aspect-ratio:1;object-fit:cover;display:block}}
.body{{padding:16px;display:flex;flex-direction:column;gap:10px}}
.meta{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.badge{{font-size:12px;font-weight:700;color:#fff;padding:4px 10px;border-radius:99px}}
.diet{{background:var(--diet)}}.workout{{background:var(--workout)}}.world{{background:var(--world)}}.home{{background:var(--home)}}.health{{background:var(--health)}}
.warn{{font-size:12px;color:#b25e00;background:#fff1dc;padding:3px 8px;border-radius:8px}}
h3{{font-size:18px;line-height:1.35;margin:0;font-weight:700}}
pre{{white-space:pre-wrap;word-break:keep-all;font-family:inherit;font-size:15px;line-height:1.6;background:var(--bg);
padding:14px;border-radius:14px;margin:0}}
.row{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.cnt{{color:var(--sub);font-size:13px;margin-right:auto}}.over{{color:var(--diet)}}
button,.solid,.ghost{{border:0;border-radius:12px;padding:10px 16px;font:700 14px 'Noto Sans KR';cursor:pointer;text-decoration:none;
min-height:42px;display:inline-flex;align-items:center}}
button{{background:var(--line);color:var(--ink)}}.solid{{background:var(--acc);color:var(--accInk)}}
.ghost{{background:transparent;color:var(--ink);border:1px solid var(--line)}}
details summary{{cursor:pointer;color:var(--sub);font-size:14px;padding:4px 0}}details pre{{margin:8px 0}}
.src a{{display:block;font-size:12px;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.make{{margin:40px 0 20px;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:20px}}
.make h2{{margin:0 0 6px;font-size:18px}}.make ol{{margin:10px 0 14px;padding-left:20px;line-height:1.8;color:var(--sub)}}
.empty{{color:var(--sub);padding:40px 0;text-align:center}}
footer{{color:var(--sub);font-size:12px;padding:24px 0 40px;text-align:center}}
.toast{{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:10px 18px;
border-radius:99px;font-size:14px;opacity:0;transition:.2s;pointer-events:none}}.toast.on{{opacity:1}}
</style></head><body>
<header class="wrap"><div class="brand"><span class="dot"></span><h1>바이럴 쇼츠 데일리</h1></div>
<p class="lead">매일 아침 자동 생성 · 복사해서 X에 바로 · 영상은 릴스·쇼츠·틱톡에</p></header>
<nav><div class="wrap chips"><button class="chip on" data-f="all">전체</button>{chips}</div></nav>
<main class="wrap">{''.join(sections) or empty}
<section class="make"><h2>새로 만들기</h2>
<ol><li>아래 버튼 → <b>Run workflow</b> 클릭</li><li><b>소재</b> 칸에 원하는 소재 입력 (비우면 트렌드 자동 4개)</li>
<li>초록 Run workflow → 약 5분 뒤 이 페이지 새로고침</li></ol>
<a class="solid" href="{run_url}" target="_blank" rel="noopener">소재 입력하고 만들기</a></section></main>
<footer>@luffynod00 · 영상 배경은 Pexels/Pixabay 무료 라이선스 · 게시 전 출처 확인</footer>
<div class="toast" id="toast">복사됨</div>
<script>
function cp(id,b){{const t=document.getElementById(id).innerText;
(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).catch(()=>{{const a=document.createElement('textarea');
a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove()}}).finally(()=>{{
const o=document.getElementById('toast');o.classList.add('on');setTimeout(()=>o.classList.remove('on'),1200)}})}}
document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{{document.querySelectorAll('.chip').forEach(x=>x.classList.remove('on'));
c.classList.add('on');const f=c.dataset.f;document.querySelectorAll('.card').forEach(k=>k.style.display=(f==='all'||k.dataset.cat===f)?'':'none');
document.querySelectorAll('.run').forEach(r=>r.style.display=[...r.querySelectorAll('.card')].some(k=>k.style.display!=='none')?'':'none')}});
document.addEventListener('play',e=>{{document.querySelectorAll('video').forEach(v=>{{if(v!==e.target)v.pause()}})}},true);
</script></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", help="이번 실행 output 폴더 (archive 에 추가)")
    ap.add_argument("--base-url", default=os.getenv("SITE_URL", ""))
    ap.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    a = ap.parse_args()
    build(a.base_url, a.new, a.repo)
