"""논문 제목 한글 번역 — Claude(claude-haiku-5-5)에게 BATCH편씩 묻고 pmid별로 쌓는다.

- 한 번 번역한 제목은 다시 묻지 않는다(research.json의 `번역`에 pmid → 한글 제목). 매일은 새 논문만 조금씩.
- ANTHROPIC_API_KEY가 없으면 아무것도 안 하고 지난 번역만 붙인다. 키·권한 오류는 첫 호출에서 멈춘다.
- 비용: 2026-11 기준 Haiku 5.5 입력 $0.10 / 출력 $0.50 (100만 토큰당). 처음 1만 편 채우기가 수십 센트.
"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50
BATCH = 40
MAX_CALLS = int(os.environ.get("TRANSLATE_MAX_CALLS", "400") or 400)
WORKERS = 8             # 한 번에 하나씩 물으면 1만 편에 1시간 반이 걸려 워크플로 시간 한도에 걸렸다(2026-11-13)
TIME_BUDGET = float(os.environ.get("TRANSLATE_MINUTES", "20") or 20) * 60   # 이 시간이 지나면 새로 묻지 않는다 — 남은 건 다음 실행

SYSTEM = """당신은 보건·의학·커뮤니케이션 분야 학술 번역가입니다. 영어 논문 제목을 한국어로 옮깁니다.
- 국내 학계에서 쓰는 용어로 옮기세요(health communication → 헬스커뮤니케이션, health literacy → 건강 문해력,
  misinformation → 허위정보, shared decision-making → 공동 의사결정, mHealth → 모바일 헬스, scoping review → 주제범위 문헌고찰,
  dyadic → 양자(dyad) 간, emerging adults → 성인 진입기 청년, cross-sectional → 횡단, stigma → 낙인).
- 제목처럼 간결하게, 명사형으로 끝내세요. 부제(콜론 뒤)도 함께 옮기고 콜론은 그대로 둡니다.
- 약어·고유명사(ChatGPT, COVID-19, TikTok, JMIR 등)와 숫자는 그대로 둡니다.
- 받은 논문은 빠짐없이 모두 답합니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "결과": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"pmid": {"type": "string"}, "번역": {"type": "string"}},
                "required": ["pmid", "번역"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["결과"],
    "additionalProperties": False,
}


class Translator:
    def __init__(self):
        self.client = None
        self.fatal = None
        self.calls = self.tin = self.tout = self.errors = 0
        self.lock = threading.Lock()
        self.start = time.monotonic()
        if os.environ.get("ANTHROPIC_API_KEY", "").strip():
            import anthropic
            self.a = anthropic
            self.client = anthropic.Anthropic(max_retries=4)

    def ready(self):
        return (self.client is not None and not self.fatal and self.calls < MAX_CALLS
                and time.monotonic() - self.start < TIME_BUDGET)

    def ask(self, chunk):
        with self.lock:
            if not self.ready():
                return None
            self.calls += 1
        a = self.a
        text = "\n".join(f"[{p['pmid']}] {p['제목']}" for p in chunk)
        try:
            resp = self.client.messages.create(
                model=MODEL,
                max_tokens=8000,
                system=SYSTEM,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": text}],
            )
        except a.APIError as e:
            with self.lock:
                self.errors += 1
            if isinstance(e, (a.AuthenticationError, a.PermissionDeniedError)):
                self.fatal = f"{type(e).__name__}: {str(e)[:200]}"
                print(f"  [중단] {self.fatal} — ANTHROPIC_API_KEY를 확인하세요")
            else:
                print(f"  API 오류: {type(e).__name__}: {str(e)[:200]}")
            return None
        with self.lock:
            self.tin += resp.usage.input_tokens
            self.tout += resp.usage.output_tokens
        if resp.stop_reason in ("refusal", "max_tokens"):
            with self.lock:
                self.errors += 1
            return None
        body = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(body)
        except ValueError:
            with self.lock:
                self.errors += 1
            return None

    def cost(self):
        return round((self.tin * PRICE_IN + self.tout * PRICE_OUT) / 1_000_000, 4)


def translate_titles(papers, cache, status):
    """papers(list)에 p['제목한']을 붙이고 캐시(pmid → 한글 제목)를 돌려준다. 새 논문부터 번역한다."""
    todo = [p for p in papers if p["pmid"] not in cache and p.get("제목")]
    todo.sort(key=lambda p: (p.get("공개일", ""), p["pmid"]), reverse=True)
    t = Translator()
    done = 0
    chunks = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    def work(chunk):
        return chunk, (t.ask(chunk) if t.ready() else None)

    if t.client and chunks:
        with ThreadPoolExecutor(WORKERS) as ex:
            for chunk, ans in ex.map(work, chunks):
                if not ans:
                    continue
                want = {p["pmid"] for p in chunk}
                for r in ans.get("결과", []):
                    pmid = re.sub(r"\D", "", r.get("pmid", ""))
                    ko = (r.get("번역") or "").strip()
                    if pmid in want and ko and re.search("[가-힣]", ko):
                        cache[pmid] = ko[:300]
                        done += 1
                if done and done % 800 < BATCH:
                    print(f"  번역 {done}편", flush=True)
    alive = {p["pmid"] for p in papers}
    cache = {k: v for k, v in cache.items() if k in alive}
    for p in papers:
        if p["pmid"] in cache:
            p["제목한"] = cache[p["pmid"]]
        else:
            p.pop("제목한", None)
    left = sum(1 for p in papers if p["pmid"] not in cache)
    status["번역"] = (f"새로 번역 {done} · 남은 것 {left}"
                    + ("" if t.client else " · ANTHROPIC_API_KEY 없음(번역 안 함)")
                    + (f" · 오류 {t.errors}" if t.errors else "")
                    + (f" · 중단: {t.fatal}" if t.fatal else ""))
    if t.calls:
        status["번역비용"] = {"호출": t.calls, "입력토큰": t.tin, "출력토큰": t.tout, "달러": t.cost()}
    return cache
