"""일감몰아주기 검토 자료 → 증여의제이익 계산 입력. 작성 Mia(윤승미)
표 정리만 Solar Pro 4(Document Parse + 채팅)가 하고, 지배주주·보유비율·계산은 코드(related.py)가 한다.

PDF 도구는 UPSTAGE_API_KEY가 필요하다(console.upstage.ai에서 발급). 결과는 '사람 확인 필요'.
"""
import re

from . import related as R
from .related_intake import _rows, norm_name, upstage


def _num(x):
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(x or ""))
    return float(m.group(0).replace(",", "")) if m else 0.0


def _pct(x):
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(x or ""))
    return float(m.group(1)) / 100 if m else None


def from_tables(md):
    head = {r[0]: r[1] for r in _rows(md, "수혜법인") if len(r) >= 2}
    corp = norm_name(head.get("법인명", ""))
    size = next((s for s in ("중소", "중견", "일반") if s in head.get("기업 규모", "")), "일반")
    stakes, people, notes = [], {}, []
    for r in _rows(md, "수혜법인 주주"):
        p = _pct(r[2]) if len(r) >= 3 else None
        if p is None or "기타" in r[0]: continue
        h = norm_name(r[0]); stakes.append((h, corp, p))
        people[h] = {"구분": "법인" if "법인" in r[1] or h.startswith("㈜") else "개인"}
    for r in _rows(md, "주주법인"):
        p = _pct(r[2]) if len(r) >= 3 else None
        if p is None or "기타" in r[1]: continue
        c, h = norm_name(r[0]), norm_name(r[1]); stakes.append((h, c, p))
        people.setdefault(h, {"구분": "법인" if h.startswith("㈜") else "개인"}); people.setdefault(c, {"구분": "법인"})
    people[corp] = {"구분": "법인"}
    sales, excluded = {}, {}
    for r in _rows(md, "매출처"):
        if len(r) < 3 or "기타" in r[0] or re.search(r"특수관계\s*없음", r[2]): continue
        c = norm_name(r[0]); sales[c] = _num(r[1])
        if len(r) > 3 and _num(r[3]): excluded[c] = _num(r[3])
    dom, why = R.dominant_shareholder(people, [], stakes, corp)
    doms = dom if isinstance(dom, list) else [dom] if dom else []
    rel, via = {}, {}
    for d in doms:
        for path, ratio in R.paths(stakes, d, corp):
            name = "직접" if len(path) == 2 else f"{path[-2]} 경유"
            rel[name] = rel.get(name, 0) + ratio
            if len(path) > 2: via[name] = path[-2]
    held = {c: sum(r for d in doms for _, r in R.paths(stakes, d, c)) for c in sales}
    m = re.search(r"^#+\s*\d*\.?\s*확인 필요.*?$(.*?)(?=^#+\s|\Z)", md, re.S | re.M)
    if m: notes = [re.sub(r"【[^】]*】", "", l).strip("-• ").strip() for l in m.group(1).splitlines() if l.strip("-• ").strip()]
    return {"수혜법인": corp, "규모": size, "지배주주": doms, "지배주주_판정": why,
            "입력": dict(size=size, op_income=_num(head.get("세무조정 후 영업손익")), taxable_income=_num(head.get("각 사업연도 소득금액")),
                       tax=_num(head.get("법인세 산출세액")), sales_total=_num(head.get("매출액")), sales_by_corp=sales, relations=rel,
                       holdings_in_related={c: v for c, v in held.items() if v}, indirect_corp_of=via, excluded_by_corp=excluded),
            "확인 필요": notes}


def compute(md):
    j = from_tables(md)
    return {**j, "계산": R.tunnelling_nts(j["수혜법인"], **j["입력"])}


_TUNNEL_PROMPT = """아래 '신고안내 작성사례' 텍스트에서 일감몰아주기 증여의제이익 계산용 데이터를 JSON으로 추출한다.
판정은 하지 않는다. 자료에 없는 숫자와 관계는 만들지 않는다.

출력 JSON 키:
- 수혜법인: {"법인명": "...", "기업 규모": "중소"|"중견"|"일반"}
- 수혜법인 주주: [{"주주": "...", "특수관계": "...", "지분율": "20%" 또는 null}]
- 주주법인: [{"법인": "...", "주주": "...", "지분율": "30%" 또는 null}]
- 매출처: [{"법인": "...", "매출액": "1,000,000,000원" 또는 숫자, "과세제외매출액": "..." 또는 null}]
- 세무조정 후 영업손익: "..." 또는 null
- 각 사업연도 소득금액: "..." 또는 null
- 법인세 산출세액: "..." 또는 null
- 매출액: "..." 또는 null
- 확인 필요: [원문 확인 필요 문장]

숫자는 원문 표기 그대로(남은 코드에서 변환). 지분율·매출액은 "기타 소액주주" 등 특정되지 않으면 넣지 않는다.
[자료]
{doc}"""


def from_text(doc):
    """Document Parse 텍스트 → Solar Pro 4로 JSON 추출 → 표 형태 정규화 → compute 입력."""
    j = upstage.chat_json(_TUNNEL_PROMPT.format(doc=doc[:14000]), max_tokens=3000)

    md = ["## 1. 수혜법인", "| 항목 | 값 |", "|---|---|"]
    corp = j.get("수혜법인", {}) or {}
    md.append(f"| 법인명 | {corp.get('법인명', '')} |")
    md.append(f"| 기업 규모 | {corp.get('기업 규모', '')} |")

    md += ["", "## 2. 수혜법인 주주", "| 주주 | 특수관계 | 지분율 |", "|---|---|---|---|"]
    for sh in (j.get("수혜법인 주주") or []):
        md.append(f"| {sh.get('주주', '')} | {sh.get('특수관계', '')} | {sh.get('지분율', '')} |")

    md += ["", "## 3. 주주법인", "| 법인 | 주주 | 지분율 |", "|---|---|---|---|"]
    for sh in (j.get("주주법인") or []):
        md.append(f"| {sh.get('법인', '')} | {sh.get('주주', '')} | {sh.get('지분율', '')} |")

    md += ["", "## 4. 매출처", "| 법인 | 매출액 | 과세제외매출액 |", "|---|---|---|---|"]
    for c in (j.get("매출처") or []):
        md.append(f"| {c.get('법인', '')} | {c.get('매출액', '')} | {c.get('과세제외매출액', '')} |")

    md += ["", "## 5. 단일 값", "| 항목 | 값 |", "|---|---|"]
    for k in ("세무조정 후 영업손익", "각 사업연도 소득금액", "법인세 산출세액", "매출액"):
        v = j.get(k)
        if v:
            md.append(f"| {k} | {v} |")

    if j.get("확인 필요"):
        md += ["", "## 확인 필요", ""]
        md += [f"- {n}" for n in j["확인 필요"]]

    return compute("\n".join(md))


def from_pdf(path):
    """PDF → Document Parse → Solar Pro 4(관계표 추출) → compute.

    UPSTAGE_API_KEY가 필요하다(console.upstage.ai에서 발급). 결과는 '사람 확인 필요'.
    """
    doc = upstage.parse(path)
    doc = doc if isinstance(doc, str) else doc.get("text", "")
    return {**from_text(doc), "출처": "Document Parse + Solar Pro 4"}
