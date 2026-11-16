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
from . import revenue_mix as RM
from .dart import DartClient, DartStop, KEY_ENV, KEY_GUIDE, mask
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
        _mix(R, p, rows_mix, tinfo, rev, brc, True, cls_ctx, items_cfs=(corp, last["year"]))
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


def _mix(R, p, rows_mix, tinfo, rev, rc, listed, ctx, items_cfs=None):
    if not rows_mix:
        p["mix_coverage"] = value(note=tinfo.get("note", "매출 하위 행 없음"))
        return
    cls, method = RM.classify(rows_mix, ctx, listed, R.upstage_key, R.solar_http, R.stat)
    R.methods.add(method)
    sh, tot = RM.mix_shares(rows_mix, cls)
    covs = {"별도": tot / rev} if rev else {}
    if listed and items_cfs and (not covs or not (0.8 <= covs["별도"] <= 1.2)):
        d = R.dc.get("fnlttSinglAcntAll.json", {"corp_code": items_cfs[0], "bsns_year": str(items_cfs[1]), "reprt_code": "11011", "fs_div": "CFS"})
        if d.get("status") == "000":
            rc_rev = ST.map_api_items(d["list"])["revenue"][0]
            if rc_rev:
                covs["연결"] = tot / rc_rev
    basis, cov = min(covs.items(), key=lambda kv: abs(kv[1] - 1)) if covs else (None, None)
    ok = cov is not None and 0.8 <= cov <= 1.2
    note = f"{method}; 기준 매출 {basis}; " + ";".join(f"{k}={v}" for k, v in tinfo.items() if k != "note")
    p["mix_coverage"] = value(cov, rcept_no=rc, note=note) if cov is not None else value(note="매출 없음")
    for k in RM.CATS:
        p["mix_" + k] = value(sh.get(k, 0.0), rcept_no=rc, note=method) if ok else value(note=f"커버리지 {cov:.2f} 범위 밖" if cov is not None else "커버리지 없음")
    p["mix_coverage"]["evidence"]["rows"] = [{"label": r[0], "amount": r[1], "category": cls[i][0], "reason": cls[i][1]} for i, r in enumerate(rows_mix)]


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
    p["max_shareholder_pct"] = value(note="비상장 — OpenDART 최대주주 현황 API는 사업보고서 제출 회사만")
    if col == 0:
        _mix(R, p, RM.unlisted_rows(is_), {}, rev, rc, False, f"{name} 업종코드 {code}")
    else:
        p["mix_coverage"] = value(note="마지막 연도 감사보고서 없음(다음 해 보고서 전기 열) — 매출 구성 생략")
    return p, extra


def run(industry_codes, years, listed="둘 다", revenue_min=None, revenue_max=None, limit=30, fs_pref="별도",
        unlisted_window=None, max_calls=300, client=None, solar_http=None, upstage_key=None):
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
    found, cand_rows, profiles, stop, skipped, short = [], [], [], None, [], []
    prog = {"left": None}
    try:
        corps = _corp_list(dc)
        pools = []
        if listed in ("상장", "둘 다"):
            pools.append(("상장", sorted((c for c in corps if c["stock_code"]), key=lambda c: c["corp_code"])))
        if listed in ("비상장", "둘 다"):
            pools.append(("비상장", _unlisted_pool(dc, years, unlisted_window)))
        for pi, (kind, pool) in enumerate(pools):
            for ci, c in enumerate(pool):
                prog["left"] = (len(pool) - ci) + sum(len(x[1]) for x in pools[pi + 1:])
                if len(found) >= limit:
                    break
                info = dc.get("company.json", {"corp_code": c["corp_code"]})
                if info.get("status") != "000":
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
        "이어서": ("같은 입력으로 다시 부르면 캐시에 쌓인 결과는 다시 부르지 않고 남은 회사부터 이어서 계속합니다." if stop else ""),
        "입력": {"industry_codes": prefixes, "years": years, "listed": listed, "revenue_min": revenue_min, "revenue_max": revenue_max, "limit": limit, "fs_pref": fs_pref},
    }
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


def _unlisted_pool(dc, years, window):
    y = max(years) + 1
    bgn, end = window or (f"{y}0301", f"{y}0331")
    seen, out = set(), []
    page, total_page = 1, 1
    while page <= total_page and page <= 50:
        d = dc.get("list.json", {"bgn_de": bgn, "end_de": end, "pblntf_ty": "F", "corp_cls": "E", "page_no": str(page), "page_count": "100"})
        if d.get("status") != "000":
            break
        total_page = int(d.get("total_page") or 1)
        for r in d.get("list", []):
            if "감사보고서" in r["report_nm"] and r["corp_code"] not in seen:
                seen.add(r["corp_code"])
                out.append({"corp_code": r["corp_code"], "corp_name": r["corp_name"], "stock_code": ""})
        page += 1
    return out


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
