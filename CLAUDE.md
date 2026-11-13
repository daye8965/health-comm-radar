# health-comm-radar

헬스커뮤니케이션 분야 상위 20개 저널의 새 논문을 PubMed에서 매일 모아 보여 주는 대시보드입니다(2026-11-13 시작).
서울아산병원 홍보팀 `amc-research-radar`(연구성과 레이더)와 같은 짜임새·화면 양식입니다.

- 공개 주소: https://daye8965.github.io/health-comm-radar/ (공개 저장소 — `docs/`는 그대로 공개됩니다)
- 의존: `requests`, `anthropic`(제목 번역). 화면은 빌드 없는 단일 `docs/index.html` + `xlsx-js-style`(엑셀)

## 구조

| 파일 | 역할 |
|---|---|
| `journals.csv` | 수집 저널 20곳(순위·약어·저널·issn·분류). **사람이 고치는 파일** |
| `hc_radar.py` | PubMed 수집 · [국내] 판정 · OpenAlex 저널 지표 → `docs/research.json` |
| `translate.py` | 논문 제목 한글 번역(Claude `claude-haiku-5-5`) — `research.json`의 `번역`(pmid → 한글)에 쌓음 |
| `docs/index.html` | 화면 (논문 목록 / 분석 탭) |
| `docs/research.json` | 수집 결과. 사람이 편집하지 말 것. 약 9MB(gzip 2.4MB) |
| `.github/workflows/collect.yml` | 매일 2번(본·예비) 수집·커밋. 수동 실행 때 `days`로 다시 훑을 기간 |

## 저널 고르는 기준

PubMed에 실리는 저널 중 **헬스커뮤니케이션이 주제의 중심**인 것(건강·위험·과학 커뮤니케이션, 환자-의료진 소통,
건강증진·건강교육, 디지털 헬스·인포데믹)을 후보로 모으고, **PubMed에 2025년 30편 이상**인 것만 남긴 뒤
**OpenAlex `2yr_mean_citedness`**(IF와 같은 정의의 무료 대용치, 값은 IF보다 작음) 순으로 20곳.

- **JCR IF가 아닙니다.** Clarivate IF는 무료 API가 없습니다. S2Journal에서 Communication 분야 화면을 PDF로
  받아 오면 연구성과 레이더의 `jcr_import.py` 방식으로 바꿀 수 있습니다.
- **Journal of Communication·Science Communication·JCMC 같은 커뮤니케이션 학술지는 빠집니다** — PubMed에
  한 해 0~5편밖에 안 실립니다(2025년 기준). 요청이 'PubMed에서'였기 때문입니다.
- 일반 의학·공중보건 저널(Social Science & Medicine, BMJ Global Health, Vaccine, JAMIA)은 피인용이 높아도
  헬스커뮤니케이션 전문지가 아니라서 넣지 않았습니다. 건강심리(Health Psychology Review, Ann Behav Med),
  질적연구(Qual Health Res), 담배규제(Tob Control)도 같은 이유로 뺐습니다. 넣으려면 `journals.csv`에 한 줄.
- 고른 날(2026-11-13) 지표: JMIR 12.4 … Am J Health Promot 2.5. 핵심지 Health Communication(3.3)·
  J Health Commun(3.3)은 피인용으로는 13·14위입니다.
- 검색은 PubMed 저널 약어 `[ta]`로 합니다. 약어가 비슷한 다른 저널이 딸려 오면 `parse_article`이
  `MedlineTA`로 다시 걸러 냅니다.

## 수집 (`hc_radar.py`)

- PubMed 등록일(edat) 기준 최근 `HC_DAYS`(기본 10)일을 매번 다시 훑고, **논문은 지우지 않고 쌓습니다.**
  `HC_FROM`(기본 2025-01-01)보다 공개일이 이른 논문만 뺍니다. 처음 채우기는 `HC_DAYS=700`.
- **PubMed 검색은 1만 건까지만 돌려줍니다** — 2년치가 10,779건이라 그대로 물으면 9,999건에서 잘렸습니다.
  그래서 60일씩 잘라 묻습니다(`search_pmids`).
- **esearch는 XML로 받습니다** — JSON은 검색식 번역 칸에 제어 문자가 섞여 `JSONDecodeError`가 났습니다.
- **efetch 응답이 가끔 중간에 끊깁니다**(`ParseError`). 4번까지 다시 받습니다.
- 공개일 = 출판일과 PubMed 등록일 중 빠른 날. 등록이 출판보다 90일 넘게 늦으면 `늦은등록`(새 논문 표시 안 함).

## 제목 번역 (`translate.py`, 2026-11-13)

- 화면은 **한글 제목을 크게, 원제를 아래 회색으로** 보여 줍니다. 키워드 해시태그는 사용자 요청으로 화면에서 뺐습니다
  (데이터와 엑셀에는 남아 있습니다).
- `claude-haiku-5-5`에 40편씩(`BATCH`) 구조화 출력(JSON 스키마)으로, **8개를 동시에**(`WORKERS`) 묻습니다. 하나씩 물으면 1만 편에 1시간 반이 걸려 워크플로 시간 한도(40분)에 걸렸습니다(2026-11-13). 한 실행에서 `TRANSLATE_MINUTES`(기본 20분)가 지나면 새로 묻지 않고, 그때까지 번역한 것은 저장합니다. **한 번 번역한 pmid는 다시 묻지 않습니다**
  (`번역` 캐시). 새 논문부터 번역하고, 한 실행에 최대 `TRANSLATE_MAX_CALLS`(기본 400)번 — 처음 1만 편이 한 번에 끝납니다.
- 시스템 프롬프트에 국내 학계 용어(헬스커뮤니케이션·건강 문해력·허위정보·공동 의사결정·주제범위 문헌고찰)를 적어 뒀습니다.
  용어를 바꾸려면 `SYSTEM`을 고치고 `번역` 캐시를 비우세요(전부 비우면 다시 1만 편을 번역합니다 — 수십 센트).
- 저장소 Secret `ANTHROPIC_API_KEY`가 없으면 번역 없이 수집만 하고 화면은 영문 제목을 그대로 씁니다.
  키·권한 오류는 첫 호출에서 멈추고 `상태.번역`에 `중단:`이 남습니다.

## [국내] 딱지

- 소속에 `Korea`(북한 제외) 또는 서울·부산·대구·대전·인천·광주가 적힌 저자가 있으면 국내 논문입니다.
  **대학만이 아니라 병원·연구소·기업도 들어갑니다**(HAII·AITRICS·NAVER 등 디지털 헬스 기업 저자가 꽤 있음).
- 역할: **제1**(첫 저자) · **교신** · **참여**(그 밖). 논문의 `국내역할`은 국내 저자들 역할의 합입니다.
- **교신은 추정입니다.** PubMed는 교신저자를 따로 표시하지 않고, 소속 칸에 이메일을 적은 저자가 대개 교신인데
  **이 저널들은 7%만 이메일을 남깁니다.** 그래서 이메일이 아무에게도 없으면 **마지막 저자를 교신으로 봅니다**
  (`교신추정: true`, 화면 `교신*`). 공동 교신·마지막이 아닌 교신은 못 잡습니다.
- 소속 기관(`org_of`)은 쉼표로 나눈 조각 중 **대학 → 단과대 → 병원·연구소** 순으로 고릅니다. 도시·국가·
  우편번호 조각은 버리고, `HAII Co, Ltd`처럼 쉼표로 떨어진 회사 꼬리는 다시 붙입니다.
  분석 탭은 `Yonsei University College of Medicine` → `Yonsei University`처럼 단과대를 대학으로 묶습니다(`orgKey`).
- 2026-11-13 처음 채운 결과: 10,515편 중 국내 441편(4.2%), 국내 제1·교신 416편.

## 화면 (`docs/index.html`)

- 카드(보기): 국내 제1·교신(기본) · 국내 참여 포함 · 최근 7일 새 논문 · 전체. 연도 버튼, 저널·유형 선택, 검색,
  `국내 논문만` 체크. 열 정렬(공개일·저널·논문=국내 순). 한 페이지 50편.
- 분석 탭: 저널별(논문·국내·국내 제1·교신) · 국내 기관별 · 국내 연구자별. 숫자·막대를 누르면 논문 목록 창.
- 엑셀: 지금 목록 그대로 한 장.
- `[hidden]{display:none!important}`를 맨 위에 뒀습니다 — 언론 대시보드에서 `hidden`이 클래스의 `display`에
  밀려 안 숨겨진 일이 있었습니다.

## 작업 규칙

- 커밋 메시지는 한글 서술형 한 줄. push 전에 `git pull --rebase`(워크플로의 `자동 수집` 커밋과 섞임).
- 확인: `python -m http.server 8791` 후 `http://localhost:8791/docs/`
- 윈도에서 돌릴 때 `requests`가 SSL 오류를 내면 `REQUESTS_CA_BUNDLE`에 윈도 인증서 묶음을 주세요.
