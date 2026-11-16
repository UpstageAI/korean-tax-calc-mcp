"""kr_comparable_candidates — OpenDART로 국내 비교기업 후보 목록·3개년 재무·후보 프로필·근거를 만든다. Claude 작성(2026-11-16).

흐름
1. 회사 목록(corpCode.xml) → 상장: 종목코드 있는 회사 / 비상장: 기간 안 감사보고서 공시(list.json, 외부감사 F·기타법인 E)의 회사
2. 기업개황(company.json)으로 업종 코드(KSIC, 앞자리 일치) 거르기 — 캐시에 쌓이므로 두 번째 실행부터 빠름
3. 재무: 상장 = 단일회사 전체 재무제표 API(별도 우선, 없으면 연결), 비상장 = 감사보고서 원문 XML(그 해 보고서, 없으면 다음 해 보고서의 전기 열)
4. 매출 구성(마지막 연도): 상장 = 사업보고서 매출 표, 비상장 = 손익계산서 매출 하위 행 → 6갈래 분류(Solar 또는 규칙), 커버리지 0.8~1.2만 확보로
5. 프로필 지표(마지막 연도)와 독립성(특수관계 매출, 상장은 최대주주 지분)
호출은 순차·캐시 우선·상한 안에서만. 상한·한도에 닿으면 그때까지 만든 결과와 멈춘 이유를 돌려준다(다시 실행하면 캐시로 이어짐).
"""
import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile

from . import statements as ST
from .statements import title_sections as F_title_sections
from . import revenue_mix as RM
from .dart import DartClient, DartStop, KEY_ENV, KEY_GUIDE, mask
from .index import CorpIndex
from .schema import STATUS_NONE, empty_profile, value

LIMIT_MAX = 100
LISTED_OPTS = ("상장", "비상장", "둘 다")
UPSTAGE_GUIDE = "UPSTAGE_API_KEY가 없어 매출 행을 이름 규칙으로 분류했습니다(정확도 낮음). 키 발급: https://console.upstage.ai"
CANDIDATE_COLS = ["company_id", "company_name", "country", "industry_code", "year", "currency", "revenue", "cogs", "opex", "operating_profit",
                  "total_assets", "inventory", "receivables", "payables", "rnd_expense", "advertising_expense", "related_party_revenue",
                  "max_shareholder_pct", "rcept_no", "fs_div", "changed_cells"]


def _zip_main(raw, rcept_no=None):
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    main = [n for n in names if rcept_no and n == rcept_no + ".xml"] or names[:1]
    return z.read(main[0]).decode("utf-8", "replace")


def _corp_list(dc):
    raw = dc.get("corpCode.xml", {}, binary=True)
    if not isinstance(raw, bytes):
        raise DartStop("회사 목록(corpCode.xml)을 받지 못했습니다: " + raw.get("message", ""))
    root = ET.fromstring(_zip_main(raw))
    return [{k: (e.findtext(k) or "").strip() for k in ("corp_code", "corp_name", "stock_code")} for e in root.iter("list")]


def _match_industry(code, prefixes):
    """'exact' = 등록 코드가 입력 앞자리로 시작 / 'short' = 등록 코드가 더 짧아 입력에 포함(세분류 확인 필요) / None."""
    code = code or ""
    if any(code.startswith(p) for p in prefixes):
        return "exact"
    if len(code) >= 2 and any(len(code) < len(p) and p.startswith(code) for p in prefixes):
        return "short"
    return None


def _ratio(a, b):
    return a / b if a is not None and b else None


def _rows_from_sections(s, biz, kw):
    sec, _ = ST.find_section(s, kw, biz)
    out = []
    for tb, ctx in ST.tables_in(sec)[:5]:
        out += ST.parse_group(ctx)[0]
    return out


def _find(rows, pat):
    for lab, c, p in rows:
        if re.search(pat, lab) and c:
            return c[-1], lab
    return None, ""


RND = r"^(경상연구개발비|연구개발비|연구비|경상개발비)"
ADV = r"^(광고선전비|광고비|광고료|판매촉진비|판촉비)"


class _Run:
    def __init__(self, dc, upstage_key, solar_http):
        self.dc, self.upstage_key, self.solar_http = dc, upstage_key, solar_http
        self.stat = {}
        self.methods = set()
        self.notes = []

    # ---------- 상장 ----------
    def listed(self, corp, info, years, fs_pref):
        rows = []
        fin_items = {}
        for y in years:
            got = None
            for fs in (("OFS", "CFS") if fs_pref == "별도" else ("CFS", "OFS")):
                d = self.dc.get("fnlttSinglAcntAll.json", {"corp_code": corp, "bsns_year": str(y), "reprt_code": "11011", "fs_div": fs})
                if d.get("status") == "000":
                    got = (fs, d["list"])
                    break
            if not got:
                continue
            fs, items = got
            fin_items[y] = (fs, items)
            m = ST.map_api_items(items)
            r = {f: m[f][0] for f in ST.FIELDS}
            ch = [f"{f}:{m[f][1]}" for f in ST.FIELDS if m[f][1] in ("nature_total", "nature_zero")]
            rows.append({"year": y, "fs_div": "별도" if fs == "OFS" else "연결", "rcept_no": items[0].get("rcept_no", ""), **r, "changed_cells": ";".join(ch)})
        return rows, fin_items

    def listed_doc(self, corp, year):
        L = self.dc.get("list.json", {"corp_code": corp, "bgn_de": f"{year + 1}0101", "end_de": f"{year + 1}1231", "pblntf_ty": "A", "page_count": "100"})
        reps = sorted([r for r in L.get("list", []) if re.match(r"^(\[기재정정\])?사업보고서", r["report_nm"])], key=lambda x: x["rcept_no"])
        if not reps:
            return None, None
        rc = reps[0]["rcept_no"]
        raw = self.dc.get("document.xml", {"rcept_no": rc}, binary=True)
        return (_zip_main(raw, rc), rc) if isinstance(raw, bytes) else (None, rc)

    # ---------- 비상장 ----------
    def unlisted_docs(self, corp, years):
        ys = sorted(years)
        L = self.dc.get("list.json", {"corp_code": corp, "bgn_de": f"{ys[0] + 1}0101", "end_de": f"{ys[-1] + 1}1231", "pblntf_ty": "F", "page_count": "100"})
        by = {}
        for r in L.get("list", []):
            m = re.search(r"감사보고서\s*\((\d{4})\.\d{2}\)", r["report_nm"])
            if not m:
                continue
            y, cons = int(m.group(1)), "연결" in r["report_nm"]
            # 별도 감사보고서 우선, 같은 종류면 나중 접수(정정 반영)
            rank = (0 if cons else 1, r["rcept_no"])
            if y not in by or rank > by[y][0]:
                by[y] = (rank, r["rcept_no"])
        return {y: v[1] for y, v in by.items()}

    def unlisted(self, corp, years):
        docs = self.unlisted_docs(corp, years)
        parsed, rows = {}, []
        for y in sorted(years):
            src = docs.get(y)
            col, use = "cur", y
            if not src and docs.get(y + 1):
                src, col, use = docs[y + 1], "prior", y + 1
            if not src:
                continue
            if src not in parsed:
                raw = self.dc.get("document.xml", {"rcept_no": src}, binary=True)
                if not isinstance(raw, bytes):
                    continue
                s = _zip_main(raw, src)
                parsed[src] = (s, ST.audit_financials(s))
            s, af = parsed[src]
            v = af[col]
            ch = [k for k in ("abs_fixed", "ta_derived", "op_sign_fixed") if af["info"].get(k)]
            if col == "prior":
                ch.append(f"{y}년 값은 {use}년 보고서의 전기 열")
            rows.append({"year": y, "fs_div": "연결" if af["info"].get("consolidated") else "별도", "rcept_no": src,
                         **{f: v.get(f) for f in ST.FIELDS}, "changed_cells": ";".join(ch)})
        return rows, parsed, docs


def _profile_listed(R, corp, name, code, rows, fin_items, last, cls_ctx):
    p = empty_profile(company_id=corp, company_name=name, listed=True, industry_code=code, year=last["year"], fs_basis=last["fs_div"], rcept_no=last["rcept_no"])
    fs, items = fin_items[last["year"]]
    rev, ta, inv = last["revenue"], last["total_assets"], last["inventory"]
    rc = last["rcept_no"]
    ppe = ST.api_account(items, "ifrs-full_PropertyPlantAndEquipment", r"^유형자산$", "BS")
    intang = ST.api_account(items, "ifrs-full_IntangibleAssetsOtherThanGoodwill", r"^무형자산$", "BS")
    has_inv_acct = any("재고" in ST.norm(i.get("account_nm")) for i in items if i.get("sj_div") == "BS")
    p["inv_to_sales"] = value(_ratio(inv, rev), rcept_no=rc, account="재고자산/매출액") if inv is not None else (
        value(0.0, STATUS_NONE, rcept_no=rc, note="재무상태표에 재고 계정 없음") if items and not has_inv_acct else value(note="재고 계정은 있으나 금액 못 읽음"))
    p["ppe_ratio"] = value(_ratio(ppe, ta), rcept_no=rc, account="유형자산/자산총계") if ppe is not None and ta else value()
    p["intang_ratio"] = value(_ratio(intang, ta), rcept_no=rc, account="무형자산/자산총계") if intang is not None and ta else value()
    p["ar_to_sales"] = value(_ratio(last["receivables"], rev), rcept_no=rc, account="매출채권/매출액") if last["receivables"] is not None and rev else value()
    if rev and None not in (last["receivables"], last["payables"]):
        p["wc_ratio"] = value(((last["receivables"] or 0) + (inv or 0) - (last["payables"] or 0)) / rev, rcept_no=rc, account="(매출채권+재고-매입채무)/매출액")
    s, brc = R.listed_doc(corp, last["year"])
    extra = {"rnd": None, "adv": None}
    if s:
        rows_mix, tinfo = RM.listed_rows(s)
        api_cogs = [(ST.norm(i.get("account_nm")), [ST.amt(i.get("thstrm_amount"))], []) for i in items
                    if i.get("sj_div") in ("IS", "CIS") and ST.amt(i.get("thstrm_amount")) is not None]
        sig = _signals(s, True, api_cogs, [], last.get("cogs"), brc)
        ov = _overview(s, name)
        p["business_desc"] = value(ov["ctx"][:1500], rcept_no=brc, account="사업의 개요") if ov["ctx"] else value(note="사업의 개요 못 찾음")
        _mix(R, p, rows_mix, tinfo, rev, brc, True, ov["ctx"] or cls_ctx, items_cfs=(corp, last["year"]), signals=sig, ctx_problems=ov["problems"])
        sga = _rows_from_sections(s, True, r"판매비\s*와?\s*(일반)?관리비|판매비및관리비") + _rows_from_sections(s, True, r"비용의\s*성격")
        sga_detail = any(re.match(r"^(급여|복리후생비|지급수수료|감가상각비)", l) for l, c, pr in sga)
        for k, pat, fld, lab in (("rnd", RND, "rnd_ratio", "연구개발비"), ("adv", ADV, "advert_ratio", "광고선전비·판매촉진비")):
            v, acc = _find(sga, pat)
            extra[k] = v
            p[fld] = value(_ratio(v, rev), rcept_no=brc, account=acc) if v is not None and rev else (
                value(0.0, STATUS_NONE, rcept_no=brc, note=f"판관비 내역에 {lab} 계정 없음") if sga_detail else value(note="판관비 내역 못 찾음"))
        inv_rows = _rows_from_sections(s, True, r"재고\s*자산")
        items_inv = ST.inventory_items(inv_rows)
        p["raw_material_inv"] = value(bool(items_inv & {"원재료", "재공품"}), rcept_no=brc, account="재고자산 주석: " + "|".join(sorted(items_inv))) if items_inv else (
            value(False, STATUS_NONE, note="재고 계정 없음") if p["inv_to_sales"]["status"] == STATUS_NONE else value(note="재고 구성 주석 못 찾음"))
        r, why = ST.related_sales(s, True, rev)
        p["related_sales_ratio"] = value(r, rcept_no=brc, account=why) if r is not None else value(note=why)
        sig, st = ST.control_signals(s, True)
        p["control_signals"] = value(sig, rcept_no=brc, account=st) if sig is not None else value(note=st)
        r, why = ST.related_purchases(s, True, last.get("cogs"), rev)
        p["related_purchase_ratio"] = value(r, rcept_no=brc, account=why) if r is not None else value(note=why)
    else:
        p["mix_coverage"] = value(note="사업보고서 원문 없음")
    h = R.dc.get("hyslrSttus.json", {"corp_code": corp, "bsns_year": str(last["year"]), "reprt_code": "11011"})
    pct = _max_shareholder(h)
    p["max_shareholder_pct"] = value(pct[0], rcept_no=pct[1], account="최대주주 현황") if pct[0] is not None else value(note="최대주주 현황 못 읽음")
    return p, extra


def _max_shareholder(h):
    if h.get("status") != "000":
        return None, None
    def f(x):
        try:
            return float(str(x).replace(",", ""))
        except ValueError:
            return None
    L = h["list"]
    common = [i for i in L if not any(x in (i.get("stock_knd") or "") for x in ("없는", "우선", "종류")) and (i.get("stock_knd") or "-") != "-"]
    ppl = [i for i in common if (i.get("nm") or "").replace(" ", "") not in ("계", "합계")]
    if not ppl:
        return None, None
    top = max(ppl, key=lambda i: f(i.get("trmend_posesn_stock_qota_rt")) or -1)
    return f(top.get("trmend_posesn_stock_qota_rt")), L[0].get("rcept_no")


CTX_SKIP = re.compile(r"참고하시기|참조하시기|참고\s*바랍니다|참조\s*바랍니다|을\s*참고|를\s*참고|을\s*참조|를\s*참조|목\s*차|기재하였습니다|기재되어\s*있습니다")
CTX_MAX = 4000


def _sentences(text):
    return [x.strip() for x in re.split(r"(?<=[다요])\.\s*|(?<=니다)\s+(?=[가-힣A-Z(])", text) if len(x.strip()) >= 8]


def _company_core(name):
    return re.sub(r"\(주\)|㈜|주식회사|\s", "", name or "")


IND_HEAD = re.compile(r"업계|시장|산업")
CO_HEAD = re.compile(r"회사의\s*현황|회사\s*현황|사업의\s*개황|영업\s*개황|사업\s*부문|회사의\s*개요|당사의|회사의\s*개황|사업\s*현황|영업\s*현황|회사의\s*사업")
TOP_HEAD = re.compile(r"^\s*([가-하])\s*\.\s*")


def _units(sec):
    """절 HTML → 단위 목록 [{'t': 글, 'kind': 'sent'|'row', 'block': 'industry'|'company'|'other'}] (문서 순서).
    표는 행마다 '셀 | 셀'로 남기고, 라벨 칸 없이 숫자만 있는 행만 뺀다. '가. 업계의 현황' 같은 소제목으로 블록을 나눈다."""
    sec = re.sub(r"<TITLE[^>]*>.*?</TITLE>", " ", sec, flags=re.S)
    units, block = [], "other"
    for m in re.finditer(r"<TABLE[^>]*>.*?</TABLE>|<P[^>]*>.*?</P>|<[^>]+>|[^<]+", sec, re.S):
        piece = m.group(0)
        if piece.startswith("<") and not piece.startswith(("<TABLE", "<P")):
            continue                              # 그 밖의 태그(SECTION·IMG 등)는 건너뜀
        if piece.startswith("<TABLE"):
            for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", piece, re.S):
                cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).replace("&nbsp;", " ").strip()
                         for c in re.findall(r"<T[DEHU][^>]*>(.*?)</T[DEHU]>", tr, re.S)]
                cells = [c for c in cells if c]
                if cells and any(re.search(r"[가-힣A-Za-z]", c) for c in cells):
                    units.append({"t": " | ".join(cells), "kind": "row", "block": block})
            continue
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", piece)).replace("&nbsp;", " ").strip()
        if not text:
            continue
        mh = TOP_HEAD.match(text)
        if mh:
            title = text[mh.end(): mh.end() + 25]
            block = "industry" if IND_HEAD.search(title) else ("company" if CO_HEAD.search(title) else "other")
        if len(text) < 60 and not re.search(r"(다|음|함|요|됨|임)\.?$", text):
            units.append({"t": text, "kind": "head", "block": block})   # 소제목 줄
            continue
        for x in _sentences(text):
            if CTX_SKIP.search(x):
                continue
            if len(x) < 30 and not re.search(r"(다|음|함|요|됨|임)\.?$", x):
                units.append({"t": x, "kind": "head", "block": block})   # 문단 안에 붙은 소제목 조각('나. 조직도' 등)
                continue
            x = x if re.search(r"[.!?]$", x) else (x + "." if re.search(r"(다|음|함|요|됨|임)$", x) else x)
            units.append({"t": x, "kind": "sent", "block": block})
    return units


def _overview(s, name=None):
    """사업보고서 '1. 사업의 개요' 추출 + 검사. 반환 {'ctx', 'raw', 'truncated', 'problems'}.
    ctx: 절의 문장과 표 행('셀 | 셀', 숫자만 있는 행 제외)을 4,000자까지 문서 순서대로. 넘으면 회사 블록('회사의 현황'·'영업개황'·'사업부문' 등)·
    회사가 주어인 문장·사업부문표 행을 먼저 채우고, 남는 자리에 업계·시장 현황 블록 앞부분을 채운다. 문장·행 중간에서 자르지 않는다."""
    secs = F_title_sections(s)
    sec = next((s[a:b] for a, b, t in secs if re.match(r"^\s*1\s*\.\s*(\([^)]*\))?\s*사업의\s*개요", t)), None)
    if sec is None:
        m = re.search(r"<TITLE[^>]*>\s*I{1,2}\.\s*사업의\s*내용\s*</TITLE>", s)
        if not m:
            return {"ctx": "", "raw": "", "truncated": False, "problems": ["사업의 개요 절 없음"]}
        end = re.search(r"<TITLE[^>]*>\s*2\s*\.\s*주요\s*제품", s[m.end():])
        sec = s[m.end(): m.end() + (end.start() if end else 30000)]
    raw = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<TITLE[^>]*>.*?</TITLE>", " ", sec, flags=re.S))).replace("&nbsp;", " ").strip()
    core = _company_core(name or (re.search(r"<COMPANY-NAME[^>]*>(.*?)</COMPANY-NAME>", s[:20000]) or [None, ""])[1])
    units = _units(sec)
    total = sum(len(u["t"]) + 1 for u in units)
    truncated = total > CTX_MAX
    if not truncated:
        keep = list(range(len(units)))
    else:
        subj = re.compile(SUBJ + ("|" + re.escape(core) if core else ""))
        seg = re.compile(r"\d{1,3}(,\d{3})+|\d+(\.\d+)?\s*%")
        prio = [k for k, u in enumerate(units) if u["block"] != "industry" or subj.search(u["t"]) or (u["kind"] == "row" and seg.search(u["t"]))]
        keep, n = [], 0
        for k in prio:
            L = len(units[k]["t"]) + 1
            if n + L <= CTX_MAX:
                keep.append(k)
                n += L
        for k, u in enumerate(units):          # 남는 자리에 업계·시장 현황 앞부분(이어진 앞쪽만)
            if k in keep or u["block"] != "industry":
                continue
            L = len(u["t"]) + 1
            if n + L > CTX_MAX:
                break
            keep.append(k)
            n += L
        keep.sort()
    # 뒤에 붙은 내용이 없는 소제목(맨 끝·건너뛴 단위 앞)은 뺀다
    kept, nxt_ok = [], False                # 뒤에서부터: 바로 뒤에 내용(문장·표 행)이 이어지는 소제목만 남김
    for i in range(len(keep) - 1, -1, -1):
        k = keep[i]
        if units[k]["kind"] == "head":
            follows = i + 1 < len(keep) and keep[i + 1] == k + 1 and nxt_ok
            if follows:
                kept.append(k)
            nxt_ok = follows
        else:
            kept.append(k)
            nxt_ok = True
    keep = kept[::-1]
    out, prev = [], None
    for k in keep:
        u = units[k]
        sep = "\n" if (u["kind"] == "row" or prev == "row") else " "
        out.append(("" if not out else sep) + u["t"])
        prev = u["kind"]
    ctx = "".join(out).strip()
    return {"ctx": ctx, "raw": raw, "truncated": truncated, "problems": overview_problems(ctx, raw, core, _segment_rows(sec), truncated)}


def _segment_rows(sec):
    """원문 절의 사업부문·매출 표 행 — 라벨 칸이 있고 금액 또는 비중(%) 칸이 있는 행 → [(라벨, 금액·비중 글자)]."""
    out = []
    for tb in re.findall(r"<TABLE[^>]*>(.*?)</TABLE>", sec, re.S):
        trs = re.findall(r"<TR[^>]*>(.*?)</TR>", tb, re.S)
        head = re.sub(r"\s", "", re.sub(r"<[^>]+>", " ", " ".join(trs[:2])))
        # 매출·매출비중 표만 — 머리에 매출/매출액/비중과 사업부문·품목·제품 라벨이 있고, 지분·출자 표(종속회사 지분율 등)는 뺀다
        if not (re.search(r"매출|비중", head) and re.search(r"사업부문|부문|품목|제품|구분|사업", head)) or re.search(r"지분|출자|소유|주식|의결권", head):
            continue
        for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", tb, re.S):
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<T[DEHU][^>]*>(.*?)</T[DEHU]>", tr, re.S)]
            lab = next((c for c in cells if re.search(r"[가-힣A-Za-z]", c)), None)
            num = next((c for c in cells if re.match(r"^\(?-?\d{1,3}(,\d{3})+\)?$|^\d+(\.\d+)?\s*%$", c)), None)
            if lab and num and not re.search(r"합\s*계|소\s*계|^계$", lab):
                out.append((lab, num))
    return out


SUBJ = r"(당사는|당사의|당사가|당사\s|회사는|연결회사|지배회사|연결실체|사업부(문)?(는|은|에서))"


def overview_problems(ctx, raw, core="", seg_rows=None, truncated=True):
    """추출 실패 유형 자동 검사."""
    p = []
    if re.search(r"[·.‥…ㆍ]{6,}|-{6,}", ctx) or re.search(r"목\s*차", ctx[:200]):
        p.append("목차를 잡음(점선·쪽 번호)")
    if not ctx:
        p.append("추출 결과 없음")
    elif len(ctx) < 200 and len(raw) >= len(ctx) + 200:
        p.append(f"추출 {len(ctx)}자 < 200자인데 원문 절은 {len(raw)}자")
    if re.search(r"(^|\s)[2-9]\s*\.\s*(주요\s*제품|원재료|생산\s*및\s*설비|매출\s*및\s*수주|위험\s*관리|주요\s*계약|연구\s*개발\s*활동|기타\s*참고)", ctx):
        p.append("다른 절까지 넘어감('2. 주요 제품' 등)")
    subj = re.compile(SUBJ + ("|" + re.escape(core) if core else ""))
    if ctx and not subj.search(ctx):
        p.append("회사 설명 빠짐(회사가 주어인 문장 0개)")
    miss = [lab for lab, num in (seg_rows or []) if num not in ctx]
    if miss:
        p.append("사업부문표 손실(" + ", ".join(m[:20] for m in miss[:4]) + ")")
    last = ctx.rstrip().split("\n")[-1] if ctx else ""
    if ctx and truncated and " | " not in last and not re.search(r"(다|음|함|요|됨|임|니다)\.?\)?$", last):
        p.append("문장 중간에서 잘림")
    body = re.sub(r"\s", "", ctx)
    if body and sum(ch.isdigit() or ch in ",.%()" for ch in body) / len(body) > 0.4:
        p.append("표 숫자만 남음")
    return p


def _context(s, biz, name=None):
    """회사 맥락(모델 입력). 상장: 사업의 개요(_overview). 비상장: 감사보고서 주석 회사 개요 문장 그대로."""
    if biz:
        return _overview(s, name)["ctx"]
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).replace("&nbsp;", " ")
    i = t.find("주석", t.find("(첨부)") + 1 if "(첨부)" in t else 0)
    for pat in (r"일\s*반\s*사\s*항", r"회\s*사\s*의\s*개\s*요", r"당사의\s*개요"):
        m = re.search(pat, t[i:]) if i >= 0 else None
        if m:
            seg = t[i + m.end(): i + m.end() + 1500]
            end = re.search(r"\s\(?2\)?\s*[.)]\s*[가-힣]|\s2\s*\.\s*[가-힣]", seg)
            return seg[: end.start() if end else 800].strip()[:800]
    return ""


def _signals(s, biz, stmt_cogs_rows, stmt_inv_rows, cogs_total, rc):
    cogs_rows = list(stmt_cogs_rows) + _rows_from_sections(s, biz, r"매출\s*원가|영업\s*비용|비용의\s*성격")
    inv_rows = list(stmt_inv_rows) + _rows_from_sections(s, biz, r"재고\s*자산")
    return ST.goods_signals(cogs_rows, inv_rows, cogs_total, rc)


def _mix(R, p, rows_mix, tinfo, rev, rc, listed, ctx, items_cfs=None, signals=None, ctx_problems=None):
    if not rows_mix:
        p["mix_coverage"] = value(note=tinfo.get("note", "매출 하위 행 없음"))
        return
    if listed and ctx_problems and any(not (len(r) > 4 and r[4]) for r in rows_mix):
        # 사업의 개요 추출 실패 — 모델에 넘기지 않고 매출 구성은 사람 확인
        why = "사업의 개요 추출 실패(" + "; ".join(ctx_problems) + ") — 사람 확인"
        tot = sum(r[1] for r in rows_mix)
        p["mix_coverage"] = value(tot / rev, rcept_no=rc, note=why) if rev else value(note=why)
        for k in RM.CATS:
            p["mix_" + k] = value(note=why)
        p["mix_coverage"]["evidence"]["rows"] = [{"label": r[0], "amount": r[1], "category": "", "reason": "분류 안 함(사업의 개요 추출 실패)"} for r in rows_mix]
        R.methods.add("분류 안 함(사업의 개요 추출 실패)")
        return
    cls, method = RM.classify(rows_mix, ctx, listed, R.upstage_key, R.solar_http, R.stat)
    R.methods.add(method)
    al = RM.allocate(rows_mix, cls, signals)
    sh, tot = al["shares"], al["total"]
    covs = {"별도": tot / rev} if rev else {}
    if listed and items_cfs and (not covs or not (0.8 <= covs["별도"] <= 1.2)):
        d = R.dc.get("fnlttSinglAcntAll.json", {"corp_code": items_cfs[0], "bsns_year": str(items_cfs[1]), "reprt_code": "11011", "fs_div": "CFS"})
        if d.get("status") == "000":
            rc_rev = ST.map_api_items(d["list"])["revenue"][0]
            if rc_rev:
                covs["연결"] = tot / rc_rev
    basis, cov = min(covs.items(), key=lambda kv: abs(kv[1] - 1)) if covs else (None, None)
    ok = cov is not None and 0.8 <= cov <= 1.2
    note = f"{method}; 기준 매출 {basis}; " + ";".join(f"{k}={v}" for k, v in tinfo.items() if k != "note") + (f"; {al['goods_alloc']}" if al["goods_alloc"] else "")
    p["mix_coverage"] = value(cov, rcept_no=rc, note=note) if cov is not None else value(note="매출 없음")
    for k in RM.CATS:
        if not ok:
            p["mix_" + k] = value(note=f"커버리지 {cov:.2f} 범위 밖" if cov is not None else "커버리지 없음")
        elif al["conflict"]:
            p["mix_" + k] = value(note=al["conflict"] + " — 사람 확인")
        elif k in al["unknown"]:
            p["mix_" + k] = value(note=al["goods_alloc"] + " — 사람 확인")
        else:
            src = "회계 기준 배분" if (k in ("product", "merchandise") and al["goods_alloc"].startswith("회계")) else method
            p["mix_" + k] = value(sh.get(k, 0.0), rcept_no=rc, note=src)
    ev = p["mix_coverage"]["evidence"]
    ev["rows"] = [{"label": r[0], "amount": r[1], "category": cls[i][0],
                   "reason": ("회계 기준 배분(모델·규칙: 재화) " if cls[i][0] == RM.GOODS and al["goods_alloc"].startswith("회계") else "") + cls[i][1]}
                  for i, r in enumerate(rows_mix)]
    ev["accounting"] = signals or {}
    if al["conflict"]:
        ev["conflict"] = al["conflict"]


def _profile_unlisted(R, corp, name, code, rows, parsed, docs, last):
    p = empty_profile(company_id=corp, company_name=name, listed=False, industry_code=code, year=last["year"], fs_basis=last["fs_div"], rcept_no=last["rcept_no"])
    s, af = parsed[last["rcept_no"]]
    col = 0 if docs.get(last["year"]) == last["rcept_no"] else 1
    bs, is_ = af["bs"], af["is"]
    rev, ta, inv = last["revenue"], last["total_assets"], last["inventory"]
    rc = last["rcept_no"]
    has_bs = bool(bs)
    p["inv_to_sales"] = value(_ratio(inv, rev), rcept_no=rc, account="재고자산/매출액") if inv is not None and rev else (
        value(0.0, STATUS_NONE, rcept_no=rc, note="재무상태표에 재고 계정 없음") if has_bs and not any("재고" in l for l, c, pr in bs) else value())
    ppe = ST.row_value(bs, r"^유형자산$", col)
    intang = ST.row_value(bs, r"^무형자산$", col)
    p["ppe_ratio"] = value(_ratio(ppe, ta), rcept_no=rc, account="유형자산/자산총계") if ppe is not None and ta else value()
    p["intang_ratio"] = value(_ratio(intang, ta), rcept_no=rc, account="무형자산/자산총계") if intang is not None and ta else (
        value(0.0, STATUS_NONE, rcept_no=rc, note="재무상태표에 무형자산 계정 없음") if has_bs else value())
    p["ar_to_sales"] = value(_ratio(last["receivables"], rev), rcept_no=rc, account="매출채권/매출액") if last["receivables"] is not None and rev else value()
    if rev and None not in (last["receivables"], last["payables"]):
        p["wc_ratio"] = value(((last["receivables"] or 0) + (inv or 0) - (last["payables"] or 0)) / rev, rcept_no=rc, account="(매출채권+재고-매입채무)/매출액")
    sga = is_ + _rows_from_sections(s, False, r"판매비\s*와?\s*(일반)?관리비|판매비및관리비")
    sga_detail = any(re.match(r"^(급여|복리후생비|지급수수료|감가상각비)", l) for l, c, pr in sga)
    extra = {}
    for k, pat, fld, lab in (("rnd", RND, "rnd_ratio", "연구개발비"), ("adv", ADV, "advert_ratio", "광고선전비·판매촉진비")):
        v, acc = _find(sga, pat) if col == 0 else (None, "")
        extra[k] = v
        p[fld] = value(_ratio(v, rev), rcept_no=rc, account=acc) if v is not None and rev else (
            value(0.0, STATUS_NONE, rcept_no=rc, note=f"판관비 내역에 {lab} 계정 없음") if sga_detail and col == 0 else value(note="판관비 내역 못 찾음"))
    items_inv = ST.inventory_items(bs) or ST.inventory_items(_rows_from_sections(s, False, r"재고\s*자산"))
    p["raw_material_inv"] = value(bool(items_inv & {"원재료", "재공품"}), rcept_no=rc, account="재고 구성: " + "|".join(sorted(items_inv))) if items_inv else (
        value(False, STATUS_NONE, note="재고 계정 없음") if p["inv_to_sales"]["status"] == STATUS_NONE else value(note="재고 구성 못 찾음"))
    r, why = ST.related_sales(s, False, rev)
    p["related_sales_ratio"] = value(r, rcept_no=rc, account=why) if r is not None else value(note=why)
    sig, st = ST.control_signals(s, False)
    p["control_signals"] = value(sig, rcept_no=rc, account=st) if sig is not None else value(note=st)
    r, why = ST.related_purchases(s, False, last.get("cogs"), rev)
    p["related_purchase_ratio"] = value(r, rcept_no=rc, account=why) if r is not None else value(note=why)
    p["max_shareholder_pct"] = value(note="비상장 — OpenDART 최대주주 현황 API는 사업보고서 제출 회사만")
    op, osent = ST.owner_share(s)
    p["owner_pct"] = value(op, rcept_no=rc, sentence=osent, account="감사보고서 주석(주주 현황·지배기업)") if op is not None else value(note=osent)
    ctx = _context(s, False)
    p["business_desc"] = value(ctx[:1500], rcept_no=rc, account="감사보고서 주석 회사 개요") if ctx else value(note="회사 개요 못 찾음")
    if col == 0:
        sig = _signals(s, False, is_, bs, last.get("cogs"), rc)
        _mix(R, p, RM.unlisted_rows(is_), {}, rev, rc, False, ctx or f"{name} 업종코드 {code}", signals=sig)
    else:
        p["mix_coverage"] = value(note="마지막 연도 감사보고서 없음(다음 해 보고서 전기 열) — 매출 구성 생략")
    return p, extra


def run(industry_codes, years, listed="둘 다", revenue_min=None, revenue_max=None, limit=30, fs_pref="별도",
        unlisted_window=None, max_calls=300, client=None, solar_http=None, upstage_key=None, build_index_only=False):
    """반환 {'결과': ..., '근거': [...], '주의': [...]} 또는 키 없음 안내."""
    key = os.environ.get(KEY_ENV, "")
    if client is None and not key:
        return {"결과": {"상태": "꺼짐 — OpenDART 인증키 없음", "안내": KEY_GUIDE}, "근거": [], "주의": ["이 도구만 꺼지고 다른 도구는 그대로 씁니다."]}
    if listed not in LISTED_OPTS:
        raise ValueError(f"listed는 {LISTED_OPTS} 중 하나")
    if not industry_codes or not years:
        raise ValueError("industry_codes와 years가 필요합니다")
    limit = max(1, min(int(limit), LIMIT_MAX))
    years = sorted({int(y) for y in years})
    prefixes = [str(c).strip().upper().lstrip("C") for c in industry_codes]
    dc = client or DartClient(key=key, max_calls=max_calls)
    up_key = upstage_key if upstage_key is not None else os.environ.get("UPSTAGE_API_KEY", "")
    R = _Run(dc, up_key, solar_http)
    IX = CorpIndex()
    found, cand_rows, profiles, stop, skipped, short = [], [], [], None, [], []
    prog = {"left": None}
    pools = []
    try:
        corps = _corp_list(dc)
        if listed in ("상장", "둘 다"):
            pools.append(("상장", sorted((c for c in corps if c["stock_code"]), key=lambda c: c["corp_code"])))
        if listed in ("비상장", "둘 다"):
            y = max(years) + 1
            bgn, end = unlisted_window or (f"{y}0301", f"{y}0331")
            pools.append(("비상장", IX.pool(dc, bgn, end)))
        for pi, (kind, pool) in enumerate(pools):
            # 색인에 있는 회사부터(업종을 색인으로 먼저 거름), 그다음 색인에 없는 회사(기업개황을 불러 색인에 쌓음)
            ordered = [c for c in pool if IX.get(c["corp_code"])] + [c for c in pool if not IX.get(c["corp_code"])]
            for ci, c in enumerate(ordered):
                prog["left"] = sum(1 for x in ordered[ci:] if not IX.get(x["corp_code"])) + sum(
                    1 for p_ in pools[pi + 1:] for x in p_[1] if not IX.get(x["corp_code"]))
                if len(found) >= limit and not build_index_only:
                    break
                ix = IX.get(c["corp_code"])
                if ix:
                    info = {"status": "000", "corp_name": ix["n"], "induty_code": ix["i"], "acc_mt": ix["a"], "corp_cls": ix["c"]}
                else:
                    info = dc.get("company.json", {"corp_code": c["corp_code"]})
                    if info.get("status") == "000":
                        IX.put(c["corp_code"], info)
                if info.get("status") != "000" or build_index_only:
                    continue
                cls = info.get("corp_cls")
                if (kind == "상장" and cls not in ("Y", "K", "N")) or (kind == "비상장" and cls != "E"):
                    continue
                mt = _match_industry(info.get("induty_code"), prefixes)
                if not mt:
                    continue
                res = _one(R, kind, c["corp_code"], info, years, fs_pref, revenue_min, revenue_max)
                if res is None:
                    continue
                if isinstance(res, str):
                    skipped.append({"company_id": c["corp_code"], "company_name": info.get("corp_name"), "사유": res})
                    continue
                rows, prof = res
                if mt == "short":
                    short.append({"company_id": c["corp_code"], "company_name": info.get("corp_name"), "industry_code": info.get("induty_code")})
                found.append(c["corp_code"])
                cand_rows += rows
                profiles.append(prof)
    except DartStop as e:
        stop = mask(str(e), key)
    IX.save()
    pool_cut = stop and listed in ("비상장", "둘 다") and not any(k == "비상장" for k, _ in pools)
    if stop and prog["left"] is None:
        prog["left"] = sum(1 for _, pool in pools for c in pool if not IX.get(c["corp_code"]))
    ix_n = ix_N = 0
    for kind, pool in pools:
        a, b = IX.progress(pool)
        ix_n, ix_N = ix_n + a, ix_N + b
    method = sorted(R.methods)
    low_acc = any("정확도 낮음" in m for m in method)
    result = {
        "후보_수": len(found),
        "후보_행": cand_rows,
        "후보_프로필": profiles,
        "제외_목록": skipped[:50],
        "업종_짧은코드_포함": short,
        "매출_분류_방법": method or ["매출 행 없음"],
        "정확도_낮음": low_acc,
        "호출": {"OpenDART_실호출": dc.calls, "OpenDART_캐시": dc.cache_hits, "Solar_실호출": R.stat.get("solar_calls", 0),
                 "Solar_캐시": R.stat.get("solar_cached", 0), "오류": [mask(x, key) for x in dc.errors[:10]] + [mask(x, key) for x in R.stat.get("solar_errors", [])[:5]]},
        "멈춤": stop or "",
        "남은_회사_수": (prog["left"] if stop else 0),
        "이어서": ("같은 입력으로 다시 부르면 캐시에 쌓인 결과는 다시 부르지 않고 남은 회사부터 이어서 계속합니다."
                   + (" 비상장 모집단(공시 목록)을 모으는 중에 멈춰 남은 수에 비상장은 아직 빠져 있습니다." if pool_cut else "") if stop else ""),
        "입력": {"industry_codes": prefixes, "years": years, "listed": listed, "revenue_min": revenue_min, "revenue_max": revenue_max, "limit": limit,
                 "fs_pref": fs_pref, "build_index_only": build_index_only},
        "색인": {"버전": IX.data["version"], "갱신": IX.data["updated"], "색인된_회사": len(IX.data["corps"]),
                 "모집단_색인": f"{ix_n}/{ix_N}", "완료": ix_N > 0 and ix_n == ix_N, "비상장_모집단_일수": len(IX.data["days"]),
                 "안내": ("" if ix_N and ix_n == ix_N else f"색인 {ix_n}/{ix_N} — 같은 입력으로 다시 부르면 이어서 계속(하루 상한 KR_COMPARABLES_DAILY_CAP 안에서)")},
    }
    if build_index_only:
        result["후보_수"] = 0
    notes = ["후보 프로필은 숫자 신호와 근거(접수번호·계정)입니다 — 비교대상 적정성 판단은 kr_comparable_profile_compare·사람 검토로.",
             "값 상태: 확보 / 불명-없음(원문에 계정 없음 → 0으로 봄) / 불명-못찾음(0인지 모름).",
             "비상장 최대주주 지분은 OpenDART API로 얻을 수 없어 불명 — 감사보고서 주석의 주주 현황을 사람이 확인."]
    if low_acc:
        notes.append(UPSTAGE_GUIDE)
    if stop:
        left = "알 수 없음(후보 목록을 만드는 중 멈춤)" if prog["left"] is None else f"{prog['left']}개"
        notes.append(f"멈춤: {stop} — 아직 확인하지 않은 회사 {left}. 같은 입력으로 다시 부르면 이어서 계속합니다.")
    basis = ["OpenDART 개발가이드(공시정보·정기보고서 주요정보·재무정보·공시서류원본파일)", "국조법 시행령 제2조②(특수관계 — 지분 50%)",
             "국조칙 비교가능성 분석요소 — 기능·자산·위험(프로필 지표는 판단 보조)"]
    return {"결과": result, "근거": basis, "주의": notes}


def _one(R, kind, corp, info, years, fs_pref, rmin, rmax):
    name, code = info.get("corp_name"), info.get("induty_code")
    if kind == "상장":
        rows, fin_items = R.listed(corp, info, years, fs_pref)
        parsed = docs = None
    else:
        rows, parsed, docs = R.unlisted(corp, years)
    if not rows:
        return "재무 자료 없음"
    last = max(rows, key=lambda r: r["year"])
    rev = last.get("revenue")
    if rmin is not None and (rev is None or rev < rmin):
        return f"매출 {rev} < 하한"
    if rmax is not None and (rev is None or rev > rmax):
        return f"매출 {rev} > 상한"
    if kind == "상장":
        prof, extra = _profile_listed(R, corp, name, code, rows, fin_items, last, f"{name} 업종코드 {code}")
    else:
        prof, extra = _profile_unlisted(R, corp, name, code, rows, parsed, docs, last)
    prof["major_label"] = None
    with_op = [r for r in rows if r.get("operating_profit") is not None]
    k = sum(1 for r in with_op if r["operating_profit"] < 0)
    opx = last.get("opex")
    prof["sga_ratio"] = value(_ratio(opx, rev), rcept_no=last.get("rcept_no"), account="판매비와관리비/매출액") if opx is not None and rev else value(note="판관비 못 읽음")
    prof["loss_years"] = value(k, rcept_no=last.get("rcept_no"), account="영업이익",
                               note=f"분석 연도 {len(with_op)}년 중 {k}년 영업손실") if with_op else value(note="영업이익 자료 없음")
    out = []
    ms = prof["max_shareholder_pct"]["value"]
    rel = prof["related_sales_ratio"]["value"]
    for r in rows:
        is_last = r["year"] == last["year"]
        out.append({"company_id": corp, "company_name": name, "country": "KR", "industry_code": code, "currency": "KRW",
                    **{k: r.get(k) for k in ("year", "revenue", "cogs", "opex", "operating_profit", "total_assets", "inventory", "receivables", "payables", "rcept_no", "fs_div", "changed_cells")},
                    "rnd_expense": extra.get("rnd") if is_last else None, "advertising_expense": extra.get("adv") if is_last else None,
                    "related_party_revenue": round(rel * r["revenue"]) if (is_last and rel is not None and r.get("revenue")) else None,
                    "max_shareholder_pct": ms})
    return out, prof
