"""비교대상 기업 선정(스크리닝) — 유료 데이터베이스에서 내보낸 후보 목록에 선정 기준을 재현 가능하게 적용. Claude 작성(2026-11-14).

이 도구가 메우는 고리: 데이터베이스 추출 목록 → [기준 적용·탈락 사유·다년 가중평균·차이 조정·민감도] → arm_length_range → 개별기업보고서 Ⅱ-11·12·13·15.
데이터베이스 검색 자체(모집단·업종·키워드)와 회사별 기능 비교(정성 판단)는 하지 않는다 — 정성 판단은 사람이 사유와 함께 넣어야만 반영한다.

근거(로컬 보관 법제처 원문 대조: 국조법 2016·2020·2026 시행본, 시행령 2016.2.5.·2020.8.12.·2021.2.17.·2026.1.2., 시행규칙 2016.4.6.·2020.3.13.·2021.3.16.·2022.3.18.·2025.3.21.):
- 2021.1.1. 이후 개시 사업연도(전부개정 시행령 부칙 제3조): 법 제8조①, 영 제8조①(거래순이익률 지표)·제14조(선택 기준·분석요소)·제15조①(분석 절차)·③(다년도)·④(차이 조정)·
  ⑤(둘 이상의 거래로 정상가격 범위)·⑥(범위 밖 기준점)·⑦(경제위기 손실기업, 2022.2.15. 신설), 시행규칙 제6조①③·제7조①·제9조,
  시행규칙 별지 제1호서식(거래가격 조정신고서) 작성방법 10 — 2022.3.18. 시행규칙부터 비교대상 수익성지표 값의 '정상사분위범위' 기재.
- 2016~2020 사업연도: 구 법 제5조①, 구 영 제4조(지표)·제5조(선택 기준)·제6조(분석 절차·범위·다년도), 구 시행규칙 제2조·제2조의2.
- 특수관계(독립성의 법정 하한): 법 제2조①3호, 영 제2조② — 의결권 있는 주식 50% 이상 직·간접 소유.
- 기준값(25%·3%·5%·25%·75%·손실 2개 연도·1.5×IQR)은 법령·OECD 지침 어디에도 숫자가 없는 실무 관행값 — 모두 바꿀 수 있고 결과에 [관행]으로 표시한다.
"""
import csv
import os
from fractions import Fraction

from .calc_tp import _quantile

SCREEN_NAMES = {
    "S1a": "독립성(법정 하한 50%)", "S1b": "독립성(관행)", "S2": "자료 충분성", "S3": "업종 코드", "S4": "규모",
    "S5": "지속 손실", "S6": "연구개발 강도", "S7": "광고 강도", "S8": "운전자본 강도", "S9": "특수관계 매출",
    "S10": "해당 부문 비중", "S11": "특수 상황", "S12": "정성 판단(사람)", "S13": "이상치",
}
FUNNEL_ORDER = ["S1a", "S1b", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12"]
DEFAULT_SCREENS = {
    "independence_pct": 25, "independence_bvd_reject": ["C", "D", "U"],
    "industry_codes": None,                     # None이면 S3를 적용하지 않음
    "size_min": None, "size_max": None,         # 평균 매출(입력 통화). None이면 S4 끔
    "loss_years": 2, "crisis_exception": False,
    "rnd_max": 0.03, "adv_max": 0.05, "wc_band": None, "related_max": 0.25, "segment_min": 0.75,
    "special_flags": ["start_up", "bankruptcy", "restructuring", "merger", "delisted"],
    "outlier_k": 1.5, "op_tolerance": 0.005,
}
PRACTICE = {"independence_pct": "[관행] 25%는 데이터베이스 독립성 지표 구간을 따른 실무값 — 국조법령 근거 없음",
            "rnd_max": "[관행] OECD 3.43이 무형자산 관련 기준을 예로 들지만 숫자는 없음",
            "adv_max": "[관행] 마케팅 무형자산이 없는 분석대상일 때의 실무값",
            "related_max": "[관행] 비교대상 이익률이 특수관계 거래로 왜곡될 가능성",
            "segment_min": "[관행] 시행규칙 제6조③(재무정보를 합리적 수준까지 세분화) 취지",
            "loss_years": "[관행] OECD 3.64~3.65(단순 기능은 오래 손실을 내지 않음, 손실은 추가 검토 계기)",
            "outlier_k": "[관행] 1.5×IQR 표시 — OECD 3.59·3.66(동떨어진 값은 신뢰성 의심), 자동 탈락하지 않음"}
PLI = {"OM": "매출액 대비 거래순이익(영 제8조①1호)", "ROA": "자산 대비 거래순이익(영 제8조①2호)",
       "NCP": "매출원가·영업비용 대비 거래순이익(영 제8조①3호)", "BERRY": "영업비용 대비 매출총이익(영 제8조①4호)"}
NUM_COLS = ["revenue", "cogs", "opex", "operating_profit", "total_assets", "inventory", "receivables", "payables",
            "rnd_expense", "advertising_expense", "related_party_revenue", "max_shareholder_pct", "relevant_segment_share", "employees"]


def _fr(x):
    if x is None:
        return None
    if isinstance(x, bool):
        raise ValueError
    if isinstance(x, str):
        x = x.strip().replace(",", "")
        if x == "":
            return None
    return Fraction(str(x))


def _pct(x, d=3):
    return None if x is None else round(float(x) * 100, d)


def load_rows(file_path=None, rows=None, column_map=None):
    """CSV/XLSX(첫 시트, 첫 행 머리글) 또는 행 목록. column_map으로 DB 열 이름을 표준 열에 연결."""
    if rows is None:
        if not file_path:
            raise ValueError("file_path 또는 rows 중 하나 필요")
        p = os.path.expanduser(file_path)
        if p.lower().endswith((".xlsx", ".xlsm")):
            from openpyxl import load_workbook
            ws = load_workbook(p, read_only=True, data_only=True).worksheets[0]
            it = ws.iter_rows(values_only=True)
            head = [str(h).strip() if h is not None else "" for h in next(it)]
            rows = [dict(zip(head, r)) for r in it if any(v is not None for v in r)]
        else:
            with open(p, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
    cmap = column_map or {}
    return [{cmap.get(k, k): v for k, v in r.items()} for r in rows]


def _pli_parts(y, pli):
    """(분자, 분모) — 거래순이익은 매출 − 매출원가 − 판관비(cogs·opex가 있을 때), 없으면 보고 영업이익."""
    rev, cogs, opex = y.get("revenue"), y.get("cogs"), y.get("opex")
    op = (rev - cogs - opex) if (rev is not None and cogs is not None and opex is not None and y.get("_op_source") == "recalc") else y.get("operating_profit")
    if pli == "OM":
        return op, rev
    if pli == "NCP":
        return op, (cogs + opex) if cogs is not None and opex is not None else None
    if pli == "BERRY":
        return (rev - cogs) if cogs is not None else None, opex
    if pli == "ROA":
        return op, y.get("total_assets")
    raise ValueError(pli)


def _avg(years_data, years, pli, averaging):
    if averaging == "weighted":
        nums = [_pli_parts(years_data[y], pli) for y in years]
        if any(a is None or b is None for a, b in nums) or sum(b for _, b in nums) == 0:
            return None
        return sum(a for a, _ in nums) / sum(b for _, b in nums)
    vals = []
    for y in years:
        a, b = _pli_parts(years_data[y], pli)
        if a is None or not b:
            return None
        vals.append(a / b)
    return sum(vals) / len(vals)


def _wc_ratio(years_data, years):
    s = Fraction(0); r = Fraction(0)
    for y in years:
        d = years_data[y]
        if any(d.get(k) is None for k in ("inventory", "receivables", "payables")):
            return None
        s += d["inventory"] + d["receivables"] - d["payables"]; r += d["revenue"]
    return s / r if r else None


def _ratio_avg(years_data, years, field):
    """Σ항목 / Σ매출(지표의 가중평균과 같은 방식). 그 항목이 비어 있는 해는 분자·분모 모두 뺌."""
    ys = [y for y in years if years_data[y].get(field) is not None and years_data[y].get("revenue")]
    if not ys:
        return None
    return sum(years_data[y][field] for y in ys) / sum(years_data[y]["revenue"] for y in ys)


def _basis(tested_year):
    if tested_year >= 2021:
        b = ("국제조세조정에 관한 법률 제8조①, 시행령 제8조①·제14조·제15조①③④⑤⑥" + ("⑦" if tested_year >= 2022 else "")
             + ", 시행규칙 제6조①③·제7조①·제9조, 법 제2조①3호·영 제2조②(특수관계 50%)")
        if tested_year >= 2022:
            b += ", 시행규칙 별지 제1호서식 작성방법 10(정상사분위범위, 2022.3.18. 시행규칙부터)"
        return b
    return ("구 국제조세조정에 관한 법률 제5조①, 구 시행령 제4조·제5조·제6조①②④⑤⑨, 구 시행규칙 제2조·제2조의2 "
            "(2021.1.1. 전 개시 사업연도 — 조문 번호가 현행과 다름. 구 시행령 개정 부칙의 적용 시기는 대조하지 않음)")


def _parse(rows, years):
    문제, companies = [], {}
    seen = set()
    for i, r in enumerate(rows):
        cid = str(r.get("company_id") or "").strip()
        if not cid:
            문제.append(f"{i + 1}행 — company_id 없음"); continue
        try:
            y = int(str(r.get("year")).strip())
        except (TypeError, ValueError):
            문제.append(f"{i + 1}행({cid}) — year가 정수가 아님"); continue
        if (cid, y) in seen:
            문제.append(f"{cid} {y} — 회사×연도 중복"); continue
        seen.add((cid, y))
        rec = {}
        for k in NUM_COLS:
            try:
                rec[k] = _fr(r.get(k))
            except (ValueError, ArithmeticError):
                문제.append(f"{cid} {y} — {k} 숫자 아님: {r.get(k)!r}")
        if rec.get("revenue") is not None and rec["revenue"] < 0:
            문제.append(f"{cid} {y} — 매출이 음수")
        c = companies.setdefault(cid, {"company_id": cid, "years": {}, "meta": {}})
        c["years"][y] = rec
        for k in ("company_name", "country", "industry_code", "currency", "bvd_independence", "special_flag",
                  "manual_decision", "manual_reason", "evidence", "reviewer", "accounting_standard", "fiscal_year_end"):
            v = r.get(k)
            if v not in (None, "") and k not in c["meta"]:
                c["meta"][k] = str(v).strip()
        if rec.get("max_shareholder_pct") is not None:          # 연도마다 다르면 가장 큰 값(어느 해든 특수관계 수준이면 걸리게)
            c["meta"]["max_shareholder_pct"] = max(c["meta"].get("max_shareholder_pct", rec["max_shareholder_pct"]), rec["max_shareholder_pct"])
        if rec.get("relevant_segment_share") is not None:       # 가장 작은 값
            c["meta"]["relevant_segment_share"] = min(c["meta"].get("relevant_segment_share", rec["relevant_segment_share"]), rec["relevant_segment_share"])
        for k in ("manual_decision", "manual_reason"):          # 사람 판단은 어느 행에 적혀 있어도 받되, 회사 안에서 서로 다르면 오류
            v = str(r.get(k) or "").strip()
            if v and c["meta"].get(k) and c["meta"][k] != v:
                문제.append(f"{cid} — {k}가 행마다 다름({c['meta'][k]!r} / {v!r})")
    if not companies:
        문제.append("후보 행이 없음")
    for need in ("company_name", "country", "industry_code"):
        miss = [c for c, v in companies.items() if need not in v["meta"]]
        if miss:
            문제.append(f"{need} 없음: {', '.join(miss[:5])}")
    return 문제, companies


def _screen_company(c, years, sc, tested, pli):
    """회사 하나를 모든 스크린으로 평가 → {스크린: (상태, 사유)}. 상태: 통과·탈락·표시·검토 필요·건너뜀."""
    m, yd = c["meta"], c["years"]
    out = {}
    sh = m.get("max_shareholder_pct") or Fraction(0)
    out["S1a"] = ("탈락", f"최대주주 {float(sh):.0f}% ≥ 50% — 법정 특수관계 수준(법 제2조①3호·영 제2조②), 끌 수 없음") if sh >= 50 else ("통과", "")
    ind = (m.get("bvd_independence") or "").upper()
    lim = sc["independence_pct"]
    if lim is None:
        out["S1b"] = ("건너뜀", "꺼짐")
    elif sh >= 50:
        out["S1b"] = ("통과", "S1a에서 처리")
    elif sh >= lim or ind in [x.upper() for x in sc["independence_bvd_reject"]]:
        out["S1b"] = ("탈락", f"독립성 지표 {ind or '-'}·최대주주 {float(sh):.0f}% — 관행 기준 {lim}%")
    else:
        out["S1b"] = ("통과", "")
    have = [y for y in years if y in yd and yd[y].get("revenue") is not None and yd[y].get("operating_profit") is not None]
    out["S2"] = ("통과", "") if len(have) == len(years) else ("탈락", f"분석 연도 {len(years)}개 중 {len(have)}개만 매출·영업이익 있음")
    codes = sc["industry_codes"]
    if codes:
        code = m.get("industry_code", "")
        out["S3"] = ("통과", "") if code in [str(x) for x in codes] else ("탈락", f"업종코드 {code} — 탐색 조건({', '.join(map(str, codes))}) 밖")
    else:
        out["S3"] = ("건너뜀", "업종코드 조건 없음")
    if not have:
        for k in ("S4", "S5", "S6", "S7", "S8", "S9", "S10"):
            out[k] = ("건너뜀", "자료 없음")
    else:
        if sc["size_min"] is None and sc["size_max"] is None:
            out["S4"] = ("건너뜀", "규모 조건 없음")
        elif sc.get("_mixed_currency") and not sc.get("fx"):
            out["S4"] = ("건너뜀", "통화가 섞였는데 환율(fx) 없음 — 규모를 비교하지 않음")
        else:
            cur = m.get("currency", "")
            if sc.get("_mixed_currency") and cur not in (sc.get("fx") or {}):
                out["S4"] = ("건너뜀", f"통화 {cur or '(없음)'}의 환율이 fx에 없음 — 규모를 비교하지 않음")
                rate = None
            else:
                rate = Fraction(str((sc.get("fx") or {}).get(cur, 1)))
        if have and out.get("S4") is None:
            ar = sum(yd[y]["revenue"] for y in have) / len(have) * rate
            lo, hi = sc["size_min"], sc["size_max"]
            ok = (lo is None or ar >= Fraction(str(lo))) and (hi is None or ar <= Fraction(str(hi)))
            out["S4"] = ("통과", "") if ok else ("탈락", f"평균 매출 {float(ar):,.0f} — 규모 범위 밖")
        losses = sum(1 for y in have if yd[y]["operating_profit"] < 0)
        if sc["loss_years"] is None:
            out["S5"] = ("건너뜀", "꺼짐")
        elif losses >= sc["loss_years"]:
            out["S5"] = (("검토 필요", f"영업손실 {losses}개 연도 — 경제위기 손실기업 예외(영 제15조⑦) 적용 여부 검토") if sc["crisis_exception"]
                         else ("탈락", f"분석 연도 중 {losses}개 연도 영업손실"))
        else:
            out["S5"] = ("통과", "")
        for key, field, lim_key, label in (("S6", "rnd_expense", "rnd_max", "연구개발비/매출"), ("S7", "advertising_expense", "adv_max", "광고선전비/매출"),
                                           ("S9", "related_party_revenue", "related_max", "특수관계 매출/매출")):
            v = _ratio_avg(yd, have, field)
            if sc[lim_key] is None:
                out[key] = ("건너뜀", "꺼짐")
            elif v is None:
                out[key] = ("건너뜀", f"{field} 자료 없음")
            elif v > Fraction(str(sc[lim_key])):
                out[key] = ("탈락", f"{label} {_pct(v, 1)}% > {sc[lim_key] * 100:g}%")
            else:
                out[key] = ("통과", "")
        wc = _wc_ratio(yd, have)
        if sc["wc_band"] is None or wc is None or tested.get("_wc") is None:
            out["S8"] = ("건너뜀", "기준 없음" if sc["wc_band"] is None else "운전자본 자료 없음")
        elif abs(wc - tested["_wc"]) > Fraction(str(sc["wc_band"])):
            out["S8"] = ("표시", f"운전자본/매출 {_pct(wc, 1)}% — 분석대상 {_pct(tested['_wc'], 1)}%와 차이 큼(운전자본 조정 검토)")
        else:
            out["S8"] = ("통과", "")
        seg = m.get("relevant_segment_share")
        if sc["segment_min"] is None or seg is None:
            out["S10"] = ("건너뜀", "부문 자료 없음" if seg is None else "꺼짐")
        else:
            out["S10"] = ("통과", "") if seg >= Fraction(str(sc["segment_min"])) else ("탈락", f"해당 부문 비중 {float(seg) * 100:.0f}% < {sc['segment_min'] * 100:g}%")
    flag = (m.get("special_flag") or "").strip()
    out["S11"] = ("탈락", f"특수 상황: {flag}") if flag and flag.lower() in [f.lower() for f in sc["special_flags"]] else ("통과", "")
    return out


def _manual(c, decisions):
    d = decisions.get(c["company_id"])
    if d is None and c["meta"].get("manual_decision"):
        d = {"decision": c["meta"]["manual_decision"], "reason": c["meta"].get("manual_reason", ""),
             "evidence": c["meta"].get("evidence", ""), "reviewer": c["meta"].get("reviewer", "")}
    return d


def _run(companies, tested, years, tested_years, pli, averaging, sc, decisions, qmethod, wca, use_outlier_exclusion=False):
    rows = {}
    for cid, c in companies.items():
        res = _screen_company(c, years, sc, tested, pli)
        d = _manual(c, decisions)
        if d:
            dec = str(d.get("decision", "")).lower()
            if dec == "reject":
                res["S12"] = ("탈락", f"수동 탈락: {d['reason']}")
            elif dec == "accept":
                over = [k for k, (s, _) in res.items() if s == "탈락" and k != "S1a"]
                for k in over:
                    res[k] = ("통과(수동 채택)", res[k][1] + f" → 수동 채택: {d['reason']}")
                res["S12"] = ("채택", f"수동 채택: {d['reason']}")
        else:
            res["S12"] = ("통과", "")
        rows[cid] = res
    final = [cid for cid, r in rows.items() if not any(s == "탈락" for s, _ in r.values())]
    vals = {}
    for cid in final:
        v = _avg(companies[cid]["years"], years, pli, averaging)
        if v is None:
            rows[cid]["S2"] = ("탈락", f"{pli} 계산에 필요한 항목 없음")
            continue
        if wca:
            wc = _wc_ratio(companies[cid]["years"], years)
            if wc is None or tested.get("_wc") is None:
                rows[cid]["S8"] = ("탈락", "운전자본 조정을 하는데 재고·매출채권·매입채무 자료 없음")
                continue
            v = v - Fraction(str(wca["rate"])) * (wc - tested["_wc"])     # 운전자본 조정(단순형)
        vals[cid] = v
    final = [c for c in final if c in vals]
    stats = None
    if len(final) >= 2:
        xs = sorted(vals[c] for c in final)
        q1, q3 = _quantile(xs, Fraction(1, 4), qmethod), _quantile(xs, Fraction(3, 4), qmethod)
        k = Fraction(str(sc["outlier_k"]))
        out_ids = [c for c in final if vals[c] > q3 + k * (q3 - q1) or vals[c] < q1 - k * (q3 - q1)]
        for c in final:
            rows[c]["S13"] = ("표시", f"지표 {_pct(vals[c])}% — {sc['outlier_k']}×IQR 밖, 자동 탈락하지 않음(빼려면 수동 탈락에 사유)") if c in out_ids else ("통과", "")
        if use_outlier_exclusion and out_ids:
            final = [c for c in final if c not in out_ids]
            xs = sorted(vals[c] for c in final)
            q1, q3 = _quantile(xs, Fraction(1, 4), qmethod), _quantile(xs, Fraction(3, 4), qmethod)
        if len(final) >= 2:
            stats = {"n": len(final), "min": xs[0], "q1": q1, "med": _quantile(xs, Fraction(1, 2), "inclusive"), "q3": q3, "max": xs[-1],
                     "outliers": out_ids}
    tv = _avg(tested["years"], tested_years, pli, averaging if len(tested_years) > 1 else "weighted")
    return rows, final, vals, stats, tv


def comparable_screen(rows=None, file_path=None, column_map=None, tested_party=None, analysis_years=None, tested_year=None,
                      pli="OM", averaging="weighted", tested_years=None, screens=None, manual_decisions=None, search_log=None,
                      quartile_method="inclusive", wca=None, multi_year_reason=None, op_source="reported", fx=None, sensitivity=True):
    문제 = []
    if pli not in PLI:
        문제.append(f"pli — {', '.join(PLI)} 중 하나")
    if averaging not in ("weighted", "simple"):
        문제.append("averaging — 'weighted'(Σ분자/Σ분모, 기본) 또는 'simple'(연도별 지표의 산술평균)")
    if quartile_method not in ("inclusive", "exclusive"):
        문제.append("quartile_method — 'inclusive' 또는 'exclusive'")
    if op_source not in ("reported", "recalc"):
        문제.append("op_source — 'reported'(보고 영업이익) 또는 'recalc'(매출−매출원가−판관비)")
    if not isinstance(analysis_years, list) or not analysis_years or not all(isinstance(y, int) for y in analysis_years):
        문제.append("analysis_years — 비교대상 분석 연도 목록(예: [2022, 2023, 2024])")
    if not isinstance(tested_year, int) or not (2016 <= tested_year <= 2026):
        문제.append("tested_year — 검토 대상 사업연도(2016~2026)")
    if not isinstance(tested_party, dict) or not isinstance(tested_party.get("is_resident"), bool) or not isinstance(tested_party.get("years"), dict):
        문제.append("tested_party — {name, is_resident(국내 법인이면 true, 국외특수관계인이면 false — 회사 이름으로 추측하지 않음), years: {연도: {revenue, cogs, opex, operating_profit, ...}}}")
    sc = dict(DEFAULT_SCREENS)
    for k, v in (screens or {}).items():
        if k not in DEFAULT_SCREENS:
            문제.append(f"screens.{k} — 알 수 없는 기준(가능: {', '.join(DEFAULT_SCREENS)})")
        else:
            sc[k] = v
    if sc["independence_pct"] is not None and (not isinstance(sc["independence_pct"], (int, float)) or sc["independence_pct"] > 50):
        문제.append(f"screens.independence_pct={sc['independence_pct']} — 50 이하(50% 이상 소유는 법정 특수관계, 법 제2조①3호·영 제2조②: 이보다 느슨하게 둘 수 없음)")
    if sc["loss_years"] is not None and (not isinstance(sc["loss_years"], int) or isinstance(sc["loss_years"], bool) or sc["loss_years"] < 1):
        문제.append(f"screens.loss_years={sc['loss_years']!r} — 1 이상의 정수(손실 연도 수), 끄려면 None")
    if wca is not None and (not isinstance(wca, dict) or not isinstance(wca.get("rate"), (int, float)) or not str(wca.get("rate_basis", "")).strip()):
        문제.append("wca — {rate: 이자율(소수), rate_basis: 금리 근거(예: 'USD 1년 SOFR + 스프레드')} — 근거 없는 금리로는 조정하지 않음")
    decisions = {}
    for i, d in enumerate(manual_decisions or []):
        if not isinstance(d, dict) or str(d.get("decision", "")).lower() not in ("accept", "reject") or not d.get("company_id"):
            문제.append(f"manual_decisions[{i}] — {{company_id, decision: accept|reject, reason, evidence, reviewer}}"); continue
        if not str(d.get("reason", "")).strip():
            문제.append(f"manual_decisions[{i}]({d['company_id']}) — reason 없음: 사람의 판단은 사유가 있어야 반영(시행규칙 제7조①7호)"); continue
        decisions[str(d["company_id"]).strip()] = d
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    try:
        raw = load_rows(file_path, rows, column_map)
    except (OSError, ValueError, StopIteration) as e:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"후보 목록을 읽지 못함: {e}"]}
    p2, companies = _parse(raw, analysis_years)
    for cid, c in companies.items():
        md = c["meta"].get("manual_decision")
        if md and cid not in decisions and md.lower() not in ("accept", "reject"):
            p2.append(f"{cid} — manual_decision={md!r}: accept 또는 reject")
        if c["meta"].get("manual_decision") and not c["meta"].get("manual_reason") and cid not in decisions:
            p2.append(f"{cid} — manual_decision은 있는데 manual_reason 없음(사유 없는 사람 판단은 반영하지 않음)")
    tested_years = tested_years or analysis_years
    tested = {"years": {}}
    if not p2:
        for y in tested_years:
            src = tested_party["years"].get(y, tested_party["years"].get(str(y)))
            if not isinstance(src, dict):
                p2.append(f"tested_party.years — {y}년 자료 없음"); continue
            try:
                tested["years"][y] = {k: _fr(src.get(k)) for k in NUM_COLS}
            except (ValueError, ArithmeticError):
                p2.append(f"tested_party.years[{y}] — 숫자 아님")
    if p2:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": p2}
    for c in list(companies.values()) + [tested]:
        for y in c["years"].values():
            y["_op_source"] = op_source
    tested["_wc"] = _wc_ratio(tested["years"], tested_years) if all(
        tested["years"][y].get(k) is not None for y in tested_years for k in ("inventory", "receivables", "payables")) else None
    currencies = {c["meta"].get("currency", "") for c in companies.values()}
    sc["_mixed_currency"] = len(currencies) > 1
    sc["fx"] = fx

    경고 = []
    # S0b 영업이익 대사(표시)
    대사 = []
    for cid, c in companies.items():
        for y, d in c["years"].items():
            if None not in (d.get("revenue"), d.get("cogs"), d.get("opex"), d.get("operating_profit")) and d["revenue"]:
                gap = abs(d["operating_profit"] - (d["revenue"] - d["cogs"] - d["opex"])) / d["revenue"]
                if gap > Fraction(str(sc["op_tolerance"])):
                    대사.append({"company_id": cid, "연도": y, "차이_매출대비%": _pct(gap, 2)})
    if 대사:
        경고.append(f"보고 영업이익과 (매출−매출원가−판관비)가 매출의 {sc['op_tolerance'] * 100:g}% 넘게 다른 행 {len(대사)}개 — 기타영업손익이 섞였는지 확인, "
                  "op_source='recalc'면 재계산 값으로 지표 계산(영 제8조①1호, 시행규칙 제6조③ 같은 기준 측정)")

    rows_res, final, vals, stats, tv = _run(companies, tested, analysis_years, tested_years, pli, averaging, sc, decisions, quartile_method, wca)
    if len(analysis_years) > 1 and not (isinstance(multi_year_reason, dict) and multi_year_reason.get("code") in (1, 2, 3) and str(multi_year_reason.get("text", "")).strip()):
        경고.append("다년도 자료를 쓰는데 multi_year_reason 없음 — 다년도 자료는 요건이 있을 때 쓸 수 있음(시행규칙 제9조 1호 경기 변동·2호 사업전략·3호 그 밖의 합리적 사유, "
                  "구법 구 시행령 제6조⑨). 개별기업보고서 Ⅱ-11을 채울 수 없음")
    if len(tested_years) != len(analysis_years) or set(tested_years) != set(analysis_years):
        경고.append(f"분석대상 기간 {tested_years}과 비교대상 기간 {analysis_years}이 다름 — 기간을 맞추거나 다르게 쓴 이유를 보고서에 적어야 함")
    stds = {c["meta"].get("accounting_standard") for c in companies.values() if c["meta"].get("accounting_standard")}
    if len(stds) > 1:
        경고.append(f"회계기준이 섞임({', '.join(sorted(stds))}) — 판매장려금·매출할인·외환손익 분류를 같은 기준으로(시행규칙 제6조③1호), 회계기준 차이 조정(제7조①8호)")
    if sc["_mixed_currency"] and not fx and (sc["size_min"] is not None or sc["size_max"] is not None):
        경고.append("통화가 섞였는데 환율(fx) 없음 — 규모 기준(S4)을 건너뜀. 지표는 비율이라 그대로 계산")
    if not search_log:
        경고.append("search_log 없음 — 데이터베이스 이름·추출일·검색 단계별 조건과 남은 수를 넣지 않으면 앞단 탐색 과정을 재현할 수 없음(개별기업보고서 Ⅱ-12)")

    if len(final) < 2:
        return {"error": "비교대상이 둘 미만 — 정상가격 범위를 산정할 수 없음(시행령 제15조⑤: 둘 이상의 거래)",
                "탈락_매트릭스": _matrix(companies, rows_res), "깔때기": _funnel(companies, rows_res), "경고": 경고, "영업이익_대사": 대사}
    if len(final) <= 3:
        경고.append(f"최종 비교대상 {len(final)}개 — 사분위 범위의 의미가 약함([관행], OECD 3.57)")
    inside = stats["q1"] <= tv <= stats["q3"]
    시나리오 = []
    if sensitivity:
        def scen(name, **kw):
            sc2 = dict(sc); sc2.update(kw.pop("sc", {}))
            r2, f2, v2, s2, t2 = _run(companies, tested, kw.get("years", analysis_years), kw.get("tyears", tested_years), pli, averaging, sc2, decisions,
                                      kw.get("qm", quartile_method), kw.get("wca", wca), kw.get("excl", False))
            if s2 is None:
                시나리오.append({"시나리오": name, "최종_수": len(f2), "범위": "비교대상 둘 미만"}); return
            시나리오.append({"시나리오": name, "최종_수": s2["n"], "제1사분위%": _pct(s2["q1"]), "중위값%": _pct(s2["med"]), "제3사분위%": _pct(s2["q3"]),
                         "분석대상%": _pct(t2), "범위_안": s2["q1"] <= t2 <= s2["q3"]})
        scen("A 기본")
        if sc["independence_pct"] is not None and sc["independence_pct"] < 50:
            scen("B 독립성 관행 기준 끔(법정 50%만)", sc={"independence_pct": None})
        if sc["loss_years"] is not None:
            scen("C 손실기업 포함", sc={"loss_years": None})
        if len(analysis_years) > 1:
            last = max(analysis_years)
            if last in tested["years"]:
                scen(f"D {last} 단년(기준도 그 해 자료로 다시 적용)", years=[last], tyears=[last])
        if wca is None and tested["_wc"] is not None:
            scen("E 운전자본 조정 5%(예시 금리)", wca={"rate": 0.05})
        scen("F 사분위 계산법 " + ("exclusive" if quartile_method == "inclusive" else "inclusive"), qm="exclusive" if quartile_method == "inclusive" else "inclusive")
        if stats["outliers"]:
            scen("G 이상치 제외", excl=True)
        if len({s.get("범위_안") for s in 시나리오 if "범위_안" in s}) > 1:
            경고.insert(0, "선정 기준에 민감 — 시나리오에 따라 범위 안/밖 결론이 뒤집힘. 기준 선택 이유를 보고서에 밝히고 과세당국 재산정 가능성(법 제7조①)을 검토")

    final_rows = []
    for cid in sorted(final, key=lambda c: vals[c]):
        c = companies[cid]
        final_rows.append({"company_id": cid, "이름": c["meta"].get("company_name"), "국가": c["meta"].get("country"), "업종": c["meta"].get("industry_code"),
                           "연도별": {y: {"매출": float(c["years"][y]["revenue"]), "영업이익": float(c["years"][y]["operating_profit"]),
                                        "지표%": _pct(_avg(c["years"], [y], pli, "weighted"))} for y in analysis_years},
                           ("가중평균%" if averaging == "weighted" else "평균%"): _pct(vals[cid]),
                           "운전자본/매출%": _pct(_wc_ratio(c["years"], analysis_years))})
    결과 = {"후보_수": len(companies), "최종_수": len(final), "지표": {"종류": pli, "뜻": PLI[pli], "평균방식": averaging, "연도": analysis_years},
          "범위": {"제1사분위%": _pct(stats["q1"]), "중위값%": _pct(stats["med"]), "제3사분위%": _pct(stats["q3"]), "최솟값%": _pct(stats["min"]),
                 "최댓값%": _pct(stats["max"]), "계산법": quartile_method}, "분석대상_값%": _pct(tv), "범위_안": inside,
          "이상치_표시": stats["outliers"]}
    alr = {"comparables": [{"이름": companies[c]["meta"].get("company_name", c), "값": float(vals[c])} for c in sorted(final, key=lambda c: vals[c])],
           "tested_value": float(tv), "quartile_method": quartile_method, "tested_is_resident": tested_party["is_resident"],
           "base_amount_안내": "다년 평균 지표를 썼으면 어느 해 매출(지표 분모)을 곱할지 정해서 base_amount로 넣음 — 연도별 배분은 따로"}
    if tested_year >= 2021:
        alr["year"] = tested_year
    부록 = {"탐색_조건": {"search_log": search_log, "적용_기준": _criteria(sc, analysis_years, pli, averaging, quartile_method)},
          "단계별_탈락": _funnel(companies, rows_res), "최종_비교대상_재무_요약": final_rows,
          "차이_조정": ({"운전자본_조정": "단순형: 조정 지표 = 지표 − 이자율 × (비교대상 운전자본/매출 − 분석대상 운전자본/매출)", "이자율": wca["rate"],
                     "이자율_근거": wca["rate_basis"], "분석대상_운전자본/매출%": _pct(tested["_wc"])} if wca else "하지 않음 — 차이가 지표에 영향을 주면 합리적으로 조정해야 함(영 제15조④)"),
          "다년도_사유": multi_year_reason,
          "개별기업보고서_연결": {"Ⅱ-11": "다년도 분석 사유(multi_year_reason)", "Ⅱ-12": "탐색 조건·단계별 탈락·최종 비교대상 재무 요약",
                           "Ⅱ-13": "차이 조정", "Ⅱ-15": "범위·분석대상 값·판정"}}
    판단 = [{"항목": "선정", "결론": f"후보 {len(companies)}개 중 {len(final)}개 선정", "근거": "시행규칙 제7조①5호·7호(외부 비교대상 수집·선정)" if tested_year >= 2021 else "구 시행규칙 제2조의2"},
          {"항목": "범위", "결론": f"{PLI[pli]} 사분위 범위 {_pct(stats['q1'])}% ~ {_pct(stats['q3'])}%, 분석대상 {_pct(tv)}% → " + ("범위 안" if inside else "범위 밖"),
           "근거": ("시행령 제15조⑤⑥, 시행규칙 별지 제1호서식 작성방법 10(정상사분위범위)" if tested_year >= 2022 else "시행령 제15조⑤⑥" if tested_year >= 2021 else "구 시행령 제6조④⑤")}]
    return {"결과": 결과, "탈락_매트릭스": _matrix(companies, rows_res), "최종_비교대상": final_rows, "민감도": 시나리오,
            "arm_length_range_입력": alr, "보고서_부록": 부록, "영업이익_대사": 대사, "경고": 경고, "판단": 판단, "근거": _basis(tested_year),
            "주의": ["데이터베이스 검색(모집단·업종·키워드)과 회사별 기능·거래단계 비교는 이 도구가 하지 않음 — 정성 판단은 manual_decisions에 사유와 함께",
                   "기준값은 [법정](특수관계 50%, 둘 이상)과 [관행](나머지)으로 나뉨 — [관행] 값은 바꿀 수 있고 선택 이유를 보고서에 적어야 함",
                   "운전자본 조정은 단순형 — OECD 지침 3장 부속서의 정확한 식과 금리 선택은 확인 필요(OECD 3.50·3.52: 신뢰성을 높일 때만)",
                   "과세당국은 다른 데이터베이스·다른 검색으로 다시 산정할 수 있음(법 제7조①, 제16조⑦)"]}


def _criteria(sc, years, pli, averaging, qm):
    out = [{"기준": "S1a 독립성", "값": "최대주주 50% 이상 탈락", "성격": "[법정] 법 제2조①3호·영 제2조②"}]
    for k, label in (("independence_pct", "S1b 독립성"), ("loss_years", "S5 지속 손실(연도 수)"), ("rnd_max", "S6 연구개발비/매출 상한"),
                     ("adv_max", "S7 광고선전비/매출 상한"), ("related_max", "S9 특수관계 매출 상한"), ("segment_min", "S10 해당 부문 비중 하한"), ("outlier_k", "S13 이상치 IQR 배수")):
        out.append({"기준": label, "값": sc[k] if sc[k] is not None else "꺼짐", "성격": PRACTICE.get(k, "[관행]")})
    out += [{"기준": "S3 업종 코드", "값": sc["industry_codes"] or "꺼짐", "성격": "[관행] 데이터베이스 검색 조건 재확인"},
            {"기준": "S4 규모(평균 매출)", "값": [sc["size_min"], sc["size_max"]], "성격": "[관행] OECD 3.43"},
            {"기준": "S11 특수 상황", "값": sc["special_flags"], "성격": "[관행] OECD 3.43"},
            {"기준": "지표·기간", "값": f"{pli} {averaging} {years}, 사분위 {qm}", "성격": "영 제8조①, 시행규칙 제9조"}]
    return out


def _matrix(companies, rows_res):
    out = []
    for cid, r in rows_res.items():
        row = {"company_id": cid, "이름": companies[cid]["meta"].get("company_name")}
        for k in SCREEN_NAMES:
            if k in r:
                s, why = r[k]
                row[k] = s + (f": {why}" if why and s != "통과" else "")
        fails = [k for k in FUNNEL_ORDER if k in r and r[k][0] == "탈락"]
        row["최종"] = f"탈락({', '.join(fails)})" if fails else "선정"
        out.append(row)
    return out


def _funnel(companies, rows_res):
    left = len(companies)
    out = [{"단계": "후보", "탈락": 0, "남음": left}]
    gone = set()
    for k in FUNNEL_ORDER:
        n = sum(1 for cid, r in rows_res.items() if cid not in gone and k in r and r[k][0] == "탈락")
        gone |= {cid for cid, r in rows_res.items() if k in r and r[k][0] == "탈락"}
        if n:
            left -= n
            out.append({"단계": f"{k} {SCREEN_NAMES[k]}", "탈락": n, "남음": left})
    return out
