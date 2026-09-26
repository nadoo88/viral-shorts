"""바이럴 쇼츠 자동화 — 실행 진입점

  python main.py                  # 수집 → 작성 → 미디어 → 렌더 → 미리보기
  python main.py --demo           # API 키 없이 demo_posts.json 으로 영상까지 테스트
  python main.py --only diet,home # 특정 카테고리만
  python main.py --collect-only   # 트렌드 신호만 수집해서 signals.json 저장
  python main.py --no-video       # 글+썸네일만
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

import collectors, dedup, export, media, render, writer  # noqa: E402


def load_cfg():
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def produce(post, out_dir, idx, cfg, video=True):
    slug = f"{idx:02d}_{post['category']}"
    mdir = os.path.join(out_dir, "media", slug)
    print(f"  🎞  미디어 수집: {post['title']}")
    m = media.fetch_scene_media(post, mdir)
    post["credits"] = [x["credit"] for x in m if x]
    thumb = os.path.join(out_dir, f"{slug}.jpg")
    render.thumbnail(post, m, thumb, cfg)
    post["thumbnail"] = os.path.basename(thumb)
    if video and cfg.get("render_video", True):
        vp = os.path.join(out_dir, f"{slug}.mp4")
        print(f"  🎬 렌더링 → {os.path.basename(vp)}")
        pp = os.path.join(out_dir, f"{slug}_poster.jpg")
        render.render(post, m, vp, cfg, poster_path=pp)
        post["video"] = os.path.basename(vp)
        post["poster"] = os.path.basename(pp)
    return post


LABELS = {"diet": "다이어트", "workout": "살빼는운동", "world": "해외이슈", "home": "살림꿀템", "health": "건강"}
GUESS = {
    "health": ["암", "증상", "병원", "혈압", "당뇨", "통증", "질환", "건강검진", "치아", "잇몸"],
    "workout": ["운동", "스트레칭", "걷기", "홈트", "거북목", "골반", "스쿼트", "근육", "자세"],
    "diet": ["다이어트", "식단", "살", "칼로리", "혈당", "공복", "음식", "먹"],
    "world": ["일본", "미국", "중국", "해외", "외국", "유럽", "나라", "세계"],
}


def label_of(cat, cfg):
    return cfg["categories"].get(cat, {}).get("label") or LABELS.get(cat, cat)


def guess_category(topic, cfg):
    for cat, words in GUESS.items():
        if any(w in topic for w in words):
            return cat
    return "home"


def write_selected(cat, topic, sigs, cfg, out_dir, idx, video):
    label = label_of(cat, cfg)
    print(f"✍️  [{label}] 선택한 소재로 작성: {topic.splitlines()[0][:50]}")
    post = writer.write_post(cat, label, sigs, dedup.used_titles(), cfg, topic=topic)
    print(f"   └ 작성 완료 ({post.get('_writer')})")
    post = produce(post, out_dir, idx, cfg, video)
    dedup.save(cat, post["title"], post["x_post"], post.get("keywords", []))
    return post


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--input", default="demo_posts.json", help="--demo 때 쓸 글 JSON")
    ap.add_argument("--only", default="")
    ap.add_argument("--collect-only", action="store_true")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--topic", default="", help='직접 정한 소재로 작성 (예: "식후 10분 걷기")')
    ap.add_argument("--category", default="", help="--topic 카테고리: diet/workout/world/home/health (비우면 자동)")
    ap.add_argument("--pick", action="store_true", help="트렌드 수집 후 번호로 소재 선택")
    ap.add_argument("--out", default=os.path.join(ROOT, "output"))
    a = ap.parse_args()

    cfg = load_cfg()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = os.path.join(a.out, stamp)
    os.makedirs(out_dir, exist_ok=True)
    cats = [c for c in list(cfg["categories"]) + ["health"] if not a.only or c in a.only.split(",")]
    posts = []

    if a.demo:
        demo = json.load(open(os.path.join(ROOT, a.input), encoding="utf-8"))
        for i, p in enumerate([p for p in demo if p["category"] in cats], 1):
            posts.append(produce(writer.validate(p, cfg.get("x_post_max_chars", 400)), out_dir, i, cfg, not a.no_video))
    elif a.topic:
        cat = a.category or guess_category(a.topic, cfg)
        posts.append(write_selected(cat, a.topic, [], cfg, out_dir, 1, not a.no_video))
    else:
        if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")) and not a.collect_only:
            print("⚠️  AI 키가 없어 오프라인 초안으로 작성합니다 (.env 에 ANTHROPIC_API_KEY 또는 OPENAI_API_KEY)")
        cfg["categories"] = {k: v for k, v in cfg["categories"].items() if k in cats}
        signals = collectors.collect_all(cfg)
        json.dump({k: [s.to_dict() for s in v] for k, v in signals.items()},
                  open(os.path.join(out_dir, "signals.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        if a.collect_only:
            print(f"✅ 신호 저장: {out_dir}/signals.json")
            return
        if a.pick:
            menu = []
            for cat, sigs in signals.items():
                for sg in collectors.rank(sigs, 8):
                    menu.append((cat, sg))
            if not menu:
                sys.exit("수집된 소재가 없습니다. 인터넷 연결을 확인하거나 --topic 으로 직접 입력하세요.")
            print("\n──── 오늘의 소재 ────")
            for n, (cat, sg) in enumerate(menu, 1):
                print(f"{n:>2}. [{label_of(cat, cfg)}] {sg.title[:70]}  ({sg.source})")
            raw = input("\n쇼츠로 만들 번호 (예: 1,5,9): ")
            picks = [int(x) for x in re.findall(r"\d+", raw) if 0 < int(x) <= len(menu)]
            for i, n in enumerate(picks, 1):
                cat, sg = menu[n - 1]
                topic = f"{sg.title}\n{sg.summary}".strip()
                posts.append(write_selected(cat, topic, [sg], cfg, out_dir, i, not a.no_video))
            export.export(posts, out_dir)
            print(f"\n✅ 완료: {len(posts)}개 → {out_dir}/index.html")
            return
        target = cfg.get("posts_per_run", 4)
        order = (cats * target)[:target]
        for i, cat in enumerate(order, 1):
            top = collectors.rank(signals.get(cat, []))
            if not top:
                print(f"  [{cat}] 신호 없음 → 건너뜀")
                continue
            label = label_of(cat, cfg)
            for attempt in range(3):
                print(f"✍️  [{label}] 작성 중… (시도 {attempt+1})")
                post = writer.write_post(cat, label, top, dedup.used_titles(), cfg)
                dup, why = dedup.is_duplicate(post["title"], post["x_post"],
                                              cfg["dedup"]["similarity_threshold"])
                if not dup and cfg["dedup"].get("check_x_api"):
                    dup, why = dedup.x_already_viral(post.get("keywords", []))
                print(f"   └ {why or '신규 소재'}")
                if not dup:
                    break
                top = top[3:] or top  # 다른 신호로 재시도
            else:
                continue
            post = produce(post, out_dir, i, cfg, not a.no_video)
            dedup.save(cat, post["title"], post["x_post"], post.get("keywords", []))
            posts.append(post)

    export.export(posts, out_dir)
    print(f"\n✅ 완료: {len(posts)}개 → {out_dir}/index.html")


if __name__ == "__main__":
    main()
