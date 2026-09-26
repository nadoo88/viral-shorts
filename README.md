# 바이럴 쇼츠 자동화 (viral-shorts-bot)

다이어트 · 살빼는운동 · 해외이슈 · 살림꿀템 4개 카테고리에서
**해외·타 플랫폼에서 먼저 터진 소재 → X 인기글 말투의 글 + 9:16 쇼츠 영상 + 1:1 썸네일**을 매일 자동 생성합니다.

```
[수집]  Google News(미국·일본·한국) · Google Trends · Reddit 주간 TOP · YouTube Shorts 조회수순 · 쓰레드/인스타 레퍼런스
   ↓   플랫폼별 인기지표 정규화 → 카테고리별 상위 12개 신호
[작성]  Claude — 후킹 첫줄 / 130자 단문 / 4개 스레드 / 장면별 자막 / 출처
   ↓   과거 글 유사도 검사(SQLite) + X API 검색(선택)으로 이미 퍼진 소재면 재작성
[미디어] Pexels 세로 영상 → Pexels 사진 → Pixabay → 그라데이션 카드 (전부 무료 상업이용 라이선스, 작가 크레딧 자동 기록)
   ↓
[렌더]  1080×1920 · 예능 자막(핵심어 노란색 팝인) · 켄번스 · 진행바 · 합성 BGM
   ↓
[출력]  output/날짜/ index.html(복사·X에 올리기 버튼) · posts.md · posts.json · mp4 · jpg
```

## 설치 (Windows / Mac 공통)

```bash
pip install -r requirements.txt
# FFmpeg 필요: Windows → winget install ffmpeg / Mac → brew install ffmpeg
copy .env.example .env      # Mac: cp .env.example .env  → 키 입력
```

## 실행

```bash
python main.py --demo           # 키 없이 바로 테스트 (데모 글 4개로 영상 렌더)
python main.py                  # 실전: 수집→작성→영상 (카테고리별 1개씩, 총 4개)
python main.py --only diet,home # 특정 카테고리만
python main.py --no-video       # 글 + 썸네일만 (빠름)
python main.py --collect-only   # 오늘의 트렌드 신호만 signals.json 으로
```

끝나면 `output/날짜_시간/index.html` 을 열어 **복사 → X에 올리기**. 영상은 X·릴스·쇼츠·틱톡에 그대로 업로드.

## 매일 자동 실행 (GitHub Actions)

1. 이 폴더를 GitHub 저장소로 푸시
2. Settings → Secrets → Actions 에 `.env` 항목들 등록
3. 매일 오전 7:50(KST) 실행 → Actions 탭 Artifacts 에서 결과 zip 다운로드
   (`history.db` 가 커밋되어 날마다 중복 소재를 피함)

## 쓰레드·인스타 소재 넣기
두 플랫폼은 공개 트렌드 API가 없어 자동 수집이 불가능합니다. 스크롤하다 반응 큰 게시물을 보면
`references.txt` 에 `카테고리|링크 또는 메모` 로 한 줄 적어두면 다음 실행 때 가장 높은 가중치로 반영됩니다.

## 말투·규칙 바꾸기
`writer.py` 의 `SYSTEM` 프롬프트 한 곳만 고치면 됩니다. (후킹 패턴, 글자수, 금지어, 사실성 규칙)

## 지켜지는 안전장치
- 근거 없는 수치·연구 지어내기 금지, 해외이슈는 실제 기사 링크 필수 → `sources` 에 자동 기록
- 극단적 절식·kcal 제한·약물 권유·비현실 감량 약속 금지 + 금지어 자동 제거
- 남의 영상/사진 재업로드 없음 — 소재만 재구성, 비주얼은 무료 라이선스 스톡 또는 직접 촬영 가이드
