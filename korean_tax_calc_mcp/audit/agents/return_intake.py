"""법인세 신고서 PDF → 사전검토 입력(precheck.corp SCHEMA 키). 작성 Mia(윤승미)
Document Parse + Solar Pro 4가 서식을 사람이 보는 표로 옮기기만 하고, 칸 번호 → 입력키 매핑·숫자 변환은 코드가 한다.

PDF 도구는 UPSTAGE_API_KEY가 필요하다(console.upstage.ai에서 발급). 결과는 '사람 확인 필요'.
"""
import re

from .related_intake import _rows
from . import upstage


# (서식 표 제목, 항목 라벨 정규식) → 입력키
MAP = {
    "신고서": [(r"수입금액", "신고서.수입금액"), (r"과세표준", "신고서.과세표준"), (r"산출세액", "신고서.산출세액"),
             (r"총부담세액", "신고서.총부담세액"), (r"기납부세액", "신고서.기납부세액"), (r"차감납부할세액", "신고서.차감납부할세액")],
    "조정계산서": [(r"결산서상\s*당기순손익|당기순이익", "조정계산서.결산서상당기순이익"), (r"익금산입", "조정계산서.익금산입"),
               (r"손금산입", "조정계산서.손금산입"), (r"차가감소득금액", "조정계산서.차가감소득금액"),
               (r"기부금\s*한도초과액", "조정계산서.기부금한도초과액"), (r"이월액\s*손금산입", "조정계산서.기부금한도초과이월액손금산입"),
               (r"각\s*사업연도\s*소득금액", "조정계산서.각사업연도소득금액"), (r"이월결손금", "조정계산서.이월결손금"),
               (r"비과세소득", "조정계산서.비과세소득"), (r"소득공제", "조정계산서.소득공제"), (r"^과세표준|과세표준$", "조정계산서.과세표준"),
               (r"산출세액", "조정계산서.산출세액"), (r"최저한세\s*적용\s*대상", "조정계산서.최저한세적용대상공제감면세액"),
               (r"최저한세\s*적용\s*제외", "조정계산서.최저한세적용제외공제감면세액"), (r"가산세", "조정계산서.가산세"),
               (r"가감계", "조정계산서.가감계"), (r"기납부세액\s*합계|^기납부세액", "조정계산서.기납부세액"),
               (r"차감납부할\s*세액", "조정계산서.차감납부할세액")],
}


def _num(s):
    """'1,234' → 1234, '-1,234'·'△1,234' → -1234, 숫자 없으면 None."""
    s = re.sub(r"【[^】]*】", "", str(s or "")).strip()
    m = re.search(r"([△\-]?)\s*(\d[\d,]*)", s)
    if not m: return None
    v = int(m.group(2).replace(",", ""))
    return -v if m.group(1) else v


def from_tables(md):
    d, raw = {}, {}
    for title, pats in MAP.items():
        for r in _rows(md, title):
            if len(r) < 2: continue
            label = re.sub(r"^[\s\d①-⑳㉑-㊿]+", "", r[-2] if len(r) >= 3 else r[0]).strip()
            v = _num(r[-1])
            if v is None: continue
            for pat, key in pats:
                if re.search(pat, label) and key not in d:
                    d[key] = v; raw[key] = " | ".join(r); break
    # 기본: 사업연도 → 개시일·종료일, 법인구분
    for r in _rows(md, "기본"):
        if len(r) < 2: continue
        if "사업연도" in r[0]:
            ds = re.findall(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", r[1])
            if len(ds) >= 2:
                d["기본.개시일"], d["기본.종료일"] = [f"{y}-{int(m):02d}-{int(dd):02d}" for y, m, dd in ds[:2]]
        if "법인구분" in r[0]: d["기본.중소기업"] = "중소" in r[1]
    # 기납부세액 합계: 서식은 중간예납·원천납부 등 소계/합계 행 — 라벨이 '합계'라 위에서 못 잡으면 구성 항목 합으로
    if "조정계산서.기납부세액" not in d:
        parts = {k: _num(r[-1]) for r in _rows(md, "조정계산서") if len(r) >= 2
                 for k in ("중간예납", "수시부과", "원천납부", "간접투자회사") if k in (r[-2] if len(r) >= 3 else r[0])}
        if parts: d["조정계산서.기납부세액"] = sum(v for v in parts.values() if v)
    # 조정계산서가 있으면 빈 칸은 0(서식상 미기재 = 해당 없음) — 대사 규칙이 돌도록
    if any(k.startswith("조정계산서.") for k in d):
        for k in ("조정계산서 기부금한도초과이월액손금산입", "조정계산서.비과세소득", "조정계산서.소득공제",
                  "조정계산서.최저한세적용대상공제감면세액", "조정계산서.최저한세적용제외공제감면세액", "조정계산서.가산세", "조정계산서.이월결손금"):
            d.setdefault(k, 0)
    yubo = []
    for r in _rows(md, "자본금과\\s*적립금[^\\n]*을"):
        if len(r) >= 5 and not re.search(r"합\s*계", r[0]):
            yubo.append({"과목": r[0].strip(), "기초": _num(r[1]) or 0, "감소": _num(r[2]) or 0, "증가": _num(r[3]) or 0, "기말": _num(r[4]) or 0})
    if yubo: d["자적을.당기"] = yubo
    return d, raw


JUNK = re.compile(r"확인\s*불가|해당\s*(칸|서식)?\s*없음|명시되지\s*않|^\s*-?\s*$")


def _clean_rows(md, title, width):
    """반복 머리행·'(해당 없음)' 행 제거."""
    out = []
    for r in _rows(md, title):
        if len(r) < width: continue
        if JUNK.search(r[0]) or r[0] in ("키", "구분", "과목", "사업연도개시일"): continue
        out.append(r)
    return out


def from_key_tables(md):
    """Solar Pro 4가 생성한 키 표 → 사전검토 입력. 코드가 숫자·형식만 검증.
    같은 키가 여러 쪽 묶음에서 나오면 처음 나온 유효값을 쓴다."""
    d = {}
    for r in _clean_rows(md, "단일 값", 2):
        k = re.sub(r"\(.*?\)", "", r[0]).strip(); v = r[1].strip()
        if "." not in k or not v or JUNK.search(v): continue
        if k == "기본.사업연도":
            ds = re.findall(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", v)
            if len(ds) >= 2 and "기본.개시일" not in d:
                d["기본.개시일"], d["기본.종료일"] = [f"{y}-{int(m):02d}-{int(x):02d}" for y, m, x in ds[:2]]
            continue
        if k in d or k == "기본.법인명": continue
        if k == "기본.법인구분": d["기본.중소기업"] = "중소" in v; continue
        if k == "최저한세.적용세율":
            m = re.search(r"(\d+(?:\.\d+)?)", v)
            if m:
                x = float(m.group(1)); x = x / 100 if x > 1 else x
                if 0.07 <= x <= 0.17: d[k] = x
            continue
        n = _num(v)
        if n is not None: d[k] = n
    add = _clean_rows(md, "소득금액조정합계표", 4)
    if add:
        yubo = {}
        for g, name, amt, disp in add[:len(add)]:
            if "유보" not in disp: continue
            dec = g.strip().startswith("손금산입") or "감소" in disp or "△" in disp
            yubo.setdefault(name.strip(), {"감소": 0, "증가": 0})["감소" if dec else "증가"] += _num(amt) or 0
        for name in [n for n, v in yubo.items() if v["증가"] == 0 and v["감소"]]:
            head = re.split(r"\s", name)[0]
            tgt = next((n for n in yubo if n != name and n.split()[0] == head and yubo[n]["증가"]), None)
            if tgt: yubo[tgt]["감소"] += yubo.pop(name)["감소"]
        d["합계표.유보처분"] = yubo
    y0 = d.get("기본.개시일", "2025-01-01")[4:]
    loss = []
    for r in _clean_rows(md, "이월결손금", 3):
        m = re.search(r"(\d{4})(?:\D+(\d{1,2})\D+(\d{1,2}))?", r[0])
        if not m: continue
        start = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m.group(2) else m.group(1) + y0
        loss.append({"개시일": start, "발생액": _num(r[1]) or 0, "소급공제": 0, "기공제": 0, "충당액": 0, "당기공제": _num(r[2]) or 0})
    if loss and not any(x["당기공제"] for x in loss) and d.get("조정계산서.이월결손금"):
        left = d["조정계산서.이월결손금"]
        for x in sorted(loss, key=lambda x: x["개시일"]):
            u = min(left, x["발생액"]); x["당기공제"] = u; left -= u
    if loss: d["이월결손금.내역"] = loss
    yb = [r for r in _clean_rows(md, r"자본금과\s*적립금[^\n]*을", 5) if not re.search(r"합\s*계|^계$", r[0].strip())]
    if yb:
        d["자적을.당기"] = [{"과목": r[0].strip(), "기초": _num(r[1]) or 0, "감소": _num(r[2]) or 0, "증가": _num(r[3]) or 0, "기말": _num(r[4]) or 0} for r in yb]
        d.setdefault("자적을.전기기말", {x["과목"]: x["기초"] for x in d["자적을.당기"]})
    if any(x.startswith("조정계산서.") for x in d):
        for k in ("조정계산서 기부금한도초과액", "조정계산서 기부금한도초과이월액손금산입", "조정계산서.비과세소득", "조정계산서.소득공제",
                  "조정계산서.최저한세적용제외공제감면세액", "조정계산서.가산세"):
            d.setdefault(k, 0)
    if "최저한세.대상감면" in d or "조정계산서.최저한세적용대상공제감면세액" in d:
        d.setdefault("최저한세.대상감면", d.get("조정계산서.최저한세적용대상공제감면세액", 0))
        d.setdefault("최저한세.제외감면", d.get("조정계산서.최저한세적용제외공제감면세액", 0))
        d.setdefault("최저한세.감면전과세표준", d.get("조정계산서.과세표준"))
        d.setdefault("최저한세.산출세액", d.get("조정계산서.산출세액"))
        d.setdefault("최저한세.배제액신고", 0)
    if any(x.startswith("기업업무추진비.") for x in d):
        for k in ("기업업무추진비.자산계상액", "기업업무추진비.적격증빙미수취", "기업업무추진비.문화지출", "기업업무추진비.전통시장지출",
                  "기업업무추진비.신고문화한도", "기업업무추진비.신고전통시장한도"):
            d.setdefault(k, 0)
    return d


def from_extract(j):
    """Solar Pro 4가 출력한 JSON → 사전검토 입력. 키 '서식_항목' → '서식.항목'."""
    if isinstance(j, str):
        import json as _json
        m = re.search(r"\{.*\}", j, re.S); j = _json.loads(m.group(0)) if m else {}
    md = ["## 1. 단일 값", "| 키 | 값 | 서식·칸 |", "|---|---|---|"]
    for k, v in j.items():
        if isinstance(v, list) or v in (None, ""): continue
        md.append(f"| {k.replace('_', '.', 1)} | {v} | |")
    md += ["", "## 2. 소득금액조정합계표", "| 구분 | 과목 | 금액 | 처분 |", "|---|---|---|---|"]
    md += [f"| {r.get('구분','')} | {r.get('과목','')} | {r.get('금액','')} | {r.get('처분','')} |" for r in j.get("합계표_행") or []]
    md += ["", "## 3. 이월결손금", "| 사업연도개시일 | 발생액 | 당기공제 | 잔액 |", "|---|---|---|---|"]
    md += [f"| {r.get('사업연도','')} | {r.get('발생액','')} | {r.get('당기공제','')} | {r.get('잔액','')} |" for r in j.get("이월결손금_행") or []]
    md += ["", "## 4. 자본금과 적립금 조정명세서(을)", "| 과목 | 기초 | 감소 | 증가 | 기말 |", "|---|---|---|---|---|"]
    md += [f"| {r.get('과목','')} | {r.get('기초','')} | {r.get('감소','')} | {r.get('증가','')} | {r.get('기말','')} |" for r in j.get("자적을_행") or []]
    md = "\n".join(md)
    return from_key_tables(md), md


def _split(path, n=3):
    """신고서 PDF를 n쪽씩 나눔 — 서식 7종·10쪽을 한 번에 옮기면 Instruct가 시간 초과."""
    import tempfile
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(path); out = []
    for i in range(0, len(r.pages), n):
        w = PdfWriter()
        for pg in r.pages[i:i + n]: w.add_page(pg)
        f = tempfile.NamedTemporaryFile(suffix=f"_{i // n + 1}.pdf", delete=False); w.write(f.name); out.append(f.name)
    return out


def _merge(parts):
    """쪽 묶음별 표 → 하나로: 같은 제목의 표 행을 합치고 단일 값은 먼저 나온 값 유지."""
    sec, order = {}, []
    for t in parts:
        cur = None
        for line in t.splitlines():
            m = re.match(r"^#+\s*\d*\.?\s*(.+?)\s*$", line)
            if m:
                cur = m.group(1);
                if cur not in sec: sec[cur] = []; order.append(cur)
                continue
            if cur and line.strip().startswith("|"):
                if not sec[cur] or not re.fullmatch(r"\|?[\s:\-|]+\|?", line.strip()) or len(sec[cur]) < 2:
                    if line not in sec[cur] or not re.search(r"\d", line): sec[cur].append(line)
            elif cur and line.strip().startswith("-") and "없음" not in line:
                sec[cur].append(line)
    return "\n\n".join(f"## {i}. {k}\n" + "\n".join(sec[k]) for i, k in enumerate(order, 1))


_EXTRACT_PROMPT = """아래 법인세 신고서 PDF 텍스트에서 다음 항목들을 찾아 JSON으로 출력하라.
없으면 null로 둔다. 숫자 값은 원문 표기 그대로(콤마·△ 포함) 출력 — 코드에서 변환한다.

항목 키(코드에서 '.'으로 변환됨):
- 기본_사업자등록번호: 사업자등록번호
- 기본_법인명: 법인명
- 기본_사업연도: 사업연도(예: "2025.1.1.~2025.12.31.")
- 기본_법인구분: "중소" 포함 여부
- 기본_개시일: 사업연도 개시일(YYYY-MM-DD)
- 기본_종료일: 사업연도 종료일(YYYY-MM-DD)
- 신고서_수입금액: 신고서 수입금액(원)
- 신고서_과세표준: 신고서 과세표준(원)
- 신고서_산출세액: 신고서 산출세액(원)
- 신고서_총부담세액: 신고서 총부담세액(원)
- 신고서_기납부세액: 신고서 기납부세액(원)
- 신고서_차감납부할세액: 신고서 차감납부할세액(원)
- 조정계산서_손익계산서상당기순이익: 조정계산서 ① 당기순손익(원)
- 조정계산서_익금산입: 조정계산서 ② 익금산입(원)
- 조정계산서_손금산입: 조정계산서 ③ 손금산입(원)
- 조정계산서_차가감소득금액: 조정계산서 ④ 차가감소득금액(원)
- 조정계산서_기부금한도초과액: 조정계산서 ⑤ 기부금한도초과액(원)
- 조정계산서_기부금한도초과이월액손금산입: 조정계산서 ⑥ 이월액 손금산입(원)
- 조정계산서_각사업연도소득금액: 조정계산서 ⑦ 각 사업연도 소득금액(원)
- 조정계산서_이월결손금: 조정계산서 ⑪ 이월결손금 공제액(원)
- 조정계산서_비과세소득: 조정계산서 ⑫ 비과세소득(원)
- 조정계산서_소득공제: 조정계산서 ⑬ 소득공제(원)
- 조정계산서_산출세액: 조정계산서 산출세액(원)
- 조정계산서_최저한세적용대상공제감면세액: 조정계산서 최저한세 적용 대상 공제감면세액(원)
- 조정계산서_최저한세적용제외공제감면세액: 조정계산서 최저한세 적용 제외 공제감면세액(원)
- 조정계산서_가산세: 조정계산서 가산세(원)
- 조정계산서_가감계: 조정계산서 가감계(원)
- 조정계산서_기납부세액: 조정계산서 기납부세액 합계(원)

[PDF 텍스트]
{doc}"""


def from_pdf(path):
    """PDF → Document Parse → Solar Pro 4(키-값 추출) → 사전검토 입력.

    UPSTAGE_API_KEY가 필요하다(console.upstage.ai에서 발급). 결과는 '사람 확인 필요'.
    """
    doc = upstage.parse(path)
    doc = doc if isinstance(doc, str) else doc.get("text", "")
    j = upstage.chat_json(_EXTRACT_PROMPT.format(doc=doc[:14000]), max_tokens=3000)
    d, raw = from_extract(j)
    return {"입력": d, "원문행": raw, "표": doc[:2000], "출처": "Document Parse + Solar Pro 4"}


def fill_by_law(d):
    """신고서에 칸이 없지만 법령·기준으로 정해지는 값 → 채우고 출처를 '기준 보완'으로 남김."""
    added = {}
    sme = d.get("기본.중소기업")
    if sme is not None:
        if "최저한세.대상감면" in d or "조정계산서.최저한세적용대상공제감면세액" in d:
            added.setdefault("최저한세.적용여부", True)
            if sme: added.setdefault("최저한세.적용세율", 0.07)
            added.setdefault("최저한세.졸업연차", 0)
            added.setdefault("최저한세.제외감면", d.get("조정계산서.최저한세적용제외공제감면세액", 0))
        if "이월결손금.내역" in d or d.get("조정계산서.이월결손금"):
            added.setdefault("이월결손금.100%공제대상", bool(sme))
    for k, v in added.items():
        if k not in d: d[k] = v
    d.setdefault("_기준보완", []).extend(k for k in added if d.get(k) == added[k])
    return d


def vote(inputs):
    """여러 번 추출한 입력 → 칸별 다수결."""
    import json as _json
    from collections import Counter
    keys = set().union(*inputs); out, unsure = {}, {}
    need = len(inputs) // 2 + 1
    for k in keys:
        vals = [_json.dumps(d.get(k), ensure_ascii=False, sort_keys=True) for d in inputs]
        (top, n), = Counter(vals).most_common(1)
        if n >= need and top != "null": out[k] = _json.loads(top)
        elif top != "null" or n < len(inputs): unsure[k] = [d.get(k) for d in inputs]
    return out, unsure


def precheck_pdf(path):
    """법인세 신고서 PDF → 사전검토(오류 의심 목록)."""
    from . import precheck
    x = from_pdf(path)
    d = fill_by_law(x["입력"])
    return {**x, "사전검토": precheck.run(d, "법인")}
