"""공시 재무 숫자 읽기 — OpenDART 단일회사 재무 API 계정 매핑(상장)과 감사보고서 원문 XML 파서(비상장). Claude 작성(2026-11-16).

감사보고서 원문(document.xml, DART 전자공시 마크업):
- 재무제표 묶음 TABLE-GROUP의 ACLASS(PBS 재무상태표·PIS 손익계산서·PCF 현금흐름표), 없으면 표 내용(자산총계·영업손익)으로 찾음
- 머리행 COLSPAN으로 당기/전기 열을 나누고 '주석' 열은 뺌, 단위는 AUNITVALUE 또는 '(단위: 원/천원/백만원)'
- 바꾼 칸 표시: 비용 괄호 표기 → 절대값(검산이 맞을 때만, abs_fixed), 자산총계 없으면 부채총계+자본총계(ta_derived), '영업손실' 행 양수 → 음수
"""
import re

FIELDS = ["revenue", "cogs", "opex", "operating_profit", "total_assets", "inventory", "receivables", "payables"]
IS_FIELDS = {"revenue", "cogs", "opex", "operating_profit"}

IDS = {
    "revenue": ["ifrs-full_Revenue", "ifrs_Revenue"],
    "cogs": ["ifrs-full_CostOfSales", "ifrs_CostOfSales"],
    "opex": ["dart_TotalSellingGeneralAdministrativeExpenses", "ifrs-full_SellingGeneralAndAdministrativeExpense"],
    "operating_profit": ["dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"],
    "total_assets": ["ifrs-full_Assets", "ifrs_Assets"],
    "inventory": ["ifrs-full_Inventories", "ifrs_Inventories", "ifrs-full_CurrentInventoriesHeldForSale"],
    "receivables": ["dart_ShortTermTradeReceivable", "ifrs-full_CurrentTradeReceivables", "ifrs-full_TradeAndOtherCurrentReceivables"],
    "payables": ["dart_ShortTermTradePayables", "ifrs-full_CurrentTradePayables", "ifrs-full_TradeAndOtherCurrentPayables"],
}
NAMES = {
    "revenue": [r"^매출액$", r"^매출$", r"^수익\(매출액\)$", r"^영업수익$", r"^매출및지분법손익$", r"^수익$"],
    "cogs": [r"^매출원가$", r"^영업원가$", r"^매출원가합계$"],
    "opex": [r"^판매비와관리비$", r"^판매비및관리비$", r"^판매비와일반관리비$", r"^판매관리비$", r"^영업비용$"],
    "operating_profit": [r"^영업이익(\(손실\))?$", r"^영업손실$", r"^영업손익$", r"^영업이익\(손실\)$"],
    "total_assets": [r"^자산총계$", r"^자산총액$", r"^자산합계$"],
    "inventory": [r"^재고자산$"],
    "receivables": [r"^매출채권$", r"^매출채권및기타(유동)?채권$", r"^단기매출채권$", r"^매출채권및기타채권$", r"^외상매출금$"],
    "payables": [r"^매입채무$", r"^매입채무및기타(유동)?채무$", r"^단기매입채무$", r"^매입채무및기타채무$", r"^외상매입금$"],
}


def norm(s):
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVXlv0-9]+[\.\)]", "", s)
    s = re.sub(r"^\(\d+\)|^[가-하][\.\)]", "", s)
    s = re.sub(r"\(주[0-9,]+\)|\(주석[0-9,\s]+\)", "", s)
    return s


def amt(v):
    if v is None:
        return None
    v = str(v).replace(",", "").strip()
    neg = v.startswith("(") and v.endswith(")")
    v = v.strip("()")
    if v in ("", "-"):
        return None
    try:
        x = int(float(v))
    except ValueError:
        return None
    return -x if neg else x


# ---------------- 상장: 단일회사 재무 API ----------------
def map_api_items(items, col="thstrm_amount"):
    """fnlttSinglAcntAll list → {필드: (값, 방법)}. 방법: id(표준 태그)|name(계정명)|nature_total|nature_zero|missing."""
    res = {}
    for f in FIELDS:
        pool = [i for i in items if (i.get("sj_div") in ("IS", "CIS")) == (f in IS_FIELDS) and i.get("sj_div") in ("IS", "CIS", "BS")]
        hit = None
        for tag in IDS[f]:
            hit = next(((amt(i.get(col)), "id") for i in pool if i.get("account_id") == tag and amt(i.get(col)) is not None), None)
            if hit:
                break
        if not hit:
            for pat in NAMES[f]:
                if f == "opex" and pat == r"^영업비용$":
                    continue
                hit = next(((amt(i.get(col)), "name") for i in pool if re.match(pat, norm(i.get("account_nm"))) and amt(i.get(col)) is not None), None)
                if hit:
                    break
        res[f] = hit or (None, "missing")
    if res["opex"][1] == "missing":   # 성격별 손익(영업수익−영업비용)
        for i in items:
            if i.get("sj_div") in ("IS", "CIS") and (norm(i.get("account_nm")) == "영업비용" or i.get("account_id") == "dart_OperatingExpenses") and amt(i.get(col)) is not None:
                res["opex"] = (amt(i.get(col)), "nature_total")
                if res["cogs"][1] == "missing" or res["cogs"][0] == res["opex"][0]:
                    res["cogs"] = (0, "nature_zero")
                break
    return res


def api_account(items, account_id=None, name_pat=None, sj=None, col="thstrm_amount"):
    for i in items:
        if sj and i.get("sj_div") != sj:
            continue
        if (account_id and i.get("account_id") == account_id) or (name_pat and re.match(name_pat, norm(i.get("account_nm")))):
            v = amt(i.get(col))
            if v is not None:
                return v
    return None


# ---------------- 감사보고서 원문 XML ----------------
NUM = re.compile(r"^\(?-?\d{1,3}(,\d{3})*\)?$|^\(?-?\d+\)?$")


def txt(x):
    return re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").replace("&amp;", "&").strip()


def num(x):
    x = x.replace(" ", "")
    if x in ("-", "－", "—"):
        return 0
    if not NUM.match(x):
        return None
    return amt(x)


def norm2(x):
    x = re.sub(r"\s+", "", x or "")
    x = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVXlv0-9]+[\.\)]", "", x)
    return norm(x)


def _span(attr):
    m = re.search(r'COLSPAN="(\d+)"', attr)
    return int(m.group(1)) if m else 1


def unit_of(g):
    mu = re.search(r'AUNITVALUE="(\d+)"', g)
    if mu:
        return int(mu.group(1)), "AUNITVALUE"
    mt = re.search(r"단\s*위\s*[:：]\s*(천\s*원|백\s*만\s*원|원)", txt(g))
    if mt:
        return {"원": 1, "천원": 1000, "백만원": 1000000}[re.sub(r"\s", "", mt.group(1))], "text"
    return 1, "없음(원 가정)"


def parse_group(g):
    """표 묶음 → ([(라벨, 당기 값들, 전기 값들)], 단위, 단위 출처)."""
    unit, usrc = unit_of(g)
    fin = re.search(r'<TABLE[^>]*ACLASS="FINANCE"[^>]*>(.*?)</TABLE>', g, re.S)
    body = fin.group(1) if fin else g
    cur_cols = pri_cols = None
    th = re.search(r"<THEAD>(.*?)</THEAD>", body, re.S)
    if th:
        ths = re.findall(r"<TH([^>]*)>(.*?)</TH>", th.group(1), re.S)
        if len(ths) >= 3:
            pos, spans = 0, []
            for attr, b in ths[1:]:
                k = _span(attr)
                if not re.sub(r"\s", "", txt(b)).startswith("주석"):
                    spans.append(range(pos, pos + k))
                pos += k
            if len(spans) >= 2:
                cur_cols, pri_cols = spans[0], spans[1]
    note_pos = None
    if cur_cols is None:
        for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", body, re.S):
            cs = re.findall(r"<(TH|TD|TE)([^>]*)>(.*?)</\1>", tr, re.S)
            pos = 0
            for _, attr, b in cs[1:]:
                if re.sub(r"\s", "", txt(b)) == "주석":
                    note_pos = pos
                pos += _span(attr)
            if note_pos is not None:
                break
    rows = []
    for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", body, re.S):
        cells = re.findall(r"<(TE|TD)([^>]*)>(.*?)</\1>", tr, re.S)
        if len(cells) < 2:
            continue
        label = norm2(txt(cells[0][2]))
        vals, pos = [], 0
        for _, attr, b in cells[1:]:
            k = _span(attr)
            vals.append((pos, num(txt(b))))
            pos += k
        n = pos
        if cur_cols is None and note_pos is not None:
            vals = [(p - (1 if p > note_pos else 0), v) for p, v in vals if p != note_pos]
            n -= 1
        cc = cur_cols or range(0, max(1, n // 2))
        pc = pri_cols or range(max(1, n // 2), n)
        cur = [v for p, v in vals if p in cc and v is not None]
        pri = [v for p, v in vals if p in pc and v is not None]
        rows.append((label, [x * unit for x in cur], [x * unit for x in pri]))
    return rows, unit, usrc


def statement_groups(s):
    """원문 → (재무상태표 행, 손익계산서 행, 현금흐름표 행, info)."""
    bs = is_ = cf = None
    info = {}
    for attr, g in re.findall(r'<TABLE-GROUP([^>]*)>(.*?)</TABLE-GROUP>', s, re.S):
        acl = (re.search(r'ACLASS="([^"]*)"', attr) or [None, ""])[1]
        t = norm(txt((re.search(r"<TITLE[^>]*>(.*?)</TITLE>", g, re.S) or [None, ""])[1]))
        if bs is None and (acl.startswith(("PBS", "CBS")) or "재무상태표" in t or "대차대조표" in t):
            bs = parse_group(g)
        elif is_ is None and (acl.startswith(("PIS", "CIS")) or "손익계산서" in t):
            is_ = parse_group(g)
        elif cf is None and acl.startswith(("PCF", "CCF")):
            cf = parse_group(g)
    if bs is None or is_ is None:
        info["fallback"] = True
        for m in re.finditer(r"<TABLE([^>]*)>(.*?)</TABLE>", s, re.S):
            t = re.sub(r"\s", "", txt(m.group(2)))
            ctx = s[max(0, m.start() - 2500):m.start()] + m.group(0)
            if bs is None and re.search(r"자산총계|자산합계", t):
                bs = parse_group(ctx)
            elif is_ is None and re.search(r"영업(이익|손실|손익)", t) and re.search(r"매출|영업수익", t) and not re.search(r"자산총계", t):
                is_ = parse_group(ctx)
    info["unit_src"] = (bs or is_ or (None, None, ""))[2]
    info["consolidated"] = bool(re.search(r'ACLASS="C(BS|IS)', s)) or "(첨부)연결재무제표" in re.sub(r"\s", "", txt(s[:60000]))
    fy = re.search(r"(\d{4})년\s*12월\s*31일", s)
    info["year"] = int(fy.group(1)) if fy else None
    return (bs or [[]])[0] if bs else [], (is_ or [[]])[0] if is_ else [], (cf or [[]])[0] if cf else [], info


def _pick(rows, pats, which):
    for pat in pats:
        for i, (k, c, p) in enumerate(rows):
            arr = c if which == 0 else p
            if re.match(pat, k) and arr:
                return arr[-1], i
    return None, None


def _recv_net(rows, which):
    v, i = _pick(rows, NAMES["receivables"], which)
    if v is None:
        return None, ""
    if i + 1 < len(rows) and rows[i + 1][0].startswith("대손충당금"):
        arr = rows[i + 1][1 if which == 0 else 2]
        if len(arr) >= 2:
            return arr[-1], "총액표시→순액(합계열)"
        if len(arr) == 1:
            return v - abs(arr[0]), "총액표시→순액(차감계산)"
    return v, "단일값"


def audit_financials(s):
    """감사보고서 원문 → {'cur': {필드: 값}, 'prior': {...}, 'info': {...}, 'bs': 행, 'is': 행, 'cf': 행}."""
    bs, is_, cf, info = statement_groups(s)
    cur, pri = {}, {}
    for which, out in ((0, cur), (1, pri)):
        for f in FIELDS:
            if f == "receivables":
                out[f], basis = _recv_net(bs, which)
                if which == 0:
                    info["recv_basis"] = basis
                continue
            v, i = _pick(is_ if f in IS_FIELDS else bs, NAMES[f], which)
            if f == "operating_profit" and v is not None and v > 0 and is_[i][0] == "영업손실":
                v = -v
                info["op_sign_fixed"] = True
            out[f] = v
        ve, _ = _pick(is_, [r"^영업비용$"], which)
        if out["cogs"] is None and ve is not None and out["opex"] == ve:
            out["cogs"] = 0
        # 비용 괄호 표기 → 절대값(검산이 맞을 때만)
        r, c, o, op = out["revenue"], out["cogs"], out["opex"], out["operating_profit"]
        if None not in (r, c, o, op) and (c < 0 or o < 0):
            tol = 0.005 * max(1, abs(r))
            if abs(r - abs(c) - abs(o) - op) <= tol < abs(r - c - o - op):
                out["cogs"], out["opex"] = abs(c), abs(o)
                if which == 0:
                    info["abs_fixed"] = True
        if out["total_assets"] is None:
            L, _ = _pick(bs, [r"^부채총계$", r"^부채합계$"], which)
            E, _ = _pick(bs, [r"^자본총계$", r"^자본합계$"], which)
            if L is not None and E is not None:
                out["total_assets"] = L + E
                if which == 0:
                    info["ta_derived"] = True
    return {"cur": cur, "prior": pri, "info": info, "bs": bs, "is": is_, "cf": cf}


def row_value(rows, pat, which=0):
    v, _ = _pick(rows, [pat], which)
    return v


# ---------------- 원문 절·표 ----------------
def title_sections(s):
    ts = [(m.start(), txt(m.group(1))) for m in re.finditer(r"<TITLE[^>]*>(.*?)</TITLE>", s, re.S)]
    return [(a, (ts[i + 1][0] if i + 1 < len(ts) else len(s)), t) for i, (a, t) in enumerate(ts)]


def find_section(s, kw_pat, is_bizrep):
    """사업보고서: 표준 주석 제목(별도 우선). 감사보고서: 번호 붙은 제목 '12. 특수관계자'."""
    if is_bizrep:
        secs = [x for x in title_sections(s) if re.search(kw_pat, x[2])]
        for pref in ("별도", "연결", ""):
            for a, b, t in secs:
                if pref in t and "주석" in t:
                    return s[a:b], t
        for a, b, t in title_sections(s):
            if re.search(r"^\s*\d+\.\s*재무제표\s*주석", t):
                sub, tt = find_section(s[a:b], kw_pat, False)
                if sub:
                    return sub, "재무제표 주석>" + tt
        return "", ""
    for m in re.finditer(r">\s*(\d{1,2})\s*\.\s*(?:<[^>]+>\s*)*([^<]{0,40})", s):
        if re.search(kw_pat, m.group(2)) and len(m.group(2).strip()) < 40:
            n = int(m.group(1))
            nxt = re.search(r">\s*%d\s*\.\s*[가-힣]" % (n + 1), s[m.end():m.end() + 120000])
            end = m.end() + (nxt.start() if nxt else 40000)
            return s[m.start():end], m.group(2).strip()
    return "", ""


def tables_in(sec):
    return [(m.group(2), sec[max(0, m.start() - 1500):m.start()] + m.group(0)) for m in re.finditer(r"<TABLE([^>]*)>(.*?)</TABLE>", sec, re.S)]


INV = {"원재료": r"^(원재료|원자재|부재료)", "재공품": r"^(재공품|반제품)", "제품": r"^제품$", "상품": r"^(상품|미착상품)$", "저장품": r"^저장품"}


def inventory_items(rows):
    got = set()
    for lab, cur, pri in rows:
        for k, pat in INV.items():
            if re.match(pat, lab) and any(v for v in cur):
                got.add(k)
    return got


def related_sales(s, is_bizrep, revenue):
    """특수관계자 거래 주석의 매출 합계 ÷ 매출 → (비율, 근거)."""
    sec, t = find_section(s, r"특수\s*관계", is_bizrep)
    if not sec:
        return None, "특수관계자 절 못 찾음"
    plain = re.sub(r"\s", "", txt(sec))
    for tb, ctx in tables_in(sec):
        trs = re.findall(r"<TR[^>]*>(.*?)</TR>", tb, re.S)
        if len(trs) < 2:
            continue
        col = None
        for tr in trs[:3]:
            pos = 0
            for tag, attr, b in re.findall(r"<(TH|TD|TE)([^>]*)>(.*?)</\1>", tr, re.S):
                x = re.sub(r"\s", "", txt(b))
                if col is None and re.match(r"^(매출|수익|매출등|매출액|영업수익|수익거래|재화의판매|매출거래)", x) and "원가" not in x:
                    col = pos
                pos += _span(attr)
            if col is not None:
                break
        if col is None:
            continue
        unit = parse_group(ctx)[1]
        total, rows_sum = None, 0
        for tr in trs:
            cells = re.findall(r"<(TH|TD|TE)([^>]*)>(.*?)</\1>", tr, re.S)
            if not cells or cells[0][0] == "TH":
                continue
            pos, val = 0, None
            for tag, attr, b in cells:
                if pos == col:
                    val = num(txt(b))
                pos += _span(attr)
            lab = re.sub(r"\s", "", txt(cells[0][2]))
            if val is None:
                continue
            if lab in ("합계", "계", "총계"):
                total = val
            else:
                rows_sum += val
        a = (total if total is not None else rows_sum) * unit
        if revenue and revenue > 0:
            r = a / revenue
            if 0 <= r <= 1.05:
                return r, "특수관계자 주석 표: " + t[:30]
            return None, f"비율 범위 밖({r:.2f}) — 단위·열 확인 필요"
        return None, "매출 없음"
    if re.search(r"거래(내역)?(은|는|이|가)?없", plain):
        return 0.0, "특수관계자 거래 없음 문장"
    return None, "매출 열 못 찾음"
