"""비교대상 기업 선정(스크리닝) — 유료 데이터베이스에서 내보낸 후보 목록에 선정 기준을 재현 가능하게 적용. Claude 작성(2026-11-14).

이 도구가 메우는 고리: 데이터베이스 추출 목록 → [기준 적용·탈락 사유·다년 가중평균·차이 조정·민감도] → arm_length_range → 개별기업보고서 Ⅱ-11·12·13·15.
데이터베이스 검색 자체(모집단·업종·키워드)와 회사별 기능 비교(정성 판단)는 하지 않는다 — 정성 판단은 사람이 사유와 함께 넣어야만 반영한다.

근거(로컬 보관 법제처 원문 대조: 국조법 2016·2020·2026 시행본, 시행령 2016.2.5.·2020.8.12.·2021.2.17.·2026.1.2., 시행규칙 2016.4.6.·2020.3.13.·2021.3.16.·2022.3.18.·2025.3.21.):
- 2021.1.1. 이후 개시 사업연도(전부개정 시행령 부칙 제3조): 법 제8조①, 영 제8조①(거래순이익률 지표)·제14조(선택 기준·분석요소)·제15조①(분석 절차)·③(다년도)·④(차이 조정)·
  ⑤(둘 이상의 거래로 정상가격 범위)·⑥(범위 밖 기준점)·⑦(경제위기 손실기업, 2022.2.15. 신설), 시행규칙 제6조①③·제7조①·제9조,
  시행규칙 별지 제1호서식(거래가격 조정신고서) 작성방법 10 — 2022.3.18. 시행규칙부터 비교대상 수익성지표 값의 '정상사분위범위' 기재.
- 2016~2020 사업연도: 구 법 제5조①, 구 영 제4조(지표)·제5조(선택 기준)·제6조(분석 절차·범위·다년도), 구 시행규칙 제2조·제2조의2.
- 특수관계(독립성의 법정 하한): 법 제2조①3호, 영 제2조② — 의결권 있는 주식 50% 이상 직·간접 소유.
- 관행 기준값(독립성 %, 연구개발·광고 상한, 손실 연도 수, 이상치 배수 등)은 이 도구에 두지 않는다(0.61.0~) — screens로 받은 값만 적용하고 [관행]으로 표시.
  값·출처는 조문 MCP transfer_pricing_guide. screens가 없으면 법정 기준(S1a 50%, 둘 이상)만.
"""
import csv
import os
from fractions import Fraction

from .calc_tp import _quantile, quartile_sensitivity, QM_ALL, norm_qm, median_of, method_info

SCREEN_NAMES = {
    "S1a": "독립성(법정 하한 50%)", "S1b": "독립성(관행)", "S2": "자료 충분성", "S3": "업종 코드", "S4": "규모",
    "S5": "지속 손실", "S6": "연구개발 강도", "S7": "광고 강도", "S8": "운전자본 강도", "S9": "특수관계 매출", "S9b": "특수관계 매입",
    "S10": "해당 부문 비중", "S11": "특수 상황", "S12": "정성 판단(사람)", "S13": "이상치",
}
FUNNEL_ORDER = ["S1a", "S1b", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S9b", "S10", "S11", "S12"]
# 선정 기준 키 — 관행·우리 규칙 값은 두지 않는다(None = 그 기준 끔). 값은 조문 MCP transfer_pricing_guide(비교대상 선정 기준)가 주는 것을 screens로 받는다.
# 이 도구가 스스로 적용하는 것은 법정 기준뿐: S1a 최대주주 50% 이상(법정 준용), 비교대상 둘 이상(시행령 제15조⑤).
DEFAULT_SCREENS = {
    "independence_pct": None,                   # 최대주주 지분 % 상한(50 이하) — S1b
    "independence_bvd_reject": None,            # 데이터베이스 독립성 지표 중 탈락 등급 목록(예: ["C","D","U"]) — S1b
    "industry_codes": None,                     # 업종 코드 목록 — S3
    "size_min": None, "size_max": None,         # 평균 매출(입력 통화) — S4
    "loss_years": None, "crisis_exception": False,   # 분석 연도 중 영업손실 연도 수 — S5
    "loss_action": "review",                    # S5에 걸리면: review(사람 확인) / exclude(탈락)
    "require_all_years": False,                 # True면 분석 연도 모두에 자료가 있어야 함 — S2
    "rnd_max": None, "adv_max": None,           # 연구개발비/매출·광고선전비/매출 상한(소수) — S6·S7
    "wc_band": None,                            # 운전자본/매출 차이 표시 폭(소수) — S8
    "related_max": None, "segment_min": None,   # 특수관계 매출/매출 상한·해당 부문 비중 하한(소수) — S9·S10
    "related_purchase_max": None,               # 특수관계 매입/매출원가 상한(소수) — S9b
    "special_flags": None,                      # 탈락시킬 special_flag 값 목록 — S11
    "outlier_k": None,                          # 이상치 표시 IQR 배수 — S13(표시만)
    "sample_min": None, "spread_ratio": None,   # 표본·편차 경고(표시만)
    "op_tolerance": 0.005,                      # 영업이익 대사 허용 오차(매출 대비) — 데이터 검산용, 선정 기준 아님
}
PRACTICE_KEYS = [k for k in DEFAULT_SCREENS if k not in ("crisis_exception", "loss_action", "require_all_years", "op_tolerance")]
NO_PRACTICE = "관행 기준 미적용 — 조문 MCP transfer_pricing_guide(비교대상 선정 기준)의 값을 screens로 넣으세요. 지금은 법정 기준(최대주주 50% 이상, 비교대상 둘 이상)만 적용"
SCREEN_NOTE = {"independence_pct": "[관행] 최대주주 지분 상한", "rnd_max": "[관행] 연구개발비/매출 상한", "adv_max": "[관행] 광고선전비/매출 상한",
               "related_max": "[관행] 특수관계 매출 상한", "related_purchase_max": "[관행] 특수관계 매입/매출원가 상한", "segment_min": "[관행] 해당 부문 비중 하한",
               "loss_years": "[관행] 손실 연도 수 — loss_action=review면 사람 확인, exclude면 탈락", "outlier_k": "[관행] 이상치 표시, 자동 탈락하지 않음"}
PLI = {"OM": "매출액 대비 거래순이익(영 제8조①1호)", "ROA": "자산 대비 거래순이익(영 제8조①2호)",
       "NCP": "매출원가·영업비용 대비 거래순이익(영 제8조①3호)", "BERRY": "영업비용 대비 매출총이익(영 제8조①4호)"}
NO_INDEP = "독립성 자료 없음(최대주주 지분율·독립성 지표)"
SRC_COLS = ("rcept_no", "fs_div", "accounting_standard", "collected_at", "source")   # 개별기업보고서 Ⅱ-12 출처 칸
NUM_COLS = ["revenue", "cogs", "opex", "operating_profit", "total_assets", "inventory", "receivables", "payables",
            "rnd_expense", "advertising_expense", "related_party_revenue", "related_party_purchase", "max_shareholder_pct", "relevant_segment_share", "employees"]


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
        if tested_year == 2021:
            b += " — 제15조⑦(2022.2.15. 신설)은 2022.2.15. 이후 신고하거나 결정·경정하는 경우부터라(대통령령 제32423호 부칙 제5조) 2021 사업연도분도 그 뒤에 신고하면 적용"
        if tested_year >= 2022:
            b += ", 시행규칙 별지 제1호서식 작성방법 10(정상사분위범위, 2022.3.18. 시행규칙부터)"
        return b
    return ("구 국제조세조정에 관한 법률 제5조①, 구 시행령 제4조·제5조·제6조①②④⑤⑨, 구 시행규칙 제2조·제2조의2 "
            "(2021.1.1. 전 개시 사업연도 — 조문 번호가 현행과 다름. 구 시행령 제6조④⑤를 거주자의 신고에도 쓰게 한 개정(대통령령 제30405호)은 부칙 제2조에 따라 2020.1.1. 이후 개시 과세연도분부터, "
            "분석절차는 구 시행규칙 제2조의2①(2019.3.20.부터 ②))")


def _parse(rows):
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
        rec["_src"] = {k: str(r[k]).strip() for k in SRC_COLS if r.get(k) not in (None, "")}
        c["years"][y] = rec
        for k in ("company_name", "country", "industry_code", "currency", "bvd_independence", "special_flag",
                  "manual_decision", "manual_reason", "evidence", "reviewer", "accounting_standard", "fiscal_year_end", "control_note"):
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


def _screen_company(c, years, sc, tested):
    """회사 하나를 모든 스크린으로 평가 → {스크린: (상태, 사유)}. 상태: 통과·탈락·표시·검토 필요·건너뜀."""
    m, yd = c["meta"], c["years"]
    out = {}
    ind = (m.get("bvd_independence") or "").upper()
    if m.get("max_shareholder_pct") is None and not ind:
        # 독립성 자료(최대주주 지분율·데이터베이스 독립성 지표)가 하나도 없는 후보 — 0%로 보고 '통과'시키지 않는다(2026-11-20).
        # 지배·계열 관계 서술(control_note)이 있으면 사람 확인, 없으면 건너뜀. 자료가 없다는 이유로 떨어뜨리지는 않음.
        note = (m.get("control_note") or "").strip()
        if note:
            out["S1a"] = ("검토 필요", f"{NO_INDEP} · 지배·계열 관계 서술 있음({note}) — 지분율이 50% 이상인지 확인(법 제2조①3호·영 제2조②)")
        else:
            out["S1a"] = ("건너뜀", f"{NO_INDEP} — 독립성을 확인하지 못함")
        out["S1b"] = ("건너뜀", "꺼짐") if sc["independence_pct"] is None and not sc["independence_bvd_reject"] else ("건너뜀", f"{NO_INDEP}")
        return _screen_rest(m, yd, years, sc, tested, out)
    sh = m.get("max_shareholder_pct") or Fraction(0)
    out["S1a"] = ("탈락", f"최대주주 {float(sh):.0f}% ≥ 50% — [법정 준용] 거래 당사자 간 특수관계 기준(법 제2조①3호·영 제2조②)을 비교대상에 준용, 특수관계기업 간 거래 자료는 비교대상 불가(기본통칙 8-0…1), 끌 수 없음") if sh >= 50 else ("통과", "")
    lim = sc["independence_pct"]
    if lim is None and sc["independence_bvd_reject"]:
        lim = 50
    if lim is None:
        out["S1b"] = ("건너뜀", "꺼짐")
    elif sh >= 50:
        out["S1b"] = ("통과", "S1a에서 처리")
    elif sh >= lim or ind in [x.upper() for x in (sc["independence_bvd_reject"] or [])]:
        out["S1b"] = ("탈락", f"독립성 지표 {ind or '-'}·최대주주 {float(sh):.0f}% — 관행 기준 {lim}%")
    else:
        out["S1b"] = ("통과", "")
    return _screen_rest(m, yd, years, sc, tested, out)


def _screen_rest(m, yd, years, sc, tested, out):
    """S2~S11 — 독립성(S1a·S1b) 뒤의 스크린."""
    have = [y for y in years if y in yd and yd[y].get("revenue") is not None and yd[y].get("operating_profit") is not None]
    if len(have) == len(years):
        out["S2"] = ("통과", "")
    elif sc.get("require_all_years") or not have:
        out["S2"] = ("탈락", f"분석 연도 {len(years)}개 중 {len(have)}개만 매출·영업이익 있음")
    else:
        out["S2"] = ("표시", f"분석 연도 {len(years)}개 중 {len(have)}개({', '.join(map(str, have))})만 자료 — 있는 연도로 평균(연도별 비교기업 갱신 허용)")
    codes = sc["industry_codes"]
    if codes:
        code = m.get("industry_code", "")
        out["S3"] = ("통과", "") if code in [str(x) for x in codes] else ("탈락", f"업종코드 {code} — 탐색 조건({', '.join(map(str, codes))}) 밖")
    else:
        out["S3"] = ("건너뜀", "업종코드 조건 없음")
    if not have:
        for k in ("S4", "S5", "S6", "S7", "S8", "S9", "S9b", "S10"):
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
            if sc["crisis_exception"]:
                out["S5"] = ("검토 필요", f"[L2] 영업손실 {losses}개 연도 — 경제위기 손실기업 예외(영 제15조⑦) 적용 여부 검토")
            elif sc.get("loss_action") == "exclude":
                out["S5"] = ("탈락", f"[L2] 분석 연도 중 {losses}개 연도 영업손실")
            else:
                out["S5"] = ("검토 필요", f"[L2] 분석 연도 {len(have)}개 중 {losses}개 연도 영업손실 — 사람 확인(손실만으로 제외하지 않음, OECD 3.64~3.65)")
        elif losses:
            out["S5"] = ("표시", f"[L1] 영업손실 {losses}개 연도 — 표시만")
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
        # S9b 특수관계 매입 ÷ 매출원가 — 매입 금액과 매출원가가 함께 있는 해만. 기준값은 screens로만 받음(조문 MCP).
        pys = [y for y in have if yd[y].get("related_party_purchase") is not None and yd[y].get("cogs")]
        if sc["related_purchase_max"] is None:
            out["S9b"] = ("건너뜀", "꺼짐")
        elif not pys:
            out["S9b"] = ("건너뜀", "related_party_purchase·cogs 자료 없음")
        else:
            pv = sum(yd[y]["related_party_purchase"] for y in pys) / sum(yd[y]["cogs"] for y in pys)
            if pv > Fraction(str(sc["related_purchase_max"])):
                out["S9b"] = ("탈락", f"특수관계 매입/매출원가 {_pct(pv, 1)}% > {sc['related_purchase_max'] * 100:g}%")
            else:
                out["S9b"] = ("통과", "")
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
    out["S11"] = ("탈락", f"특수 상황: {flag}") if flag and flag.lower() in [f.lower() for f in (sc["special_flags"] or [])] else (("표시", f"특수 상황 {flag} — 기준(special_flags) 없음, 사람 확인") if flag else ("통과", ""))
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
        res = _screen_company(c, years, sc, tested)
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
    def yrs(cid):
        yd = companies[cid]["years"]
        have = [y for y in years if y in yd and yd[y].get("revenue") is not None and yd[y].get("operating_profit") is not None]
        return years if sc.get("require_all_years") else have
    for cid in final:
        v = _avg(companies[cid]["years"], yrs(cid), pli, averaging)
        if v is None:
            rows[cid]["S2"] = ("탈락", f"{pli} 계산에 필요한 항목 없음")
            continue
        if wca:
            wc = _wc_ratio(companies[cid]["years"], yrs(cid))
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
        out_ids = []
        if sc.get("outlier_k") is not None:
            k = Fraction(str(sc["outlier_k"]))
            out_ids = [c for c in final if vals[c] > q3 + k * (q3 - q1) or vals[c] < q1 - k * (q3 - q1)]
        for c in final:
            rows[c]["S13"] = (("표시", f"지표 {_pct(vals[c])}% — {sc['outlier_k']}×IQR 밖, 자동 탈락하지 않음(빼려면 수동 탈락에 사유)") if c in out_ids
                              else ("통과", "") if sc.get("outlier_k") is not None else ("건너뜀", "꺼짐"))
        if use_outlier_exclusion and out_ids:
            final = [c for c in final if c not in out_ids]
            xs = sorted(vals[c] for c in final)
            q1, q3 = _quantile(xs, Fraction(1, 4), qmethod), _quantile(xs, Fraction(3, 4), qmethod)
        if len(final) >= 2:
            stats = {"n": len(final), "min": xs[0], "q1": q1, "med": median_of(xs, qmethod), "q3": q3, "max": xs[-1],
                     "outliers": out_ids}
    tv = _avg(tested["years"], tested_years, pli, averaging if len(tested_years) > 1 else "weighted")
    return rows, final, vals, stats, tv


def comparable_screen(rows=None, file_path=None, column_map=None, tested_party=None, analysis_years=None, tested_year=None,
                      pli="OM", averaging="weighted", tested_years=None, screens=None, manual_decisions=None, search_log=None,
                      quartile_method="nts", wca=None, multi_year_reason=None, op_source="reported", fx=None, sensitivity=True):
    문제 = []
    if pli not in PLI:
        문제.append(f"pli — {', '.join(PLI)} 중 하나")
    if averaging not in ("weighted", "simple"):
        문제.append("averaging — 'weighted'(Σ분자/Σ분모, 기본) 또는 'simple'(연도별 지표의 산술평균)")
    if quartile_method not in QM_ALL:
        문제.append("quartile_method — 'nts'(국조법 기본통칙 8-15…1, 기본) · 'excel_inc'(엑셀 QUARTILE.INC, 0.60.x까지 기본 — 'inclusive'도 같음) · 'exclusive'(QUARTILE.EXC) · 'us'(26 CFR §1.482-1(e)(2)(iii)(C), 보간 없음)")
    quartile_method = norm_qm(quartile_method)
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
        문제.append(f"screens.loss_years={sc['loss_years']!r} — 1 이상의 정수(손실 연도 수), 끄려면 비워 두세요(null)")
    if sc.get("loss_action") not in ("review", "exclude"):
        문제.append(f"screens.loss_action={sc.get('loss_action')!r} — 'review'(사람 확인, 기본) 또는 'exclude'(탈락)")
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
    p2, companies = _parse(raw)
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

    no_indep = [cid for cid in companies if NO_INDEP in rows_res[cid]["S1a"][1]]
    if no_indep:
        review = sum(1 for cid in no_indep if rows_res[cid]["S1a"][0] == "검토 필요")
        경고.append(f"독립성 자료 없는 후보 {len(no_indep)}곳 — 최대주주 지분율·독립성 지표가 없어 독립성 스크린(S1a·S1b)을 적용하지 못함"
                  + (f"(그중 지배·계열 관계 서술이 있는 {review}곳은 '검토 필요')" if review else "") + ". 지분 구조를 따로 확인해야 함")
    if len(final) < 2:
        return {**({"안내": NO_PRACTICE} if not any(sc.get(k) not in (None, [], "") for k in PRACTICE_KEYS) else {}),
                "error": "비교대상이 둘 미만 — 정상가격 범위를 산정할 수 없음(시행령 제15조⑤: 둘 이상의 거래)",
                "탈락_매트릭스": _matrix(companies, rows_res), "깔때기": _funnel(companies, rows_res), "경고": 경고, "영업이익_대사": 대사}
    if len(final) <= 3:
        경고.append(f"최종 비교대상 {len(final)}개 — 사분위 범위의 의미가 약할 수 있음(OECD 3.57)")
    spread = stats["q3"] - stats["q1"]
    if (sc.get("sample_min") and len(final) < sc["sample_min"]) or (sc.get("spread_ratio") and stats["med"] != 0 and spread > Fraction(str(sc["spread_ratio"])) * abs(stats["med"])):
        경고.append(f"[우리 규칙] 표본 {len(final)}개, 사분위 폭 {_pct(spread)}%p(중위값 {_pct(stats['med'])}%) — 표본이 {sc.get('sample_min')}개 미만이거나 폭이 중위값의 {sc.get('spread_ratio')}배보다 크면 "
                  "편차 원인을 분석하고 영업 특성이 비슷한 비교대상 추가를 검토(판례는 조문 MCP transfer_pricing_cases)")
    t_loss = [y for y in tested_years if (tested["years"].get(y) or {}).get("operating_profit") is not None and tested["years"][y]["operating_profit"] < 0]
    if sc.get("loss_years") is not None and sc.get("loss_action") == "exclude" and t_loss:
        경고.insert(0, f"분석대상이 {t_loss}년 영업손실인데 손실 후보를 일괄 제외(loss_action=exclude) — 분석대상 손실 원인을 분석하고 손실 후보 중 비교 가능한 기업이 있는지 "
                      "사람이 확인(판례는 조문 MCP transfer_pricing_cases)")
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
            scen("B 독립성 관행 기준 끔(법정 50%만)", sc={"independence_pct": None, "independence_bvd_reject": None})
        if sc["loss_years"] is not None:
            if sc.get("loss_action") == "exclude":
                scen("C 손실기업 포함", sc={"loss_years": None})
            else:
                scen("C 지속 손실기업 제외", sc={"loss_action": "exclude"})
        if len(analysis_years) > 1:
            last = max(analysis_years)
            if last in tested["years"]:
                scen(f"D {last} 단년(기준도 그 해 자료로 다시 적용)", years=[last], tyears=[last])
        for alt in [m for m in ("nts", "excel_inc", "us") if m != quartile_method]:
            scen(f"F 사분위 계산법 {alt}", qm=alt)
        if stats["outliers"]:
            scen("G 이상치 제외", excl=True)
        if len({s.get("범위_안") for s in 시나리오 if "범위_안" in s}) > 1:
            경고.insert(0, "선정 기준에 민감 — 시나리오에 따라 범위 안/밖 결론이 뒤집힘. 기준 선택 이유를 보고서에 밝히고 과세당국 재산정 가능성(법 제7조①)을 검토")

    final_rows = []
    for cid in sorted(final, key=lambda c: vals[c]):
        c = companies[cid]
        have = [y for y in analysis_years if y in c["years"] and c["years"][y].get("revenue") is not None and c["years"][y].get("operating_profit") is not None]
        wcr = _wc_ratio(c["years"], have)
        final_rows.append({"company_id": cid, "이름": c["meta"].get("company_name"), "국가": c["meta"].get("country"), "업종": c["meta"].get("industry_code"),
                           "연도별": {y: {"매출": float(c["years"][y]["revenue"]), "영업이익": float(c["years"][y]["operating_profit"]),
                                        "지표%": _pct(_avg(c["years"], [y], pli, "weighted")),
                                        "출처_접수번호": c["years"][y]["_src"].get("rcept_no") or c["years"][y]["_src"].get("source") or "입력 없음",
                                        "재무제표_구분": {"OFS": "별도", "CFS": "연결"}.get(c["years"][y]["_src"].get("fs_div"), c["years"][y]["_src"].get("fs_div") or "입력 없음"),
                                        "회계기준": c["years"][y]["_src"].get("accounting_standard") or c["meta"].get("accounting_standard") or "입력 없음",
                                        "수집_기준_시점": c["years"][y]["_src"].get("collected_at") or (search_log or {}).get("collected_at") or "입력 없음"} for y in have},
                           "자료_연도": have,
                           ("가중평균%" if averaging == "weighted" else "평균%"): _pct(vals[cid]),
                           "운전자본/매출%": _pct(wcr) if wcr is not None else None})
    결과 = {**({"안내": NO_PRACTICE} if not any(sc.get(k) not in (None, [], "") for k in PRACTICE_KEYS) else {}), "후보_수": len(companies), "최종_수": len(final), "지표": {"종류": pli, "뜻": PLI[pli], "평균방식": averaging, "연도": analysis_years},
          "범위": {"제1사분위%": _pct(stats["q1"]), "중위값%": _pct(stats["med"]), "제3사분위%": _pct(stats["q3"]), "최솟값%": _pct(stats["min"]),
                 "최댓값%": _pct(stats["max"]), "계산법": quartile_method, "계산법_설명": _QM_NAME[quartile_method], "n": stats["n"], "조정점": "중위값",
                 "근거": method_info(quartile_method, stats["n"])["근거"]}, "분석대상_값%": _pct(tv), "범위_안": inside,
          "이상치_표시": stats["outliers"],
          "연도별_범위": _yearly(companies, final, analysis_years, tested, pli, quartile_method),
          "사분위_민감도": {m: {"이름": x["이름"], "제1사분위%": _pct(x["제1사분위"]), "중위값%": _pct(x["중위값"]), "제3사분위%": _pct(x["제3사분위"]), "범위_안": x["범위_안"]}
                       for m, x in quartile_sensitivity([vals[c] for c in final], tv).items()},
          "사람_확인": [{"company_id": cid, "이름": companies[cid]["meta"].get("company_name"), "사유": why}
                    for cid in final for k, (st, why) in rows_res[cid].items() if st == "검토 필요"]}
    multi_ok = len(analysis_years) > 1 and isinstance(multi_year_reason, dict) and multi_year_reason.get("code") in (1, 2, 3) and str(multi_year_reason.get("text", "")).strip()
    if len(analysis_years) == 1:
        결과["주_결과"] = "범위(단년)"
    elif multi_ok:
        결과["주_결과"] = "범위(다년 — multi_year_reason 입력, 서식 Ⅱ-11) · 단년_범위 함께"
    else:
        결과["주_결과"] = "단년_범위(서식 Ⅱ-11: 다년도는 수행한 경우에만 사유 기재 — 사유가 없어 단년을 주 결과로)"
    결과["단년_범위"] = 결과["연도별_범위"].get(tested_year, f"{tested_year}년이 분석 연도에 없음")
    v0 = None
    if wca:
        r0, f0, v0, s0, t0 = _run(companies, tested, analysis_years, tested_years, pli, averaging, sc, decisions, quartile_method, None)
        결과["조정_전_범위"] = ({"제1사분위%": _pct(s0["q1"]), "중위값%": _pct(s0["med"]), "제3사분위%": _pct(s0["q3"]), "n": s0["n"], "분석대상_값%": _pct(t0),
                            "범위_안": s0["q1"] <= t0 <= s0["q3"]} if s0 else "비교대상 둘 미만")
        결과["조정_후_범위"] = "범위(운전자본 조정 후)"
    alr = {"comparables": [{"이름": companies[c]["meta"].get("company_name", c), "값": float(vals[c])} for c in sorted(final, key=lambda c: vals[c])],
           "tested_value": float(tv), "quartile_method": quartile_method, "tested_is_resident": tested_party["is_resident"],
           "base_amount_안내": "다년 평균 지표를 썼으면 어느 해 매출(지표 분모)을 곱할지 정해서 base_amount로 넣음 — 연도별 배분은 따로"}
    if tested_year >= 2021:
        alr["year"] = tested_year
    부록 = {"탐색_조건": {"search_log": search_log, "적용_기준": _criteria(sc, analysis_years, pli, averaging, quartile_method, screens)},
          "단계별_탈락": _funnel(companies, rows_res), "최종_비교대상_재무_요약": final_rows,
          "차이_조정": ({"운전자본_조정": "단순형: 조정 지표 = 지표 − 이자율 × (비교대상 운전자본/매출 − 분석대상 운전자본/매출)", "이자율": wca["rate"],
                     "이자율_근거": wca["rate_basis"], "분석대상_운전자본/매출%": _pct(tested["_wc"]), "한계": WCA_LIMIT,
                     "적용_쪽": "비교대상(비교대상 지표를 분석대상 운전자본 수준에 맞춰 조정 — 분석대상 값은 그대로)",
                     "조정_전후": [{"이름": companies[c]["meta"].get("company_name", c), "조정_전%": _pct(v0[c]) if v0 and c in v0 else None, "조정_후%": _pct(vals[c])}
                               for c in sorted(final, key=lambda c: vals[c])]} if wca else "하지 않음 — 차이가 지표에 영향을 주면 합리적으로 조정해야 함(영 제15조④)"),
          "다년도_사유": multi_year_reason,
          "사람_판단": [{"company_id": cid, "이름": companies[cid]["meta"].get("company_name") if cid in companies else None, "결정": d.get("decision"), "사유": d.get("reason"),
                     "근거": d.get("evidence"), "검토자": d.get("reviewer")} for cid, d in decisions.items()],
          "Ⅱ-8_지표_선정_이유": tested_party.get("pli_reason") or "입력 필요 — tested_party.pli_reason(지표 선정 이유·선정하지 않은 방법의 이유)",
          "Ⅱ-9_분석대상_선정_이유": tested_party.get("selection_reason") or "입력 필요 — tested_party.selection_reason(분석대상 선정 이유)",
          "개별기업보고서_연결": {"Ⅱ-11": "다년도 분석 사유(multi_year_reason)", "Ⅱ-12": "탐색 조건·단계별 탈락·최종 비교대상 재무 요약(행별 접수번호·연결/별도·회계기준·수집 기준 시점)·사람 판단", "Ⅱ-8": "Ⅱ-8_지표_선정_이유", "Ⅱ-9": "Ⅱ-9_분석대상_선정_이유",
                           "Ⅱ-13": "차이 조정(적용 쪽·조정 전후 값)", "Ⅱ-15": "범위·분석대상 값·판정"}}
    판단 = [{"항목": "선정", "결론": f"후보 {len(companies)}개 중 {len(final)}개 선정", "근거": "시행규칙 제7조①5호·7호(외부 비교대상 수집·선정)" if tested_year >= 2021 else "구 시행규칙 제2조의2"},
          {"항목": "범위", "결론": f"{PLI[pli]} 사분위 범위 {_pct(stats['q1'])}% ~ {_pct(stats['q3'])}%, 분석대상 {_pct(tv)}% → " + ("범위 안" if inside else "범위 밖"),
           "근거": ("시행령 제15조⑤⑥, 시행규칙 별지 제1호서식 작성방법 10(정상사분위범위)" if tested_year >= 2022 else "시행령 제15조⑤⑥" if tested_year >= 2021 else "구 시행령 제6조④⑤")}]
    return {"결과": 결과, "탈락_매트릭스": _matrix(companies, rows_res), "최종_비교대상": final_rows, "민감도": 시나리오,
            "arm_length_range_입력": alr, "보고서_부록": 부록, "영업이익_대사": 대사, "경고": 경고, "판단": 판단, "근거": _basis(tested_year),
            "주의": ["데이터베이스 검색(모집단·업종·키워드)과 회사별 기능·거래단계 비교는 이 도구가 하지 않음 — 정성 판단은 manual_decisions에 사유와 함께",
                   "이 도구가 스스로 적용하는 기준은 법정(최대주주 50% 이상, 둘 이상)뿐 — [관행] 기준은 screens로 넣은 값만 적용(값·출처는 조문 MCP transfer_pricing_guide), 선택 이유를 보고서에 적어야 함",
                   "운전자본 조정 식은 OECD 이전가격지침(2022) 3장 부속서 예시와 같음 — 조정 지표 = 비교대상 지표 + (분석대상 (매출채권+재고−매입채무)/매출 − 비교대상 같은 비율) × 이자율(부속서 문단 6·7, 2026-11-15 원문 대조). "
                   "부속서와 다른 점: 부속서는 지표의 분모에 맞춰 운전자본 수준을 재라고 함(문단 6 a) — 이 도구는 지표가 원가·영업비용 기준이어도 매출 대비로 잼. 부속서 예시는 연도별 기말 잔액, 이 도구는 분석 연도 합계 비율(기말이 연중 수준을 대표하지 않으면 평균 — 문단 8). "
                   "이자율은 분석대상 당사자와 같은 시장의 상업적 기업에 적용되는 이자율(대개 상업 대출 금리), 운전자본이 음수면 다른 이자율이 맞을 수 있음(문단 8). 조정은 신뢰성을 높일 때만(문단 1, 3.50·3.52)",
                   WCA_LIMIT,
                   "연도별_범위를 함께 보고 연도마다 같은 기준을 쓸 것 — 다년도 분석 요건·경정 범위는 조문 MCP에서 확인",
                   "과세당국은 다른 데이터베이스·다른 검색으로 다시 산정할 수 있음(법 제7조①, 제16조⑦)"]}


WCA_LIMIT = ("운전자본 조정은 재고·매출채권·매입채무 수준 차이만 조정함 — 품목·거래단계·마케팅 기능 차이는 해소하지 못하므로 별도 근거·조정이 필요"
             "(판례는 조문 MCP transfer_pricing_cases)")


_QM_NAME = {"excel_inc": "excel_inc(엑셀 QUARTILE.INC, 위치 (n−1)q 보간 — 0.60.x까지 기본)", "exclusive": "exclusive(QUARTILE.EXC)",
            "us": "us(26 CFR §1.482-1(e)(2)(iii)(C), 보간 없음)",
            "nts": "nts(국조법 기본통칙 8-15…1 — 위치 (n+2)/4·(3n+2)/4, 소수 위치면 인접 두 값 평균)"}


def _yearly(companies, final, years, tested, pli, qm):
    """연도별 사분위 범위 — 그해 자료가 있는 최종 비교대상만(연도별로 비교기업이 달라도 됨)."""
    out = {}
    for y in years:
        xs = []
        for cid in final:
            yd = companies[cid]["years"]
            if y in yd:
                v = _avg(yd, [y], pli, "weighted")
                if v is not None:
                    xs.append(v)
        xs.sort()
        tvy = _avg(tested["years"], [y], pli, "weighted") if y in tested["years"] else None
        if len(xs) < 2:
            out[y] = {"n": len(xs), "범위": "비교대상 둘 미만"}
            continue
        q1, q3 = _quantile(xs, Fraction(1, 4), qm), _quantile(xs, Fraction(3, 4), qm)
        med = median_of(xs, qm)
        out[y] = {"n": len(xs), "제1사분위%": _pct(q1), "중위값%": _pct(med), "제3사분위%": _pct(q3),
                  "분석대상%": _pct(tvy) if tvy is not None else None, "범위_안": (q1 <= tvy <= q3) if tvy is not None else None}
    return out


def _criteria(sc, years, pli, averaging, qm, given=None):
    given = set(given or {})
    src = lambda k: "사용자 입력" if k in given else "입력 없음 — 꺼짐(값·출처는 조문 MCP transfer_pricing_guide)"
    out = [{"기준": "S1a 독립성", "값": "최대주주 50% 이상 탈락", "성격": "[법정 준용] 법 제2조①3호·영 제2조②(거래 당사자 간 기준을 비교대상에 준용)", "입력": "법정 — 항상 적용"}]
    for k, label in (("independence_pct", "S1b 독립성"), ("loss_years", "S5 지속 손실(연도 수)"), ("rnd_max", "S6 연구개발비/매출 상한"),
                     ("adv_max", "S7 광고선전비/매출 상한"), ("related_max", "S9 특수관계 매출 상한"), ("related_purchase_max", "S9b 특수관계 매입/매출원가 상한"), ("segment_min", "S10 해당 부문 비중 하한"), ("outlier_k", "S13 이상치 IQR 배수")):
        out.append({"기준": label, "값": sc[k] if sc[k] is not None else "꺼짐", "성격": SCREEN_NOTE.get(k, "[관행]"), "입력": src(k)})
    out += [{"기준": "S3 업종 코드", "값": sc["industry_codes"] or "꺼짐", "성격": "[관행] 데이터베이스 검색 조건 재확인", "입력": src("industry_codes")},
            {"기준": "S4 규모(평균 매출)", "값": [sc["size_min"], sc["size_max"]], "성격": "[관행]", "입력": src("size_min") if "size_min" in given else src("size_max")},
            {"기준": "S11 특수 상황", "값": sc["special_flags"] or "꺼짐", "성격": "[관행]", "입력": src("special_flags")},
            {"기준": "지표·기간", "값": f"{pli} {averaging} {years}, 사분위 {qm}", "성격": "영 제8조①, 시행규칙 제9조"},
            {"기준": "표본·편차 경고", "값": [sc["sample_min"], sc["spread_ratio"]], "성격": "[우리 규칙] 표시만",
             "입력": "사용자 입력" if {"sample_min", "spread_ratio"} & given else "입력 없음 — 꺼짐"}]
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
