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
    for m in re.finditer(r">\s*(\d{1,2})\s*\.\s*(?:<[^>]+>\s*)*([^<]{0,80})", s):
        title = _heading_title(m.group(2))
        if title and not title[0].isdigit() and re.search(kw_pat, title) and len(title) < 40:
            n = int(m.group(1))
            nxt = re.search(r">\s*%d\s*\.\s*[가-힣]" % (n + 1), s[m.end():m.end() + 120000])
            end = m.end() + (nxt.start() if nxt else 40000)
            return s[m.start():end], title
    return "", ""


# 감사보고서 주석 제목 뒤에 본문이 태그 없이 붙는 원문이 많음('특수관계자와의 거래27-1. 당기말…', '특수관계자(1) 당기말…',
# '특수관계자 공시22.1 지배…') — 하위 번호·괄호 번호·두 칸 공백 앞에서 끊은 것을 제목으로 봄
_HEAD_CUT = re.compile(r"\d{1,2}\s*[.\-]\s*\d|\(\s*\d{1,2}\s*\)|\d{1,2}\)|[①-⑳]|\s{2,}")


def _heading_title(raw):
    t = raw.strip()
    m = _HEAD_CUT.search(t)
    return (t[:m.start()] if m else t).strip()


_PRIOR_TABLE = re.compile(r"[<(\[①-⑳\d.\s가-하]*전\s*기\s*말?\s*[>)\]]?\s*[:：]?\s*(\(?단위[^)]*\)?)?\s*$")


def is_prior_table(ctx):
    """표 바로 앞 글이 '전기'·'(전기)'·'② 전기'·'<전기>'(+단위 표기)로 끝나면 전기 표 — 당기 표에 그 열이 없을 때 전기 표 값을 대신 읽지 않게."""
    i = ctx.rfind("<TABLE")
    pre = re.sub(r"\s+", " ", txt(ctx[:i] if i >= 0 else ctx)).strip()[-40:]
    return bool(_PRIOR_TABLE.search(pre)) and not re.search(r"당\s*기[^전]*$", pre)


def tables_in(sec):
    return [(m.group(2), sec[max(0, m.start() - 1500):m.start()] + m.group(0)) for m in re.finditer(r"<TABLE([^>]*)>(.*?)</TABLE>", sec, re.S)]


INV = {"원재료": r"^(유동)?(원재료|원자재|부재료)", "재공품": r"^(유동)?(재공품|반제품)", "제품": r"^(유동)?제품(\(\*\))?$",
       "상품": r"^(유동)?(상품|미착상품)(\(\*\))?$", "저장품": r"^(유동)?저장품"}


def inventory_items(rows):
    got = set()
    for lab, cur, pri in rows:
        for k, pat in INV.items():
            if re.match(pat, lab) and any(v for v in cur):
                got.add(k)
    return got



# ---------------- 특수관계자 거래 표: 가로형(회사 × 매출·매입 열)·세로형(거래 종류 행 × 당기·전기 열) ----------------
_CELL = r"<(TH|TD|TE)([^>]*)>(.*?)</\1>"


def _is_header_row(tr):
    """머리글 행 = 금액 칸이 없는 행. 첫 데이터 행의 '상품매입' 같은 글자를 열 제목으로 잘못 잡지 않게."""
    cells = re.findall(_CELL, tr, re.S)
    return bool(cells) and all(num(txt(b)) is None for _, _, b in cells)


def _header_col(trs, pat):
    for tr in [t for t in trs[:3] if _is_header_row(t)]:
        pos = 0
        for tag, attr, b in re.findall(_CELL, tr, re.S):
            if re.match(pat, re.sub(r"\s", "", txt(b))):
                return pos
            pos += _span(attr)
    return None


def _grid(trs):
    """표의 행들을 병합(ROWSPAN·COLSPAN)을 풀어 격자로 — 행마다 [(글자, 내려온 칸인지)]. 머리글이 여러 줄이거나 앞 칸이 세로로 병합된 표에서
    칸 위치가 밀리지 않게 한다(종전: 둘째 머리글 줄의 '매출등'을 0번 열로 봐 회사 이름 열을 더하고 0%를 냄)."""
    rows, carry = [], {}
    for tr in trs:
        pending, row, col = list(re.findall(_CELL, tr, re.S)), [], 0
        while pending or any(c >= col for c in carry):
            if col in carry:
                rem, text = carry[col]
                row.append((text, True))
                if rem > 1:
                    carry[col] = (rem - 1, text)
                else:
                    del carry[col]
                col += 1
                continue
            if not pending:
                row.append(("", True))
                col += 1
                continue
            tag, attr, b = pending.pop(0)
            text = re.sub(r"\s", "", txt(b))
            m = re.search(r'ROWSPAN="(\d+)"', attr)
            rs = int(m.group(1)) if m else 1
            for k in range(_span(attr)):
                row.append((text, False))
                if rs > 1:
                    carry[col + k] = (rs - 1, text)
            col += _span(attr)
        rows.append(row)
    width = max((len(r) for r in rows), default=0)
    # 병합 표시(ROWSPAN) 없이 앞 칸이 빠진 행(예: 둘째 행부터 '구분' 칸이 없음, 둘째 머리글 줄에 '당기|전기'만 있음)은 오른쪽에 맞춘다 — 금액 칸은 오른쪽 끝에 있음
    return [[("", True)] * (width - len(r)) + r if 1 < len(r) < width else r for r in rows]


REL_HDR_EXCL = r"채권|채무|외상|대여|차입|미수|미지급|선수|선급|보증|잔액|원가|유형|무형|(?<!재고)자산|주식|지분|투자|취득|처분|매각|할인|에누리"
_TOTAL_LAB = ("합계", "계", "총계", "총합계")


_CUR = r"당기(\([^)]*\))?(금액)?"


def _wide_sum(trs, hdr_pat):
    """가로형 표(회사가 행, 거래 종류가 열): 머리글 줄들을 격자로 풀어 열마다 제목 경로(위→아래)를 만들고, 맨 아래 제목이 hdr_pat에 맞는 열을
    (당기·전기가 함께 있으면 당기 쪽만) 더한다. 반환 (금액 또는 None, 설명). 열을 못 찾거나 그 열에서 금액을 하나도 못 읽으면 None —
    0으로 내지 않는다. 합계 행이 있으면 합계를 쓰고 행을 더한 값과 다르면 설명에 적는다."""
    n_hdr = 0
    for t in trs[:5]:
        if not _is_header_row(t):
            break
        n_hdr += 1
    if not n_hdr:
        return None, ""
    g = _grid(trs)
    width = max(len(r) for r in g)
    paths = []
    for c in range(width):
        path = []
        for r in g[:n_hdr]:
            x = r[c][0] if c < len(r) else ""
            if x and (not path or path[-1] != x):
                path.append(x)
        paths.append(path)

    def ok(c):
        path = paths[c]
        return bool(path) and re.search(hdr_pat, path[-1]) and not any(re.search(REL_HDR_EXCL, x) for x in path)
    cols = [c for c in range(width) if ok(c)]
    if not cols:      # 맨 아래 제목이 아니라 윗줄 제목이 맞는 경우(예: '매출' 아래 '상품'·'용역')
        cols = [c for c in range(width) if paths[c] and any(re.search(hdr_pat, x) for x in paths[c][:-1])
                and not any(re.search(REL_HDR_EXCL, x) for x in paths[c]) and not re.match(r"^(기타|이자|배당|임대|수수료)", paths[c][-1])]
    if not cols:
        return None, ""
    if any(any(re.fullmatch(_CUR, x) for x in paths[c]) for c in cols):
        cols = [c for c in cols if any(re.fullmatch(_CUR, x) for x in paths[c])]
    elif all(any(re.match(r"^전기", x) for x in paths[c]) for c in cols):
        return None, ""      # 전기만 있는 표
    total, rows_sum, read, totals, cur_mark = None, 0, 0, 0, False
    for r in g[n_hdr:]:
        labs = [x for x, _ in r[:3]]
        if any(re.fullmatch(r"[<(\[]?당기[>)\]]?", x) for x, _ in r):
            cur_mark = True
        vals = [num(r[c][0]) for c in cols if c < len(r) and not r[c][1] and r[c][0] != ""]
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        if any(x in _TOTAL_LAB for x in labs):
            totals += 1
            if totals == 1:
                total = sum(vals)
        elif totals or any(re.search(r"소계$", x) for x in labs):
            continue                 # 첫 합계 행 뒤(한 표에 당기·전기 묶음이 위아래로 있는 경우의 둘째 묶음)와 소계 행은 더하지 않음
        else:
            rows_sum += sum(vals)
            read += 1
    if total is None and not read:
        return None, ""
    names = "+".join(dict.fromkeys(paths[c][-1] for c in cols))
    if totals > 1 and not cur_mark:
        return None, "합계 행이 둘 이상(당기·전기 묶음 구분 없음) — 사람 확인"
    if total is not None and read and abs(total - rows_sum) > 1:
        return None, f"열 {names}: 행을 더한 값({rows_sum:,.0f})과 합계 행({total:,.0f})이 다름 — 사람 확인"
    return (total if total is not None else rows_sum), f"열 {names}" + (", 합계 행과 일치" if total is not None and read else "")


def _long_sum(trs, row_pat, excl_pat):
    """세로형 표: 머리글에 '당기' 열(또는 맨 오른쪽 '계' 열)이 있고, 거래 종류(예: 상품매입)가 행으로 내려옴. 병합을 푼 격자에서 거래 종류 이름이
    row_pat에 맞는 행의 당기 칸을 더함 — 거래 종류 칸이 세로로 병합돼 둘째 행부터 비어 있어도(과목 | 구분 | 당기) 읽고,
    합계·소계 행은 더하지 않는다(종전: '합계 | 매출등' 행까지 더해 두 배). 해당 행이 없으면 None."""
    n_hdr = 0
    for t in trs[:5]:
        if not _is_header_row(t):
            break
        n_hdr += 1
    if not n_hdr:
        return None
    g = _grid(trs)
    width = max(len(r) for r in g)
    paths = [[r[c][0] for r in g[:n_hdr] if c < len(r) and r[c][0]] for c in range(width)]
    cur = next((c for c in range(width) if any(re.fullmatch(_CUR, x) for x in paths[c])), None)
    if cur is None:
        if not (paths and paths[-1] and re.fullmatch(r"(계|합계|총계)", paths[-1][-1])):
            return None
        cur = width - 1      # 거래 종류 행 × 회사별 열 + 맨 오른쪽 '계' 열
    total, found = 0, False
    for r in g[n_hdr:]:
        if cur >= len(r) or r[cur][1]:
            continue
        labs = [x for x, _ in r[:cur] if x and num(x) is None]
        if any(x in _TOTAL_LAB or re.search(r"소계$", x) for x in labs):
            continue
        # '상품매출/매출채권등'처럼 거래와 잔액 이름을 빗금으로 묶은 칸은 빗금 앞(거래 이름)만 본다
        if not any(re.search(row_pat, x.split("/")[0]) and not re.search(excl_pat, x.split("/")[0]) for x in labs):
            continue
        v = num(r[cur][0])
        if v is not None:
            total += v
            found = True
    return total if found else None


def _rel_unit(ctx):
    """특수관계자 표 단위 — 표 안 AUNITVALUE, 없으면 표 바로 앞에서 가장 가까운 '단위:' 표기(앞 표의 단위를 가져오지 않게)."""
    i = ctx.rfind("<TABLE")      # 맥락 안의 마지막 표가 이 표(앞 표가 맥락에 들어와도)
    head, table = (ctx[:i], ctx[i:]) if i >= 0 else (ctx, "")
    mu = re.search(r'AUNITVALUE="(\d+)"', table)
    if mu:
        return int(mu.group(1))
    ms = re.findall(r"단\s*위\s*[:：]\s*(천\s*원|백\s*만\s*원|원)", txt(head))
    return {"원": 1, "천원": 1000, "백만원": 1000000}[re.sub(r"\s", "", ms[-1])] if ms else unit_of(ctx)[0]


def _unit_mismatch(sec, unit):
    """같은 특수관계자 절 안에서 금액 표의 단위 표기가 갈리면(예: 거래 표 '원', 채권·채무 표 '천원') 그 표 단위가 다수와 다른지.
    원문 단위 표기가 틀린 경우가 있어(실제 사례: 거래 표 '(단위 : 원)'인데 같은 상대 채권이 천원 표에서 43억) 숫자를 내지 않고 사람 확인."""
    units = [_rel_unit(c) for tb, c in tables_in(sec) if re.search(r"\d{1,3}(,\d{3})+", txt(tb))]
    if len(set(units)) < 2:
        return False
    major = max(set(units), key=units.count)
    return unit != major


SALES_HDR = r"매출|^영업수익|^수익(거래)?$|재화의판매|용역의제공"
SALES_ROW = r"매출|^영업수익|^수익$|재화의판매|용역의제공|용역제공"
PURCHASE_ROW = r"매입"
REL_EXCL = r"(원가|채권|채무|외상|미수|미지급|선수|선급|유형|무형|(?<!재고)자산|주식|지분|투자|취득|처분|매각|할인|에누리)"
# '특수관계자와의 거래 없음' 문장 — '자금거래·담보·보증 내역은 없습니다' 같은 다른 거래 문장에 걸리지 않게 '특수관계자(와의) 거래'로 한정
NO_REL_TX = re.compile(r"특수관계자(와|와의|와의주요|간)?(매출·?매입)?거래(내역|내용)?(은|는|이|가)?(없|존재하지않)")

def related_sales(s, is_bizrep, revenue):
    """특수관계자 거래 주석의 매출 합계 ÷ 매출 → (비율, 근거)."""
    sec, t = find_section(s, r"특수\s*관계", is_bizrep)
    if not sec:
        return None, "특수관계자 절 못 찾음"
    plain = re.sub(r"\s", "", txt(sec))
    for tb, ctx in tables_in(sec):
        if is_prior_table(ctx):
            continue
        trs = re.findall(r"<TR[^>]*>(.*?)</TR>", tb, re.S)
        if len(trs) < 2:
            continue
        wv, winfo = _wide_sum(trs, SALES_HDR)
        if wv is None and winfo:
            return None, winfo
        if wv is None:
            lv = _long_sum(trs, SALES_ROW, REL_EXCL)
            if lv is None:
                continue
            if _unit_mismatch(sec, _rel_unit(ctx)):
                return None, "주석 표마다 단위 표기가 다름(원·천원 등) — 사람 확인"
            a = lv * _rel_unit(ctx)
            if revenue and revenue > 0:
                r = a / revenue
                if 0 <= r <= 1.05:
                    return r, "특수관계자 주석 표(거래 종류 행, 당기): " + t[:30]
                return None, f"비율 범위 밖({r:.2f}) — 단위·열 확인 필요"
            return None, "매출 없음"
        unit = _rel_unit(ctx)
        if _unit_mismatch(sec, unit):
            return None, "주석 표마다 단위 표기가 다름(원·천원 등) — 사람 확인"
        a = wv * unit
        if revenue and revenue > 0:
            r = a / revenue
            if 0 <= r <= 1.05:
                return r, f"특수관계자 주석 표({winfo}): " + t[:30]
            return None, f"비율 범위 밖({r:.2f}) — 단위·열 확인 필요"
        return None, "매출 없음"
    if NO_REL_TX.search(plain):
        return 0.0, "특수관계자 거래 없음 문장"
    return None, "매출 열 못 찾음"


# ---------------- 제품·상품 회계 신호 ----------------
COGS_PAT = {"merch": r"^(상품매출원가|상품원가|상품판매원가|상품매출원가합계)$", "product": r"^(제품매출원가|제품원가|제품판매원가|제품매출원가합계)$",
            "service": r"^(용역매출원가|용역원가|공사원가|공사매출원가|서비스원가|서비스매출원가|임대원가|운송원가)$"}
INV_MERCH = r"^(유동)?(상품|미착상품)(\(\*\))?$"
INV_PROD = r"^(유동)?(제품|재공품|반제품|원재료|부재료|원자재|미착원재료)(\(\*\))?$"


def _first(rows, pat):
    for lab, c, p in rows:
        if re.match(pat, lab) and c and "충당금" not in lab:
            return c[0], lab
    return None, ""


def goods_signals(cogs_rows, inv_rows, cogs_total=None, rcept_no=None):
    """매출원가 내역(상품·제품·용역)과 재고 구성(상품 / 제품·재공품·원재료)으로 재화 매출의 상품 비율 m을 정한다.
    반환 {'merch_ratio': m|None, 'source', 'values', 'goods_cost_share': (상품+제품 원가)/매출원가|None, 'rcept_no'}."""
    cm, lm = _first(cogs_rows, COGS_PAT["merch"])
    cp, lp = _first(cogs_rows, COGS_PAT["product"])
    cs, ls = _first(cogs_rows, COGS_PAT["service"])
    out = {"merch_ratio": None, "source": "", "values": {}, "goods_cost_share": None, "rcept_no": rcept_no}
    if (cm or 0) > 0 or (cp or 0) > 0:
        a, b = max(cm or 0, 0), max(cp or 0, 0)
        out.update(merch_ratio=a / (a + b), source="매출원가 상품:제품", values={lm or "상품매출원가": cm, lp or "제품매출원가": cp, **({ls: cs} if cs is not None else {})})
        base = cogs_total if cogs_total else (a + b + max(cs or 0, 0) if cs is not None else None)
        if base:
            out["goods_cost_share"] = min(1.0, (a + b) / base)
        return out
    first = {}
    for lab, c, p in inv_rows:                     # 같은 표가 당기·전기로 되풀이되므로 라벨마다 처음 값만
        if c and "충당금" not in lab and lab not in first:
            first[lab] = c[0]
    im = sum(max(v, 0) for lab, v in first.items() if re.match(INV_MERCH, lab))
    ip = sum(max(v, 0) for lab, v in first.items() if re.match(INV_PROD, lab))
    if im + ip > 0:
        out.update(merch_ratio=im / (im + ip), source="재고 상품:제품·재공품·원재료", values={"상품 재고": im, "제품·재공품·원재료 재고": ip})
    if cs is not None and cogs_total and cs >= 0:
        out["goods_cost_share"] = max(0.0, 1 - cs / cogs_total) if out["merch_ratio"] is not None else None
    return out


# ---------------- 실질 지배 신호(특수관계자 주석) ----------------
PURCHASE_HDR = r"매입"
# 재고(상품·제품·원재료) 매입 열·행 — '기타매입'(사용료·용역·광고비 등 재고 아닌 매입)은 매출원가와 짝이 맞지 않아 먼저 뺀다
GOODS_ITEM = r"(재고자산|재고|상품|제품|원재료|원부재료|원자재|부재료)"
GOODS_PURCHASE_HDR = rf"^({GOODS_ITEM}(및|·|,|/)?)*\s*매입(액|거래)?(\(\*\d*\))?$"
GOODS_PURCHASE_EXCL = REL_EXCL[:-1] + r"|^기타|비용|용역|수수료|사용료|로열티)"
OVER_COGS_NOTE = "매입이 매출원가보다 큼 — 재고가 늘었거나 재고 아닌 매입이 섞였을 수 있음, 원문 확인"


def _purchase_ratio(r, why, bl):
    """매입 ÷ 매출원가가 100%를 넘으면 숫자는 두되 근거에 주의를 붙인다(관계사에서 거의 다 사는 회사는 재고 증가만으로도 넘음).
    150% 넘으면 단위·열 오독으로 보고 숫자를 내지 않는다."""
    if r < 0 or r > 1.5:
        return None, f"비율 범위 밖({r:.2f}) — 단위·열 확인 필요"
    return r, why + (f" — {OVER_COGS_NOTE}({r:.0%})" if r > 1 and bl == "매출원가" else "")


def related_purchases(s, is_bizrep, cogs=None, revenue=None):
    """특수관계자 거래 주석 표의 매입 합계 ÷ 매출원가(없으면 매출) → (비율, 근거).
    재고 매입 열·행(상품·원재료 매입 등)이 있으면 그것만, 없으면 '매입'이 붙은 열·행 전부(근거에 표시)."""
    sec, t = find_section(s, r"특수\s*관계", is_bizrep)
    if not sec:
        return None, "특수관계자 절 못 찾음"
    base, bl = (cogs, "매출원가") if cogs else (revenue, "매출")
    if not base or base <= 0:
        return None, "매출원가·매출 없음"
    for tb, ctx in tables_in(sec):
        if is_prior_table(ctx):
            continue
        trs = re.findall(r"<TR[^>]*>(.*?)</TR>", tb, re.S)
        wv, winfo = _wide_sum(trs, GOODS_PURCHASE_HDR)
        if wv is None and not winfo:
            wv, winfo = _wide_sum(trs, PURCHASE_HDR)
        cols = re.match(r"열 ([^,]+)", winfo or "")
        kind = "재고 매입" if cols and all(re.fullmatch(GOODS_PURCHASE_HDR, c) for c in cols.group(1).split("+")) else "매입(재고 외 포함 가능)"
        if wv is None and winfo:
            return None, winfo
        if wv is None:
            lv, kind = _long_sum(trs, PURCHASE_ROW, GOODS_PURCHASE_EXCL), "매입(기타 매입 행 제외)"
            if lv is None:
                lv, kind = _long_sum(trs, PURCHASE_ROW, REL_EXCL), "매입(재고 외 포함 가능)"
            if lv is None:
                continue
            if _unit_mismatch(sec, _rel_unit(ctx)):
                return None, "주석 표마다 단위 표기가 다름(원·천원 등) — 사람 확인"
            return _purchase_ratio(lv * _rel_unit(ctx) / base, f"특수관계자 주석 표(거래 종류 행, 당기) {kind} ÷ {bl}: " + t[:30], bl)
        unit = _rel_unit(ctx)
        if _unit_mismatch(sec, unit):
            return None, "주석 표마다 단위 표기가 다름(원·천원 등) — 사람 확인"
        return _purchase_ratio(wv * unit / base, f"특수관계자 주석 표({winfo}) {kind} ÷ {bl}: " + t[:30], bl)
    if NO_REL_TX.search(re.sub(r"\s", "", txt(sec))):
        return 0.0, "특수관계자 거래 없음 문장"
    return None, "매입 열 못 찾음"


CONTROL_KW = [("임원 겸직", r"겸직|겸임"), ("지배기업", r"지배기업|최상위\s*지배|모회사"), ("유의적 영향력", r"유의적인?\s*영향력"),
              ("자금 대여·보증", r"자금\s*(대여|차입|거래)|대여금|차입금|지급보증|담보\s*제공"),
              ("기업집단 계열", r"기업집단|계열회사|상호출자제한"), ("지식재산 사용료", r"사용료|로열티|기술료|상표권\s*사용")]


def control_signals(s, is_bizrep):
    """특수관계자 주석에서 실질 지배 신호 문장 — 참고용, 법정 특수관계 판정 아님(판단은 조문 MCP). 반환 (신호 목록 [{kind, sentence}], 절 제목) — 절을 못 찾으면 (None, 사유)."""
    sec, t = find_section(s, r"특수\s*관계", is_bizrep)
    if not sec:
        return None, "특수관계자 절 못 찾음"
    text = re.sub(r"\s+", " ", txt(re.sub(r"<TR[^>]*>", " . ", sec)))
    sents = [x.strip() for x in re.split(r"(?<=[다음함])\.\s*|\s\.\s", text) if 10 <= len(x.strip()) <= 400]
    out = []
    for kind, pat in CONTROL_KW:
        hits = [x for x in sents if re.search(pat, x)][:3]
        out += [{"kind": kind, "sentence": x[:200]} for x in hits]
    return out, t


# ---------------- 비상장 최대주주·지배기업 지분율(감사보고서 주석) ----------------
OWNER_SUBJ = (r"(지배기업|최상위\s*지배|모회사|최대주주|주요\s*주주|주주\s*현황|주식을\s*(소유|보유)|지분을\s*(소유|보유)"
              r"|지분\s*\d{1,3}(\.\d+)?\s*%\s*(를|을)?\s*(소유|보유)|%\s*(의)?\s*(지분|주식)\s*(을|를)?\s*(소유|보유))")


def owner_share(s):
    """감사보고서 주석(일반사항·주주 현황·특수관계자)에서 최대주주·지배기업 지분율 → (지분율 %, 근거 문장·행).
    표('주주명 | 주식수 | 지분율')가 있으면 가장 큰 지분율 행, 없으면 지배기업·최대주주 문장의 % 값. 못 찾으면 (None, 사유)."""
    i = s.find("주석")
    body = s[i:] if i >= 0 else s
    best = None
    for tb, ctx in tables_in(body[:200000]):
        trs = re.findall(r"<TR[^>]*>(.*?)</TR>", tb, re.S)
        if len(trs) < 2:
            continue
        head = re.sub(r"\s", "", txt(" ".join(trs[:2])))
        if not re.search(r"(지분율|소유비율|지분비율|소유지분율|지분\(%\))", head) or not re.search(r"(주주|성명|회사명|주주명|주식수|구분)", head):
            continue
        pre = re.sub(r"\s", "", txt(ctx[:ctx.rfind("<TABLE")]))[-200:]
        if re.search(r"(종속|관계|공동)기업|투자|매도가능|피투자|장부금액|취득원가|분할|신설", head + pre):
            continue                                   # 투자한 회사 지분표는 제외
        col = None
        for tr in trs[:2]:
            pos = 0
            for tag, attr, b in re.findall(r"<(TH|TD|TE)([^>]*)>(.*?)</\1>", tr, re.S):
                if col is None and re.search(r"(지분율|소유비율|지분비율)", re.sub(r"\s", "", txt(b))):
                    col = pos
                pos += _span(attr)
        for tr in trs:
            cells = re.findall(r"<(TH|TD|TE)([^>]*)>(.*?)</\1>", tr, re.S)
            if not cells or col is None:
                continue
            pos, val = 0, None
            for tag, attr, b in cells:
                if pos == col:
                    m = re.fullmatch(r"\(?(\d{1,3}(?:\.\d+)?)\s*%?\)?", re.sub(r"\s", "", txt(b)))
                    val = float(m.group(1)) if m else None
                pos += _span(attr)
            name = re.sub(r"\s+", " ", txt(cells[0][2])).strip()
            if val is None or not (0 < val <= 100) or re.sub(r"\s", "", name) in ("합계", "계", "총계", "소계"):
                continue
            if best is None or val > best[0]:
                best = (val, f"주주 표: {name[:40]} {val:g}%")
    if best:
        return best
    text = re.sub(r"\s+", " ", txt(body))
    for sent in re.split(r"(?<=[다음함])\.\s*", text):
        if re.search(OWNER_SUBJ, sent) and len(sent) < 400:
            pcts = [float(x) for x in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", sent) if 0 < float(x) <= 100]
            if pcts and not re.search(r"종속기업|관계기업|분할|신설회사|취득|투자주식|피투자", sent):
                v = max(pcts)
                k = sent.find(f"{v:g}") if f"{v:g}" in sent else sent.find("%")
                k2 = max(sent.rfind(m) for m in ("지배", "주주", "지분") if True)
                a = max(0, min(k, k2 if k2 >= 0 else k) - 100)
                if best is None or v > best[0]:
                    best = (v, sent[a:a + 200].strip())
    return best if best else (None, "주주·지배기업 지분율 문장·표 못 찾음")
