"""주주명부·가족관계·임원명단 자료 → 특수관계 판독 입력(case). 작성 Mia(윤승미)
뽑기만 Solar(Document Parse + Solar Pro 4)가 하고, 지분율은 원문 숫자와 대조해 검증한다. 판정은 related.py.
"""
import re

from . import upstage


PROMPT = """아래 자료에서 특수관계 판독용 관계표를 뽑는다. 판정은 하지 않는다. 자료에 없는 사람·관계·숫자는 만들지 않는다.
- people: {{이름: {{"구분": "개인"|"법인"}}}} — 법인명은 자료 표기 그대로(㈜ 포함)
- family: [[a, b, "부모자녀"|"배우자"]] — 부모자녀는 [부모, 자녀] 순서. "자녀"·"부"·"모" 관계를 이 형태로 바꾼다.
  촌수만 적힌 먼 친척은 중간 인물이 자료에 있으면 그 사슬로, 없으면 family_note에 원문 그대로.
- stakes: [[주주, 법인, 지분율]] — 지분율은 0~1 소수. '기타 소액주주'처럼 특정되지 않는 주주는 넣지 않는다.
- officers: {{법인: [임원]}}, employees: {{법인: [직원]}}
- influence: [[영향력자, 법인]] — 임원 선임·사업방침 결정 진술이 있을 때만
- basis_date: 자료의 기준일(YYYY-MM-DD), 없으면 ""
- family_note: [원문 그대로의 관계 문장]
[자료]
{doc}"""


def norm_name(x):
    """법인 표기 통일: (주)·주식회사 → ㈜ (자료마다 표기가 달라 같은 법인이 둘로 갈리지 않게)."""
    x = re.sub(r"\s+", " ", str(x)).strip()
    x = re.sub(r"^\(주\)\s*|^주식회사\s*", "㈜", x)
    return re.sub(r"\s*\(주\)$|\s*주식회사$", "", x) if not x.startswith("㈜") else x


def normalize(j):
    n = norm_name
    j["people"] = {n(k): v for k, v in (j.get("people") or {}).items()}
    j["family"] = [[n(a), n(b), t] for a, b, t in j.get("family") or []]
    j["stakes"] = [[n(h), n(c), r] for h, c, r in j.get("stakes") or []]
    for k in ("officers", "employees"):
        j[k] = {n(c): [n(x) for x in xs] for c, xs in (j.get(k) or {}).items()}
    for k in ("influence", "livelihood"):
        j[k] = [[n(a), n(b)] for a, b in j.get(k) or []]
    j["group"] = {g: [n(x) for x in xs] for g, xs in (j.get("group") or {}).items()}
    for h, c, _ in j["stakes"]:
        for x in (h, c):
            j["people"].setdefault(x, {"구분": "법인" if x.startswith("㈜") or re.search(r"법인|회사", x) else "개인"})
    for a, b, _ in j["family"]:
        for x in (a, b): j["people"].setdefault(x, {"구분": "개인"})
    return j


def to_case(j):
    """추출 결과 → related.judge_* 입력."""
    return {"people": j["people"], "family": [tuple(x) for x in j["family"]], "stakes": [(h, c, float(r)) for h, c, r in j["stakes"]],
            "officers": j.get("officers", {}), "employees": j.get("employees", {}), "livelihood": [tuple(x) for x in j.get("livelihood", [])],
            "influence": [tuple(x) for x in j.get("influence", [])], "group": j.get("group", {})}


def _pct_ok(doc, r):
    """지분율이 원문에 있는 숫자인지(소수점 한 자리 반올림 허용)."""
    p = round(r * 100, 1)
    return any(abs(float(x) - p) < 0.06 for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", doc))


def from_text(doc):
    j = upstage.chat_json(PROMPT.format(doc=doc[:14000]), max_tokens=3000)
    stakes, dropped = [], []
    for s in j.get("stakes", []):
        try:
            h, c, r = s[0], s[1], float(s[2]); r = r / 100 if r > 1 else r
        except Exception: continue
        (stakes if _pct_ok(doc, r) else dropped).append([h, c, r])
    j["stakes"] = stakes
    j["검증"] = {"지분율_원문대조_통과": len(stakes), "원문에_없는_지분율_제외": dropped}
    for k in ("people", "family", "officers", "employees", "influence", "family_note"):
        j.setdefault(k, {} if k in ("people", "officers", "employees") else [])
    for h, c, _ in stakes:  # 표에 있는데 people에 빠진 당사자 보충
        for x in (h, c):
            j["people"].setdefault(x, {"구분": "법인" if re.search(r"㈜|\(주\)|주식회사|법인", x) else "개인"})
    return j


def _rows(md, title):
    """'## N. 제목' 아래 마크다운 표 행 → [[셀...]] (머리행·구분행 제외)."""
    m = re.search(r"^#+\s*\d*\.?\s*" + title + r".*?$(.*?)(?=^#+\s|\Z)", md, re.S | re.M)
    if not m: return []
    clean = lambda c: re.sub(r"【[^】]*】|\[\^?\d+\]", "", c).strip()
    rows = [[clean(c) for c in l.strip().strip("|").split("|")] for l in m.group(1).splitlines() if l.strip().startswith("|")]
    return [r for r in rows[1:] if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]


def from_tables(md):
    """Solar Pro 4가 낸 사람용 표 → 관계표(JSON 없이 표를 코드가 직접 읽음)."""
    j = {"people": {}, "family": [], "stakes": [], "officers": {}, "employees": {}, "livelihood": [], "influence": [], "group": {},
         "family_note": [], "transactions": []}
    d = re.search(r"기준일\s*[:：]\s*(\d{4})\D(\d{1,2})\D(\d{1,2})", md)
    j["basis_date"] = f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else ""
    for r in _rows(md, "주주"):
        if len(r) < 4: continue
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", r[3])
        if not m or not r[1] or "기타" in r[1]: continue
        j["stakes"].append([r[1], r[0], float(m.group(1)) / 100])
        j["people"][r[1]] = {"구분": "법인" if "법인" in r[2] else "개인"}
        j["people"][r[0]] = {"구분": "법인"}
    for r in _rows(md, "가족"):
        if len(r) < 3: continue
        a, rel, b = r[0], r[1], r[2]
        if "배우자" in rel: j["family"].append([a, b, "배우자"])
        elif rel in ("자녀", "아들", "딸") or "자녀" in rel: j["family"].append([a, b, "부모자녀"])
        elif rel in ("부", "모", "부친", "모친", "아버지", "어머니"): j["family"].append([b, a, "부모자녀"])
        else: j["family_note"].append(" ".join(r))
    for r in _rows(md, "임원"):
        if len(r) < 3: continue
        key = "employees" if re.search(r"직원|사원|과장|대리|주임|팀장|부장|차장", r[2]) and not re.search(r"이사|감사|대표", r[2]) else "officers"
        j[key].setdefault(r[0], []).append(r[1])
    for r in _rows(md, "사실상"):
        if len(r) < 3 or r[0] in ("없음", "-"): continue
        if "영향력" in r[0]: j["influence"].append([r[1], r[2]])
        elif "생계" in r[0]: j["livelihood"].append([r[3], r[1]])
        elif "기업집단" in r[0]: j["group"].setdefault(r[2] or "기업집단", []).append(r[1])
    for r in _rows(md, "검토 대상 거래"):
        if len(r) >= 3: j["transactions"].append({"from": r[0], "to": r[1], "amount": r[2], "note": r[3] if len(r) > 3 else ""})
    m = re.search(r"^#+\s*\d*\.?\s*확인 필요.*?$(.*?)(?=^#+\s|\Z)", md, re.S | re.M)
    if m: j["family_note"] += [re.sub(r"【[^】]*】|\s*\|\s*$", "", l.strip("-• ")).strip() for l in m.group(1).splitlines() if l.strip().strip("-• ")]
    return j


def from_pdf(path):
    """PDF → Document Parse → Solar Pro 4(관계표 추출) → normalize.

    UPSTAGE_API_KEY가 필요하다(console.upstage.ai에서 발급). 결과는 '사람 확인 필요'.
    """
    doc = upstage.parse(path)
    doc = doc if isinstance(doc, str) else doc.get("text", "")
    return {**normalize(from_text(doc)), "출처": "Document Parse + Solar Pro 4"}
