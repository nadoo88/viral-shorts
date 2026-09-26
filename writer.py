"""바이럴 글 작성기 (Claude API)

수집된 트렌드 신호 → 쇼츠 전문가 스타일의
  · 쇼츠 제목 / X 본문(단문+스레드) / 장면별 쇼츠 대본 / 미디어 검색어 / 출처
를 JSON으로 생성합니다.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

SYSTEM = """너는 X(트위터)·유튜브 쇼츠·릴스에서 조회수 수백만을 여러 번 만든 한국 숏폼 전문 에디터다.

[말투 — X 100만+ 인기글 문법 (실제 인기글 분석 반영)]
- 첫 줄은 >>꺾쇠 강조<< 로 타깃을 콕 집는다. "~하는 사람 필독", "여태 ~했으면", "이거 ~밖에 없음"
  예: ">>소화제 먹고 넘기는 사람 필독<<" / ">>이거 만들 수 있는 회사가 전 세계에 딱 하나<<"
- 다른 후킹 패턴: "이거 장난인 줄 알았는데 실제였음"(반전), "○○ 말고 이거 봐"(통념 뒤집기),
  "식단 안 해도 이것만"(제로 노력), 숫자 희소성("91대밖에 없음")
- 전언체 섞기: "~라고 함", "~래", "~임", "~됨". 반말, 짧게, 한 줄에 한 호흡, 줄바꿈 많이.
- 리액션 양념은 한 글에 한두 번만: ㅋㅋ, ;;, ㄹㅇ (남발 금지)
- 누구나 하는 습관을 저격하는 공감 장면 넣기 ("등 아프면 파스 붙이고 끝남")
- 마지막은 참여 유도: "부모님한테도 보내드려", "타본 사람?", "지금 앉아 있으면 바로 해봐", "저장"
- 권위를 지어내지 말 것: "PT쌤이 알려준", "치과에 걸려있는" 같은 확인 안 된 출처·가짜 체험담 금지.
  권위는 실제 통계·기관·연구로만.
- 실존 연예인·유명인 이름을 붙인 식단/효과 주장, 외모 평가·몸매 품평 글은 쓰지 않는다.
- 숫자·비교·반전을 넣는다 (예: "10분 걷기 vs 30분 뛰기").
- 핵심 정보는 번호 목록(1. 2. 3.)으로 스캔되게.
- 마지막 줄은 저장/리포스트/인용을 부르는 한 줄 (예: "나중에 찾지 말고 저장해둬").
- 이모지는 0~2개, 해시태그는 본문 끝에 최대 2개. 과한 느낌표·"충격"·"경악" 금지(싸구려 느낌).
- x_post는 공백 포함 {max_chars}자 이내. 번호 리스트 포함 장문 가능.

[사실성 — 절대 규칙]
- 제공된 신호(뉴스/레딧/유튜브/레퍼런스)에 근거한 사실만 쓴다. 근거가 없는 수치·연구·인물 발언을 지어내지 않는다.
- 해외이슈는 반드시 실제 기사 링크를 sources에 넣는다. 확인 안 된 루머는 쓰지 않는다.
- 다이어트/운동: 극단적 절식, 하루 ○kcal 이하, 단식 강요, 약물·보조제 권유, "한 달 -10kg" 같은 비현실 약속 금지.
  건강 정보는 일반적이고 안전한 범위로. 필요하면 짧은 주의 한 줄.
- 다른 크리에이터의 영상·사진을 그대로 쓰라고 지시하지 않는다. 소재·인사이트만 재구성하고,
  시각 자료는 무료 라이선스 스톡(Pexels/Pixabay) 검색어 또는 직접 촬영/생성 가이드로 제시한다.
- 이미 사용한 제목 목록과 겹치는 소재·각도는 피한다.

[출력] 반드시 아래 JSON 하나만 출력. 설명 금지.
{
  "category": "diet|workout|world|home",
  "title": "쇼츠 제목 (25자 이내, 호기심+숫자)",
  "hook": "영상 첫 1.5초 자막 (15자 이내)",
  "x_post": "X 본문 (줄바꿈 포함)",
  "x_thread": ["스레드 1(후킹)", "2", "3", "4(저장 유도)"],
  "scenes": [
    {"text": "화면 자막 (한 줄 14자 이내, 최대 2줄, \\n으로 구분)",
     "highlight": "노란색 강조할 핵심 단어",
     "visual": "영문 스톡 검색어 (예: woman walking stairs)"}
  ],
  "media_queries": ["대표 썸네일용 영문 검색어 2~3개"],
  "shooting_guide": "직접 찍거나 AI로 만들 때 컷 구성 한두 줄",
  "keywords": ["중복검사용 핵심 키워드 3개"],
  "hashtags": ["#태그1", "#태그2"],
  "sources": [{"title": "출처 제목", "url": "링크"}],
  "why_viral": "이 글이 터질 이유 한 줄 (내부용)"
}
scenes는 5~7개. 첫 장면 = hook, 마지막 장면 = 저장/팔로우 유도."""

CATEGORY_ANGLE = {
    "diet": "먹는 순서·타이밍·흔한 착각 뒤집기 등 '오늘 바로 해볼 수 있는' 각도",
    "workout": "짧은 시간·집에서·특정 부위·걷기/계단 등 진입장벽 낮은 각도",
    "world": "한국엔 없는 해외 제도·문화·사건을 '우리나라랑 비교'하는 각도",
    "home": "돈 안 드는 살림 꿀팁·흔한 실수 교정·몰랐던 용도 각도",
    "health": "흔한 습관 속 놓치기 쉬운 신호, 공포 조장 없이 행동 가이드로",
}


def build_user_prompt(category: str, label: str, signals: list, used: list[str],
                      topic: str | None = None) -> str:
    lines = []
    for i, s in enumerate(signals, 1):
        d = s if isinstance(s, dict) else s.to_dict()
        pop = f" (인기지표 {int(d['score']):,})" if d.get("score") else ""
        lines.append(f"{i}. [{d['source']}]{pop} {d['title']}\n   {d.get('summary','')[:200]}\n   {d.get('url','')}")
    used_txt = "\n".join(f"- {t}" for t in used[:60]) or "- (없음)"
    if topic:
        task = (f"[사용자가 직접 선택한 소재]\n{topic}\n\n"
                "반드시 이 소재로 바이럴 쇼츠 패키지 JSON 1개를 만들어줘. 다른 소재로 바꾸지 마.\n"
                "소재에 과장·오류가 있으면 사실에 맞게 바로잡아 쓰고, 확인 안 되는 수치는 빼.")
    else:
        task = ("위 신호 중 한국 X에는 아직 안 퍼졌을 법하고, 사실 근거가 확실한 소재 1개를 골라\n"
                "바이럴 쇼츠 패키지 JSON 1개를 만들어줘.")
    return f"""카테고리: {label} ({category})
추천 각도: {CATEGORY_ANGLE.get(category, '')}

[참고 신호]
{chr(10).join(lines) or '(없음)'}

[이미 사용한 제목 — 겹치지 말 것]
{used_txt}

{task}"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON 응답 없음")
    return json.loads(m.group(0))


# ── AI 호출 (429 재시도 + 제공자 자동 전환) ─────────────────
class QuotaError(Exception):
    """크레딧/한도 소진 — 재시도해도 안 됨."""


def _post_json(url, headers, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _with_retry(name, fn, tries=4):
    """429·5xx면 Retry-After 또는 5→10→20초 대기 후 재시도. 크레딧 소진이면 바로 포기."""
    for i in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001
                pass
            if e.code == 429 and ("insufficient_quota" in body or "credit" in body.lower()
                                  or "billing" in body.lower()):
                raise QuotaError(f"{name} 크레딧/결제 한도 소진 (충전 필요)") from e
            if e.code in (429, 500, 502, 503, 529) and i < tries - 1:
                wait = e.headers.get("retry-after") if e.headers else None
                wait = float(wait) if wait and wait.replace(".", "").isdigit() else 5 * 2 ** i
                wait = min(wait, 60)
                print(f"   ⏳ {name} {e.code} (요청 과다) → {wait:.0f}초 후 재시도 {i+1}/{tries-1}")
                time.sleep(wait)
                continue
            raise RuntimeError(f"{name} HTTP {e.code}: {body[:200]}") from e


def _call_anthropic(system, user, cfg):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    w = cfg["writer"]
    res = _with_retry("Claude", lambda: _post_json(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        {"model": w.get("model", "claude-opus-5-5"), "max_tokens": w.get("max_tokens", 4000),
         "system": system, "messages": [{"role": "user", "content": user}]}))
    return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")


def _call_openai(system, user, cfg):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    w = cfg["writer"]
    res = _with_retry("OpenAI", lambda: _post_json(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {"model": w.get("openai_model", "gpt-4.1-mini"),
         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
         "response_format": {"type": "json_object"}}))
    return res["choices"][0]["message"]["content"]


PROVIDERS = {"anthropic": _call_anthropic, "openai": _call_openai}


def write_post(category: str, label: str, signals: list, used: list[str], cfg: dict,
               topic: str | None = None) -> dict:
    """providers 순서대로 시도. 전부 실패하면 선택한 소재로 오프라인 초안을 만들어 멈추지 않음."""
    max_chars = cfg.get("x_post_max_chars", 400)
    system = SYSTEM.replace("{max_chars}", str(max_chars))
    user = build_user_prompt(category, label, signals, used, topic)
    errors = []
    for name in cfg["writer"].get("providers", ["anthropic", "openai"]):
        fn = PROVIDERS.get(name)
        if not fn:
            continue
        try:
            text = fn(system, user, cfg)
            if text is None:
                continue  # 키 없음
            post = _extract_json(text)
            post["category"] = category
            post["_writer"] = name
            return validate(post, max_chars)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
            print(f"   ⚠️  {name} 생성 실패: {e} → 다음 방법으로 전환")
    print("   📝 AI 사용 불가 → 선택한 소재로 오프라인 초안 생성 (사실 확인 후 게시)")
    post = offline_draft(category, label, topic or (signals[0].title if signals and hasattr(signals[0], "title")
                                                    else (signals[0]["title"] if signals else label)), signals)
    post["_writer"] = "offline"
    post["_errors"] = errors
    return validate(post, max_chars)


# ── 오프라인 초안 (API 없이도 쇼츠 완성) ──────────────────────
HOOKS = {
    "diet": (">>다이어트 중이면 이거 꼭 봐<<", "살 빠지는 사람들은 이미 알고 있었음"),
    "workout": (">>운동할 시간 없는 사람 필독<<", "이것만 해도 몸이 달라짐"),
    "world": (">>우리나라엔 없는 이야기<<", "해외에서 난리 난 소식"),
    "home": (">>살림하는 사람 저장 필수<<", "여태 반대로 하고 있었음"),
    "health": (">>이 신호 그냥 넘기면 안 됨<<", "몸이 먼저 보내는 경고"),
}


VISUAL_EN = {"diet": "healthy meal", "workout": "home workout", "world": "city street abroad",
             "home": "clean kitchen", "health": "doctor consultation"}


def offline_draft(category: str, label: str, topic: str, signals: list) -> dict:
    topic = re.sub(r"\s+", " ", topic).strip()
    label_en = VISUAL_EN.get(category, "lifestyle")
    first, second = HOOKS.get(category, HOOKS["home"])
    short = topic if len(topic) <= 22 else topic[:21] + "…"
    src = []
    for s in signals[:2]:
        d = s if isinstance(s, dict) else s.to_dict()
        if d.get("url"):
            src.append({"title": d["title"][:60], "url": d["url"]})
    x_post = (f"{first}\n{short}\n\n{second}\n\n"
              f"1. 핵심 포인트 한 줄\n2. 이유 한 줄\n3. 오늘 바로 해볼 것 한 줄\n\n"
              f"나중에 찾지 말고 저장해둬")
    return {
        "category": category,
        "title": short,
        "hook": short[:15],
        "x_post": x_post,
        "x_thread": [f"{first}\n{short}", "왜 그런지 이유 정리", "바로 따라 할 수 있는 방법", "저장·공유 유도 한 줄"],
        "scenes": [
            {"text": _wrap(short), "highlight": short.split(" ")[0], "visual": label_en},
            {"text": _wrap(second), "highlight": second.split(" ")[-1], "visual": label_en},
            {"text": "핵심은\n딱 3가지", "highlight": "3가지", "visual": label_en},
            {"text": "오늘 바로\n해봐", "highlight": "바로", "visual": label_en},
            {"text": "까먹기 전에\n저장해둬", "highlight": "저장", "visual": label_en},
        ],
        "media_queries": [label_en],
        "shooting_guide": "오프라인 초안입니다. 번호 목록 3줄을 실제 내용으로 채우고 사실 확인 후 게시하세요.",
        "keywords": topic.split(" ")[:3],
        "hashtags": [f"#{label}"],
        "sources": src,
        "why_viral": "오프라인 초안 — AI 연결되면 자동으로 완성본이 생성됩니다",
    }


def _wrap(text: str, n=12) -> str:
    words, lines, cur = text.split(" "), [], ""
    for w_ in words:
        if len(cur + " " + w_) > n and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    lines.append(cur)
    return "\n".join(lines[:2])


def validate(post: dict, max_chars: int = 400) -> dict:
    """길이·금지어 자동 교정."""
    banned = ["충격", "경악", "무조건 빠지는", "기적의", "-10kg", "단식하세요"]
    for k in ("title", "x_post", "hook"):
        for b in banned:
            post[k] = post.get(k, "").replace(b, "")
    if len(post.get("x_post", "")) > max_chars:
        post["x_post"] = post["x_post"][:max_chars - 1].rstrip() + "…"
    post["title"] = post.get("title", "")[:30]
    post.setdefault("scenes", [])
    post.setdefault("hashtags", [])
    post.setdefault("sources", [])
    post.setdefault("keywords", [])
    return post
