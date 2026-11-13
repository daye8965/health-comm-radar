"""헬스커뮤니케이션 논문 레이더 — 분야 상위 20개 저널에 새로 올라온 논문을 PubMed에서 매일 모은다.

결과는 docs/research.json 하나. docs/index.html(GitHub Pages)이 읽는다.

- 저널: journals.csv (사람이 고치는 파일). PubMed 저널 약어([ta])로 찾는다.
- 수집: PubMed 등록일(edat) 기준 최근 HC_DAYS일을 매번 다시 훑는다(이미 있는 PMID는 덮어씀). 논문은 지우지 않고 쌓는다.
- [국내] 딱지: 소속에 한국(Korea, 북한 제외)이 적힌 저자가 있으면 붙인다. 역할은 제1 · 교신(소속 칸에 이메일) · 참여.
- 저널 지표: OpenAlex 2yr_mean_citedness(최근 2년 논문 평균 피인용 — IF와 같은 정의의 무료 대용치, IF보다 작게 나온다).

환경변수: HC_DAYS(기본 10) · HC_FROM(기본 2025-01-01, 공개일이 이보다 이른 논문은 뺌) · NCBI_API_KEY(선택)
"""
import csv
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from countries import ISO, country_of
from translate import translate_titles

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
OUT = Path("docs/research.json")
JOURNALS = Path("journals.csv")
DAYS = int(os.environ.get("HC_DAYS", "10") or 10)
FROM_DATE = os.environ.get("HC_FROM", "").strip() or "2025-01-01"
LATE_DAYS = 90          # 출판 뒤 이만큼 넘게 지나 PubMed에 올라온 논문은 '늦게 등록'
NCBI_KEY = os.environ.get("NCBI_API_KEY", "").strip()
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
UA = {"User-Agent": "health-comm-radar/1.0"}
NON_RESEARCH = {"Comment", "Editorial", "Letter", "Erratum", "Published Erratum", "News",
                "Retraction Notice", "Retraction of Publication", "Expression of Concern", "Biography",
                "Portrait", "Interview", "Introductory Journal Article", "Corrected and Republished Article"}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(*a):
    print(*a, flush=True)


def load_journals():
    with open(JOURNALS, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("약어")]


# ── PubMed ─────────────────────────────────────────────────────────────────
def eutils(path, **params):
    if NCBI_KEY:
        params["api_key"] = NCBI_KEY
    for attempt in range(5):
        r = requests.get(EUTILS + path, params=params, headers=UA, timeout=90)
        if r.status_code == 429:
            time.sleep(1.5 * (attempt + 1))
            continue
        r.raise_for_status()
        time.sleep(0.12 if NCBI_KEY else 0.4)
        return r
    r.raise_for_status()


def search_pmids(journals, start, end):
    """PubMed 검색은 결과 1만 건까지만 돌려준다 — 기간을 60일씩 잘라 묻는다(처음 채울 때 2년치가 1만 건을 넘는다)."""
    ids, s = [], start
    while s <= end:
        e = min(end, s + timedelta(days=59))
        ids += _search(journals, s, e)
        s = e + timedelta(days=1)
    return list(dict.fromkeys(ids))


def _search(journals, start, end):
    ta = " OR ".join(f'"{j["약어"]}"[ta]' for j in journals)
    term = f"({ta}) AND {start:%Y/%m/%d}:{end:%Y/%m/%d}[edat]"
    ids, retstart = [], 0
    while True:
        # JSON 응답은 검색식 번역 칸에 제어 문자가 섞여 깨질 때가 있어 XML로 받는다
        x = ET.fromstring(eutils("esearch.fcgi", db="pubmed", retmax=5000, retstart=retstart, term=term).content)
        ids += [e.text for e in x.findall("IdList/Id")]
        retstart += 5000
        if retstart >= int(x.findtext("Count") or 0):
            return ids


def text_of(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def is_korea(aff):
    a = aff.lower()
    if "democratic people" in a or "dprk" in a or "pyongyang" in a:
        return False
    return bool(re.search(r"\bkorea\b|republic of korea|\bseoul\b|\bbusan\b|\bdaejeon\b|\bdaegu\b|\bincheon\b|\bgwangju\b", a))


ORG_RE = re.compile(r"[^,;]*(?:University|College|Hospital|Institute|Center|Centre|Agency|Ministry|Foundation|"
                    r"School|Corporation|Service|KAIST|POSTECH)[^,;]*", re.I)


def org_of(aff):
    """소속 문자열에서 기관 이름 하나 — 학과·부서·도시 말고 기관을 고른다. 대학 → 단과대 → 병원·연구소 순."""
    parts = [p.strip().rstrip(".").strip() for p in re.split(r"[,;]", aff) if p.strip().rstrip(".").strip()]
    dept = re.compile(r"^(Department|Dept|Division|Graduate School|School of|College of|Program|Laboratory|Lab)\b", re.I)
    for pat in (r"University|KAIST|POSTECH|UNIST|DGIST|\bGIST\b",r"College|School",
                r"Hospital|Medical Center|Institute|Agency|Ministry|Center|Centre|Foundation|Corporation|Service|Council|Association"):
        for p in parts:
            if re.search(pat, p) and not dept.match(p):
                return p
    city = re.compile(r"^(Republic of Korea|South Korea|Korea|Seoul|Busan|Daegu|Daejeon|Incheon|Gwangju|Ulsan|Suwon|Seongnam|"
                      r"Goyang|Cheongju|Jeonju|Chuncheon|Wonju|\d[\d-]*|[A-Z][a-z]+-(?:si|do|gu|gun))$", re.I)
    rest = [p for p in parts if not city.match(p) and "@" not in p]
    # 'HAII Co, Ltd'처럼 회사 꼬리가 쉼표로 떨어져 나온 경우 앞 조각과 붙인다
    while len(rest) > 1 and re.fullmatch(r"(Ltd|Inc|Co|Corp|LLC|Co\.?\s*Ltd)\.?", rest[-1], re.I):
        rest = rest[:-2] + [rest[-2] + ", " + rest[-1]]
    return rest[-1] if rest else ""


MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def pub_date(art):
    ad = art.find("Article/ArticleDate")
    if ad is not None and ad.findtext("Year"):
        return f"{ad.findtext('Year')}-{int(ad.findtext('Month') or 1):02d}-{int(ad.findtext('Day') or 1):02d}"
    pd = art.find("Article/Journal/JournalIssue/PubDate")
    if pd is None:
        return ""
    y = pd.findtext("Year") or (pd.findtext("MedlineDate") or "")[:4]
    m = pd.findtext("Month") or "1"
    m = MON.get(m[:3], int(m) if m.isdigit() else 1)
    d = pd.findtext("Day") or "1"
    return f"{y}-{m:02d}-{int(d) if d.isdigit() else 1:02d}" if y.isdigit() else ""


def conclusion_of(art):
    parts = art.findall("Article/Abstract/AbstractText")
    if not parts:
        return ""
    for p in parts:
        lab = (p.get("Label") or p.get("NlmCategory") or "").upper()
        if lab.startswith("CONCLUSION") or lab == "INTERPRETATION":
            return text_of(p)[:280]
    sents = re.split(r"(?<=[.!?])\s+", text_of(parts[-1]))
    return " ".join(sents[-2:])[:280]


def parse_article(pa, by_ta):
    mc = pa.find("MedlineCitation")
    pmid = mc.findtext("PMID")
    journal = mc.find("Article/Journal")
    ta = journal.findtext("ISOAbbreviation") or mc.findtext("MedlineJournalInfo/MedlineTA") or ""
    mta = mc.findtext("MedlineJournalInfo/MedlineTA") or ""
    j = by_ta.get(mta.lower()) or by_ta.get(ta.lower())
    if not j:
        return None                               # [ta] 검색이 비슷한 이름의 다른 저널을 끌고 온 경우
    doi = ""
    for aid in pa.findall("PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi":
            doi = (aid.text or "").strip()
    authors = mc.findall("Article/AuthorList/Author")
    n = len(authors)
    names, kor = [], []
    corr = []
    first_c, corr_c = "", []
    # 교신저자 — PubMed는 따로 표시하지 않는다. 소속 칸에 이메일을 적은 저자가 대개 교신인데, 이 분야 저널은
    # 7%만 이메일을 남긴다. 그래서 이메일이 아무에게도 없으면 **마지막 저자를 교신으로 본다**(분야 관행)
    any_mail = any("@" in text_of(a) for au in authors for a in au.findall("AffiliationInfo/Affiliation"))
    for i, au in enumerate(authors):
        name = " ".join(x for x in [au.findtext("ForeName"), au.findtext("LastName")] if x) \
            or au.findtext("CollectiveName") or ""
        affs = [text_of(a) for a in au.findall("AffiliationInfo/Affiliation")]
        is_corr = any("@" in a for a in affs) if any_mail else (i == n - 1 and n > 1)
        names.append(name)
        if is_corr:
            corr.append(name)
        # 나라 — 소속이 여럿이면 처음 찾은 것(대개 주 소속)
        cty = next((c for c in map(country_of, affs) if c), "")
        if i == 0:
            first_c = cty
        if is_corr and cty and cty not in corr_c:
            corr_c.append(cty)
        ko = [a for a in affs if is_korea(a)]
        if ko:
            roles = [r for r, ok in (("제1", i == 0), ("교신", is_corr)) if ok]
            kor.append({"이름": name, "역할": roles or ["참여"], "소속": org_of(ko[0])[:80]})
    types = [text_of(t) for t in mc.findall("Article/PublicationTypeList/PublicationType")]
    edat = ""
    for d in pa.findall("PubmedData/History/PubMedPubDate"):
        if d.get("PubStatus") == "entrez":
            edat = f"{d.findtext('Year')}-{int(d.findtext('Month')):02d}-{int(d.findtext('Day')):02d}"
    kws = [text_of(k) for k in mc.findall("KeywordList/Keyword")][:6]
    # 국내 역할 요약 — 제1·교신이 있으면 그것을 앞세운다(화면 딱지)
    lead = sorted({r for k in kor for r in k["역할"] if r in ("제1", "교신")}, key=["제1", "교신"].index)
    return {
        "pmid": pmid,
        "doi": doi,
        "제목": text_of(mc.find("Article/ArticleTitle")).rstrip("."),
        "약어": j["약어"],
        "출판일": pub_date(mc),
        "등록일": edat,
        "유형": [t for t in types if t != "Journal Article"],
        "연구": not any(t in NON_RESEARCH for t in types),
        "저자수": n,
        "제1저자": names[0] if names else "",
        "교신": corr[:3],
        "교신추정": not any_mail,
        "마지막저자": names[-1] if n > 1 else "",
        "국내": kor[:8],
        "국내역할": lead or (["참여"] if kor else []),
        # 분석 탭 '나라별' — 교신이 안 잡히는 1인 저자 논문은 제1저자 나라를 교신으로도 쓴다
        "국가": {"제1": first_c, "교신": corr_c or ([first_c] if n == 1 and first_c else [])},
        "키워드": kws,
        "결론": conclusion_of(mc),
    }


def fetch_articles(pmids, by_ta):
    out = []
    for i in range(0, len(pmids), 200):
        chunk = pmids[i:i + 200]
        root = None
        for attempt in range(4):                  # 가끔 응답이 중간에 끊겨 XML이 깨진다 — 다시 받는다
            try:
                root = ET.fromstring(eutils("efetch.fcgi", db="pubmed", retmode="xml", id=",".join(chunk)).content)
                break
            except (ET.ParseError, requests.RequestException) as e:
                log(f"  efetch 재시도 {attempt + 1}: {type(e).__name__}")
                time.sleep(3 * (attempt + 1))
        if root is None:
            raise RuntimeError("efetch 4번 실패")
        for pa in root.findall("PubmedArticle"):
            a = parse_article(pa, by_ta)
            if a:
                out.append(a)
        log(f"  efetch {min(i + 200, len(pmids))}/{len(pmids)}")
    return out


def fill_countries(papers, status, limit=2000):
    """소속에 나라 이름이 없어 비어 있는 제1·교신 나라를 OpenAlex 기관 정보로 채운다(DOI로 50편씩).
    한 번 물어본 논문은 `국가확인`을 붙여 다시 묻지 않는다."""
    todo = [p for p in papers if p.get("doi") and not p.get("국가확인")
            and (not p["국가"]["제1"] or not p["국가"]["교신"])][:limit]
    filled = 0
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        by_doi = {p["doi"].lower(): p for p in chunk}
        try:
            r = requests.get("https://api.openalex.org/works", headers=UA, timeout=60, params={
                "filter": "doi:" + "|".join(by_doi), "per-page": 50,
                "select": "doi,authorships"}).json()
        except Exception as e:
            log("  OpenAlex 나라 실패:", type(e).__name__)
            break
        for w in r.get("results", []):
            p = by_doi.get((w.get("doi") or "").replace("https://doi.org/", "").lower())
            if not p:
                continue
            au = w.get("authorships") or []
            iso = lambda a: next((ISO.get(c) for c in (a.get("countries") or []) if ISO.get(c)), "")
            c = p["국가"]
            if not c["제1"] and au:
                c["제1"] = iso(au[0])
                filled += bool(c["제1"])
            if not c["교신"]:
                cs = [iso(a) for a in au if a.get("is_corresponding")] or ([iso(au[-1])] if p.get("교신추정") and au else [])
                c["교신"] = [x for x in dict.fromkeys(cs) if x]
                filled += bool(c["교신"])
        for p in chunk:
            p["국가확인"] = True
        time.sleep(0.2)
    status["나라"] = f"OpenAlex로 채움 {filled} · 물어본 논문 {len(todo)}"


def journal_stats(journals, old):
    """OpenAlex 2년 평균 피인용 — 실패하면 지난 값."""
    out = {}
    for j in journals:
        prev = (old or {}).get(j["약어"], {})
        try:
            s = requests.get(f"https://api.openalex.org/sources/issn:{j['issn']}", headers=UA, timeout=30).json()
            out[j["약어"]] = {"저널": j["저널"], "issn": j["issn"], "분류": j.get("분류", ""), "순위": int(j["순위"]),
                             "지표": round(s["summary_stats"]["2yr_mean_citedness"], 2),
                             "h": s["summary_stats"].get("h_index")}
        except Exception:
            out[j["약어"]] = prev or {"저널": j["저널"], "issn": j["issn"], "분류": j.get("분류", ""),
                                      "순위": int(j["순위"]), "지표": None}
        time.sleep(0.2)
    return out


def main():
    journals = load_journals()
    by_ta = {j["약어"].lower(): j for j in journals}
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    papers = {p["pmid"]: p for p in old.get("논문", [])}
    status = {}
    end = NOW.date()
    start = end - timedelta(days=DAYS)
    try:
        pmids = search_pmids(journals, start, end)
        log(f"PubMed {start}~{end}: {len(pmids)}건")
        fresh = fetch_articles(pmids, by_ta)
        status["수집"] = f"{start}~{end} PubMed {len(pmids)}건 → {len(fresh)}편"
    except Exception as e:
        log("PubMed 수집 실패:", type(e).__name__, e)
        status["수집"] = f"실패 ({type(e).__name__}) — 지난 목록 유지"
        fresh = []
    for a in fresh:
        papers[a["pmid"]] = a

    # 공개일 = 출판일과 PubMed 등록일 중 빠른 날 (연구성과 레이더와 같은 기준)
    for v in papers.values():
        days = [x for x in (v.get("출판일"), v.get("등록일")) if x]
        v["공개일"] = min(days) if days else ""
        late = v.get("출판일") and v.get("등록일") and v["출판일"] < v["등록일"] and \
            (datetime.fromisoformat(v["등록일"]) - datetime.fromisoformat(v["출판일"])).days > LATE_DAYS
        if late:
            v["늦은등록"] = True
        else:
            v.pop("늦은등록", None)
    keep = {j["약어"] for j in journals}
    papers = {k: v for k, v in papers.items() if (v.get("공개일") or "9999") >= FROM_DATE and v["약어"] in keep}

    # 새로 받은 논문은 PubMed 기준으로 나라를 다시 매겼으니 OpenAlex 확인 표시를 지운다
    for a in fresh:
        if a["pmid"] in papers:
            papers[a["pmid"]].pop("국가확인", None)
    fill_countries(list(papers.values()), status)
    jstats = journal_stats(journals, old.get("저널"))
    items = list(papers.values())
    ko_cache = translate_titles(items, old.get("번역", {}), status)
    items = sorted(papers.values(), key=lambda p: (p.get("공개일", ""), p["pmid"]), reverse=True)
    status["국내"] = sum(1 for p in items if p["국내"])
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "생성": NOW.strftime("%Y-%m-%d %H:%M"),
        "시작일": FROM_DATE,
        "상태": status,
        "건수": len(items),
        "저널": jstats,
        "번역": ko_cache,
        "논문": items,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
