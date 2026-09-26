"""미디어 수집 — 무료 상업 이용 가능 스톡만 사용
- Pexels (PEXELS_API_KEY): 세로 영상 클립 우선, 없으면 세로 사진
- Pixabay (PIXABAY_API_KEY): Pexels 실패 시 대체
키가 없으면 빈 결과 → 렌더러가 그라데이션 카드 배경으로 대체합니다.
모든 파일의 작가/출처를 credits에 기록해 캡션·설명란에 표기할 수 있게 합니다.
"""
from __future__ import annotations

import os
import requests

TIMEOUT = 20


def _download(url: str, path: str) -> str | None:
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        return path
    except Exception as e:  # noqa: BLE001
        print(f"    [다운로드 실패] {e}")
        return None


def pexels_video(query: str, out_dir: str, idx: int):
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://api.pexels.com/videos/search", timeout=TIMEOUT,
                         headers={"Authorization": key},
                         params={"query": query, "orientation": "portrait", "per_page": 5, "size": "medium"})
        vids = r.json().get("videos", [])
    except Exception:  # noqa: BLE001
        return None
    for v in vids:
        files = sorted([f for f in v["video_files"] if f.get("height", 0) >= 1280 and f["file_type"] == "video/mp4"],
                       key=lambda f: f["height"])
        if files:
            p = _download(files[0]["link"], os.path.join(out_dir, f"scene{idx:02d}.mp4"))
            if p:
                return {"path": p, "type": "video", "credit": f"{v['user']['name']} / Pexels", "url": v["url"]}
    return None


def pexels_photo(query: str, out_dir: str, idx: int):
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://api.pexels.com/v1/search", timeout=TIMEOUT,
                         headers={"Authorization": key},
                         params={"query": query, "orientation": "portrait", "per_page": 3})
        photos = r.json().get("photos", [])
    except Exception:  # noqa: BLE001
        return None
    if not photos:
        return None
    ph = photos[0]
    p = _download(ph["src"]["large2x"], os.path.join(out_dir, f"scene{idx:02d}.jpg"))
    return p and {"path": p, "type": "image", "credit": f"{ph['photographer']} / Pexels", "url": ph["url"]}


def pixabay_photo(query: str, out_dir: str, idx: int):
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return None
    try:
        hits = requests.get("https://pixabay.com/api/", timeout=TIMEOUT, params={
            "key": key, "q": query, "orientation": "vertical", "image_type": "photo",
            "safesearch": "true", "per_page": 3}).json().get("hits", [])
    except Exception:  # noqa: BLE001
        return None
    if not hits:
        return None
    h = hits[0]
    p = _download(h["largeImageURL"], os.path.join(out_dir, f"scene{idx:02d}.jpg"))
    return p and {"path": p, "type": "image", "credit": f"{h['user']} / Pixabay", "url": h["pageURL"]}


def fetch_scene_media(post: dict, out_dir: str, prefer_video=True) -> list:
    os.makedirs(out_dir, exist_ok=True)
    media = []
    for i, sc in enumerate(post.get("scenes", [])):
        q = sc.get("visual") or (post.get("media_queries") or ["lifestyle"])[0]
        m = None
        if prefer_video:
            m = pexels_video(q, out_dir, i)
        m = m or pexels_photo(q, out_dir, i) or pixabay_photo(q, out_dir, i)
        media.append(m)
        print(f"    장면{i+1} '{q}' → {m['type'] + ' · ' + m['credit'] if m else '카드 배경'}")
    return media
