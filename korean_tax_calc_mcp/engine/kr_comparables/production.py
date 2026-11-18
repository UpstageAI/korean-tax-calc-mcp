"""사업보고서 'II. 사업의 내용 > 3. 원재료 및 생산설비'에서 직접 생산 여부의 단서를 원문 그대로 뽑는다.

기능 분석에서 '후보가 직접 만드는가(공장·설비) / 외주로 만들게 하는가'를 볼 때 쓰는 자리.
'1. 사업의 개요'의 '제조 및 판매업 영위' 같은 사업 목적 문구로는 알 수 없고 이 절에 적혀 있다
(2026-11-18 화장품 업종 상장 13곳: 13곳 모두 절이 있고 11곳은 단서가 한쪽으로만 나옴).
- 판정하지 않는다 — 단서(문장·표 유무)와 원문 일부만 낸다. '직접 제조/안 함' 판정은 조문 MCP 몫.
- 비상장사 감사보고서에는 이 절이 없다 — 부르지 않는다.
Claude 작성(2026-11-18)."""
import re

from .statements import title_sections, txt

TEXT_MAX = 1500
SNIP = 60
# 자체 생산설비가 없다는 문장 — '자체 생산공장을 보유하고 있지 않습니다', '자체 생산설비 없이 OEM방식으로', '전 제품을 외주생산방식'
NO_OWN = re.compile(
    r"(?:자체|별도의?)\s*(?:생산|제조)?\s*(?:공장|시설|설비)[을를은는이가]?\s*(?:을\s*)?(?:보유하고\s*있지\s*(?:않|아니)|보유하지\s*(?:않|아니)|없이|없으|없습|없고|없음)"
    r"|(?:전|모든)\s*제품을?\s*(?:외주|위탁)\s*(?:생산|제조|가공)"
    r"|(?:외주|위탁)\s*생산\s*(?:방식|을\s*하고|하고)"
    r"|OEM(?:\s*/\s*ODM)?\s*(?:의\s*)?(?:방식|형태)으?로\s*(?:제품을\s*)?(?:생산|제조)"
    r"|(?:제품|제조)의?\s*생산을\s*(?:외주|위탁)|생산을\s*위탁")
# 직접 생산의 흔적 — 생산능력·생산실적·가동률 표, 공장별 설비 현황
OWN = re.compile(r"생산\s*능력|생산\s*실적|가\s*동\s*률|가\s*동\s*율|(?:공장|사업장)별\s*(?:자산|설비)|생산\s*설비\s*(?:의\s*)?현황|생산\s*시설\s*현황")
# '해당사항 없음'으로 지운 줄 — '생산실적 및 가동률 … 해당사항이 없습니다'는 흔적이 아님
VOID = re.compile(r"해당\s*사항\s*(?:이\s*)?없|표기하지\s*않|기재하지\s*않|생략|어렵|산정하지\s*않|하지\s*않습니다")
DATA = re.compile(r"단\s*위\s*[:：]|\(\s*단\s*위|\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s*%")   # 흔적 뒤에 실제 숫자 표가 있어야 함 — '생산능력' 소제목만 있고 '기획·마케팅에 주력'이면 흔적 아님


def section(s):
    """'원재료 및 생산설비'(또는 '생산 및 설비') 절의 원문(HTML). 없으면 ''."""
    secs = title_sections(s)
    start = next((i for i, (_a, _b, t) in enumerate(secs) if re.match(r"\s*I{1,2}\.\s*사업의\s*내용", t)), None)
    if start is None:
        return ""
    for a, b, t in secs[start + 1:]:
        if re.match(r"\s*(I{1,3}|IV|V)\.\s", t):
            break
        if re.search(r"생산\s*(?:및|과)?\s*설비|원재료\s*및\s*생산", t):
            return s[a:b]
    return ""


def _plain(sec):
    return re.sub(r"\s+", " ", txt(re.sub(r"<TITLE[^>]*>.*?</TITLE>", " ", sec, flags=re.S))).strip()


def _snips(text, pat, void_check=False):
    out = []
    for m in pat.finditer(text):
        around = text[max(0, m.start() - SNIP):m.end() + SNIP]
        if void_check:
            after = text[m.end():m.end() + 150]
            if VOID.search(text[m.start():m.end() + 100]) or not DATA.search(after):
                continue
        if around not in out:
            out.append(around)
    return out


def extract(s):
    """사업보고서 원문 → {'found', 'text', 'truncated', 'no_own_facility': [문장], 'own_production': [문장], 'problems': [..]}.

    no_own_facility: 자체 생산설비가 없다·외주로 생산한다는 원문 문장. own_production: 생산능력·생산실적·가동률·공장별 설비 현황 원문(‘해당사항 없음’으로 지운 줄은 뺌).
    둘 다 있으면 사업부문마다 다를 수 있다(예: 화장품은 외주, 다른 사업은 공장) — problems에 적는다."""
    sec = section(s)
    if not sec:
        return {"found": False, "text": "", "truncated": False, "no_own_facility": [], "own_production": [], "problems": ["원재료 및 생산설비 절 없음"]}
    text = _plain(sec)
    no_own = _snips(text, NO_OWN)
    own = _snips(text, OWN, void_check=True)
    problems = []
    if no_own and own:
        problems.append("자체 생산설비가 없다는 문장과 생산능력·설비 현황이 함께 있음 — 사업부문·자회사마다 다를 수 있어 원문 확인")
    return {"found": True, "text": text[:TEXT_MAX], "truncated": len(text) > TEXT_MAX,
            "no_own_facility": no_own[:3], "own_production": own[:3], "problems": problems}


MACHINERY = re.compile(r"기\s*계\s*(?:장\s*치|설\s*비)|생\s*산\s*설\s*비")
PPE = re.compile(r"유\s*형\s*자\s*산")


def machinery(s):
    """비상장 감사보고서 → 기계장치 계정이 있는지(2026-11-18). 반환 {'machinery_account': 없음|있음|불명, 'evidence': 원문 일부}.

    없음: 유형자산 주석은 있는데 '기계장치·기계설비·생산설비'라는 말이 전혀 없음 — 직접 생산하지 않는다는 단서.
    있음: 그 말이 있음 — 금액·비중은 아직 읽지 않음(회계정책 표의 내용연수만 있을 수도 있어 판단은 사람·조문 MCP).
    불명: 원문에서 유형자산 자체를 못 찾음(문서를 못 읽었을 수 있어 '없음'이라 하지 않음). 판정하지 않는다."""
    plain = re.sub(r"\s+", " ", txt(s or ""))
    if not PPE.search(plain):
        return {"machinery_account": "불명", "evidence": "원문에서 유형자산을 찾지 못함"}
    m = MACHINERY.search(plain)
    if not m:
        return {"machinery_account": "없음", "evidence": "유형자산 주석에 기계장치·기계설비·생산설비 계정 없음"}
    return {"machinery_account": "있음", "evidence": plain[max(0, m.start() - SNIP):m.end() + SNIP]}


_MACH_LAB = re.compile(r"^(?:기계장치|기계설비|생산설비)(?:\(\*\d*\))?$")
_COST_LAB = re.compile(r"^(?:취득원가|취득가액|원가)(?:\(\*\d*\))?$")
_TOTAL_LAB = re.compile(r"^(?:합계|계|총계)$")
_PPE_CLASS = re.compile(r"^(?:토지|건물|구축물|비품|공기구비품|공구와기구|차량운반구|시설장치|건설중인자산|임차개량자산)")
_END_COL = re.compile(r"^(?:기말|당기말|기말금액|기말잔액)")


def _ppe_sections(s):
    """감사보고서의 '유형자산' 번호 절을 모두(회계정책의 같은 제목 포함) — 표가 있는 절을 고르려고."""
    from .statements import _heading_title
    out = []
    for m in re.finditer(r">\s*(\d{1,2})\s*\.\s*(?:<[^>]+>\s*)*([^<]{0,80})", s):
        title = _heading_title(m.group(2))
        if re.match(r"^유형자산(?!처분|손상|재평가잉여|폐기)", title or "") and len(title) < 40:
            n = int(m.group(1))
            nxt = re.search(r">\s*%d\s*\.\s*[가-힣]" % (n + 1), s[m.end():m.end() + 120000])
            out.append(s[m.start():m.end() + (nxt.start() if nxt else 40000)])
    return out


def _cost_from_grid(g, ctx):
    """격자 하나에서 기계장치 취득원가 → (값, 유형자산 합계 또는 None, 설명) / ('없음', None, 설명) / None."""
    from .statements import num, txt
    hdr = range(min(4, len(g)))
    # 모양 1: 기계장치가 머리글 열, 취득원가가 행 이름
    for hi in hdr:
        mc = next((j for j, c in enumerate(g[hi]) if _MACH_LAB.match(c)), None)
        if mc is None: continue
        tc = next((j for j, c in enumerate(g[hi]) if _TOTAL_LAB.match(c)), None)
        for row in g[hi + 1:]:
            if row and _COST_LAB.match(row[0]) and mc < len(row) and num(row[mc]) is not None:
                tot = num(row[tc]) if tc is not None and tc < len(row) else None
                return num(row[mc]), tot, f"주석 표 열 '{g[hi][mc]}' × 행 '{row[0]}'"
    # 모양 2: 자산 종류가 행, 취득원가가 머리글 열(당기·전기 두 줄 머리글이면 처음 나온 취득원가 = 당기)
    for hi in hdr:
        cc = next((j for j, c in enumerate(g[hi]) if _COST_LAB.match(c)), None)
        if cc is None: continue
        body = g[hi + 1:]
        mrow = next((r for r in body if r and _MACH_LAB.match(r[0])), None)
        trow = next((r for r in body if r and _TOTAL_LAB.match(r[0])), None)
        if mrow and cc < len(mrow) and num(mrow[cc]) is not None:
            return num(mrow[cc]), (num(trow[cc]) if trow and cc < len(trow) else None), f"주석 표 행 '{mrow[0]}' × 열 '{g[hi][cc]}'"
        if not mrow and trow and any(r and _PPE_CLASS.match(r[0]) for r in body):
            return "없음", (num(trow[cc]) if cc < len(trow) else None), "주석 취득원가 표에 기계장치 행 없음 — " + ", ".join(r[0] for r in body if r and r[0])[:60]
    # 모양 3: 변동표 안에 '기계장치' 줄과 그 아래(또는 같은 줄 둘째 칸) '취득원가' 줄 — 기말 열(없으면 마지막 숫자)
    endc = next((j for hi in hdr for j, c in enumerate(g[hi]) if _END_COL.match(c)), None)
    for i, row in enumerate(g):
        if not (row and _MACH_LAB.match(row[0])):
            continue
        if len(row) > 1 and _COST_LAB.match(row[1]):
            sub = row
        elif i + 1 < len(g) and g[i + 1] and (_COST_LAB.match(g[i + 1][0]) or (len(g[i + 1]) > 1 and _COST_LAB.match(g[i + 1][1]))):
            sub = g[i + 1]
        else:
            continue
        v = num(sub[endc]) if endc is not None and endc < len(sub) else next((x for x in reversed([num(c) for c in sub]) if x is not None), None)
        if v is not None:
            return v, None, "주석 변동표 '기계장치 > 취득원가' 기말"
    # 모양 5: 한 표에 취득원가·감가상각누계액·장부금액 덩어리가 제목 없이 쌓임 — 기계장치 행이 여럿이고 음수(상각누계) 행이 있으면
    # 맨 앞 기계장치 행의 기말을 취득원가로. 취득원가 + 상각누계 = 장부금액(마지막 기계장치 행)일 때만 받는다.
    if endc is not None:
        mrows = [r for r in g if r and _MACH_LAB.match(r[0]) and endc < len(r) and num(r[endc]) is not None]
        if len(mrows) >= 3:
            cost, acc, book = num(mrows[0][endc]), num(mrows[1][endc]), num(mrows[-1][endc])
            if cost > 0 and acc < 0 and abs(cost + acc - book) <= max(1, abs(book) * 0.001):
                return cost, None, "주석 변동표 덩어리(취득원가·상각누계·장부금액) 중 취득원가 기말 — 취득원가+상각누계=장부금액 확인"
    # 모양 4: 표 바로 앞 글이 '취득원가'인 변동표(취득원가 변동·상각누계액 변동을 표 둘로) — 기계장치 행의 기말
    pre = re.sub(r"\s+", "", txt(ctx[:ctx.rfind("<TABLE")] if "<TABLE" in ctx else ctx))[-60:]
    if endc is not None and re.search(r"취득원가|취득가액", pre) and not re.search(r"감가상각누계|상각누계", pre):
        mrow = next((r for r in g if r and _MACH_LAB.match(r[0])), None)
        if mrow and endc < len(mrow) and num(mrow[endc]) is not None:
            return num(mrow[endc]), None, "주석 '취득원가' 변동표 기계장치 기말"
    return None


def machinery_cost(s):
    """비상장 감사보고서에서 기계장치 '취득원가'를 칸 단위로 읽는다(2026-11-18).

    상각누계액·장부가액은 쓰지 않는다 — 상각은 원가 배분일 뿐 설비는 처분 전까지 남아, 오래된 공장일수록 장부가액이 작게 읽힘.
    1순위 재무상태표의 '기계장치/감가상각누계액' 짝(일반기업회계기준에 흔함), 2순위 유형자산 주석 표(K-IFRS는 취득원가·상각누계액 공시):
    열·행 두 모양, 두 줄 머리글, 변동표 안 '기계장치 > 취득원가' 줄, '취득원가' 변동표. 전기 표는 건너뛴다. 단위는 표마다.
    취득원가 표에 기계장치 행이 없거나 재무상태표 기계장치가 0이면 0(기계장치 없음). 못 읽으면 None — 추정하지 않는다.
    반환 {'machinery_cost': 원 또는 None, 'ppe_cost_total': 원 또는 None, 'unit', 'evidence'}."""
    from .statements import tables_in, is_prior_table, unit_of, _grid, statement_groups
    try:
        bs = statement_groups(s or "")[0]
    except Exception:
        bs = []
    for i, (lab, cur, _pri) in enumerate(bs):
        if _MACH_LAB.match(lab) and i + 1 < len(bs) and "감가상각누계" in bs[i + 1][0] and cur:
            return {"machinery_cost": cur[0], "ppe_cost_total": None, "unit": 1,
                    "evidence": f"재무상태표 '{lab}' {cur[0]:,}원 · 다음 줄 '{bs[i + 1][0]}' {bs[i + 1][1][0] if bs[i + 1][1] else ''}"}
    secs = _ppe_sections(s or "")
    if not secs:
        return {"machinery_cost": None, "ppe_cost_total": None, "unit": None, "evidence": "유형자산 주석을 찾지 못함"}
    none_hit = None
    for sec in secs:
        for body, ctx in tables_in(sec):
            if is_prior_table(ctx):
                continue
            g = [[t for t, _ in row] for row in _grid(re.findall(r"<TR[^>]*>(.*?)</TR>", body, re.S | re.I))]
            if not g:
                continue
            r = _cost_from_grid(g, ctx)
            if not r:
                continue
            unit = unit_of(ctx)[0]
            v, tot, ev = r
            if v == "없음":
                none_hit = none_hit or {"machinery_cost": 0, "ppe_cost_total": tot * unit if tot is not None else None, "unit": unit, "evidence": ev}
                continue
            return {"machinery_cost": v * unit, "ppe_cost_total": tot * unit if tot is not None else None, "unit": unit, "evidence": ev}
    return none_hit or {"machinery_cost": None, "ppe_cost_total": None, "unit": None, "evidence": "유형자산 표에서 기계장치 취득원가 칸을 찾지 못함"}
