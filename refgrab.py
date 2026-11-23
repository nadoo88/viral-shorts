"""레퍼런스 영상 수집 — 로컬 cobalt(https://github.com/imputnet/cobalt) API 사용

트렌드 신호 중 영상 링크(YouTube Shorts · Reddit · TikTok · 인스타 · X · 쓰레드 등)를
output/날짜/refs/ 에 내려받아 '왜 터졌는지' 연출·자막·컷 템포를 분석하는 용도입니다.

⚠️ 받은 영상은 분석 전용입니다. 렌더·썸네일·사이트에는 절대 쓰지 않으며
   (site_builder 는 refs/ 폴더를 복사하지 않음) 재업로드하지 않습니다.

cobalt 가 꺼져 있거나(GitHub Actions 등) 링크가 지원되지 않으면 조용히 건너뜁니다.
API 주소: 환경변수 COBALT_API_URL > config.yaml reference_grab.api > http://localhost:9000/
"""
from __future__ import annotations

import json
import os
import re

import requests

HEAD = {"Accept": "application/json", "Content-Type": "application/json"}
VIDEO_HOSTS = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "reddit.com",
               "x.com", "twitter.com", "threads.net", "threads.com", "facebook.com",
               "vimeo.com", "bilibili.com", "pinterest.", "streamable.com", "twitch.tv")


def _api(cfg: dict) -> str:
    url = os.getenv("COBALT_API_URL") or (cfg.get("reference_grab") or {}).get("api") or "http://localhost:9000/"
    return url if url.endswith("/") else url + "/"


def available(cfg: dict) -> bool:
    """cobalt 서버가 떠 있는지 (GET / 는 레이트리밋 없음)."""
    try:
        return "cobalt" in requests.get(_api(cfg), timeout=3).json()
    except Exception:  # noqa: BLE001
        return False


def is_video_link(url: str) -> bool:
    return bool(url) and any(h in url for h in VIDEO_HOSTS)


def _safe(name: str, limit=60) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', " ", name).strip()
    return re.sub(r"\s+", "_", name)[:limit] or "ref"


def _save(link: str, path: str) -> str | None:
    try:
        with requests.get(link, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        if os.path.getsize(path) == 0:
            os.remove(path)
            return None
        return path
    except Exception as e:  # noqa: BLE001
        print(f"    [레퍼런스 저장 실패] {e}")
        return None


def grab(url: str, out_dir: str, cfg: dict, prefix: str = "ref") -> list[str]:
    """링크 하나를 cobalt 로 받아 저장된 파일 경로 목록을 돌려줌 (실패 시 빈 리스트)."""
    rc = cfg.get("reference_grab") or {}
    os.makedirs(out_dir, exist_ok=True)
    body = {
        "url": url,
        "downloadMode": rc.get("mode", "auto"),          # auto / audio / mute
        "videoQuality": str(rc.get("quality", "720")),   # 분석용이라 720 기본
        "youtubeVideoCodec": "h264",                     # 어디서든 재생되게
        "filenameStyle": "basic",
    }
    try:
        r = requests.post(_api(cfg), headers=HEAD, json=body, timeout=60).json()
    except Exception as e:  # noqa: BLE001
        print(f"    [cobalt 요청 실패] {e}")
        return []

    status = r.get("status")
    if status in ("tunnel", "redirect"):
        ext = os.path.splitext(r.get("filename", ""))[1] or ".mp4"
        p = _save(r["url"], os.path.join(out_dir, f"{prefix}{ext}"))
        return [p] if p else []
    if status == "picker":                               # 슬라이드·여러 장
        saved = []
        for i, it in enumerate(r.get("picker", [])[: int(rc.get("max_picker", 10))], 1):
            ext = ".mp4" if it.get("type") in ("video", "gif") else ".jpg"
            p = _save(it["url"], os.path.join(out_dir, f"{prefix}_{i:02d}{ext}"))
            if p:
                saved.append(p)
        if r.get("audio"):
            p = _save(r["audio"], os.path.join(out_dir, f"{prefix}_audio.mp3"))
            if p:
                saved.append(p)
        return saved
    err = (r.get("error") or {}).get("code", status)
    print(f"    [cobalt] 건너뜀: {err}")
    return []


def grab_for_post(post: dict, signals: list, out_dir: str, cfg: dict, idx: int) -> list[dict]:
    """글 작성에 쓰인 상위 신호 중 영상 링크를 per_post 개까지 받아 post['ref_media'] 에 기록."""
    rc = cfg.get("reference_grab") or {}
    want = int(rc.get("per_post", 2))
    refs_dir = os.path.join(out_dir, "refs")
    got = []
    for s in signals:
        if len(got) >= want:
            break
        url = getattr(s, "url", "") if not isinstance(s, dict) else s.get("url", "")
        title = getattr(s, "title", "") if not isinstance(s, dict) else s.get("title", "")
        if not is_video_link(url):
            continue
        prefix = f"{idx:02d}_{post.get('category', 'ref')}_{len(got)+1}_{_safe(title, 40)}"
        print(f"  📥 레퍼런스: {title[:50]} ({url[:60]})")
        files = grab(url, refs_dir, cfg, prefix)
        if files:
            got.append({"url": url, "title": title,
                        "files": [os.path.relpath(f, out_dir).replace("\\", "/") for f in files]})
    if got:
        post["ref_media"] = got
    return got


def grab_urls(urls: list[str], out_dir: str, cfg: dict) -> list[dict]:
    """--grab 단독 실행: 링크 목록을 refs/ 에 받고 refs/index.json 기록."""
    refs_dir = os.path.join(out_dir, "refs")
    out = []
    for i, u in enumerate(urls, 1):
        print(f"📥 [{i}/{len(urls)}] {u}")
        files = grab(u, refs_dir, cfg, f"{i:02d}_{_safe(u.split('?')[0].rstrip('/').split('/')[-1], 40)}")
        out.append({"url": u, "files": [os.path.relpath(f, out_dir).replace("\\", "/") for f in files]})
        print(f"   └ {len(files)}개 저장" if files else "   └ 실패")
    os.makedirs(refs_dir, exist_ok=True)
    with open(os.path.join(refs_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out
