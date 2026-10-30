"""비상장주식 평가 — (A) 상증법 보충적 평가(법 제63조①1호나목, 영 제54조~제56조·제53조 할증) (B) 소득세법 기준시가(법 제99조①4호, 영 제165조④).
구간별 값은 조문 원문 대조(2026-10-30, law.go.kr 조문 연혁). 작성 Claude."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _won(v) -> str:
    return f"{v:,.0f}원"


# ── (A) 상증법 보충적 평가 ────────────────────────────────────────────────────

def _floor_ratio_inh(vd: date) -> tuple[float | None, str]:
    if vd < date(2017, 4, 1):
        return None, "영 제54조① 2017.3.31.까지 하한 없음"
    if vd < date(2018, 4, 1):
        return 0.70, "영 제54조① 단서(순자산가치 80%)를 대통령령 제27835호 부칙 제7조가 2017.4.1.~2018.3.31. 상속·증여분은 70%로"
    return 0.80, "영 제54조① 단서(2018.4.1.~ 순자산가치의 80%)"


def _net_asset_only_rule(vd: date) -> tuple[list[str], str, bool]:
    """(사유 목록, 근거, 부동산·주식 80% 사유에 '가중평균 < 순자산가치' 한정 여부)"""
    if vd < date(2017, 2, 7):
        return ["청산", "개시3년미만", "휴폐업", "3년연속결손"], "영 제54조④(2015.2.3.본): 청산 진행·사업 계속 곤란, 사업개시 전·개시 후 3년 미만·휴폐업, 직전 3년 연속 결손", False
    if vd < date(2018, 2, 13):
        return ["청산", "개시3년미만", "휴폐업", "3년연속결손", "주식80", "존속3년"], "영 제54조④(2017.2.7.): + 자산 중 주식등 80% 이상, 잔여 존속기한 3년 이내", False
    if vd < date(2026, 2, 27):
        return ["청산", "개시3년미만", "휴폐업", "부동산80", "주식80", "존속3년"], "영 제54조④(2018.2.13., 부칙 제8조 시행 이후 평가분): 3년 연속 결손 사유 삭제, 자산 중 부동산 80% 이상 신설", False
    return ["청산", "개시3년미만", "휴폐업", "부동산80", "주식80", "존속3년"], "영 제54조④(2026.2.27., 부칙 제11조): 부동산·주식 80% 사유는 가중평균이 순자산가치보다 낮은 경우로 한정", True


def _premium(vd: date, is_max: bool, ratio_over_50: bool | None, sme: bool, mid_sized: bool, exclusion: str | None) -> tuple[float, str, list[str]]:
    notes: list[str] = []
    if not is_max:
        return 0.0, "최대주주등이 아님 — 할증 없음(법 제63조③)", notes
    if exclusion:
        return 0.0, f"할증 제외 사유 '{exclusion}'(영 제53조⑧(구 ⑥·⑦) 각 호)", notes
    if vd < date(2020, 1, 1):
        if sme:
            return 0.0, "중소기업 최대주주 — 조세특례제한법 제101조로 2019.12.31.까지 상속·증여분 할증 미적용(법문 10%/15%는 적용되지 않음)", notes
        if ratio_over_50 is None:
            notes.append("최대주주등 지분이 50%(2017~ 의결권 있는 주식 기준)를 초과하는지 몰라 20%로 계산 — 초과하면 30%(ratio_over_50=True)")
            return 0.20, "법 제63조③(2019.12.31.까지): 20%, 50% 초과 보유 시 30%", notes
        return (0.30 if ratio_over_50 else 0.20), "법 제63조③(2019.12.31.까지): 20%, 50% 초과 보유 시 30%", notes
    if sme:
        return 0.0, "중소기업 제외(법 제63조③, 영 제53조⑥·2020.1.1.~)", notes
    if mid_sized and vd >= date(2023, 1, 1):
        return 0.0, "중견기업(직전 3개 사업연도 매출액 평균 5천억 미만) 제외(영 제53조⑦, 2023.1.1.~ 상속·증여분)", notes
    return 0.20, "법 제63조③(2020.1.1.~): 20% 단일", notes


def goodwill_value(avg_income_3y: float, equity: float, rate: float = 0.10, years: int = 5) -> tuple[float, str]:
    """영 제59조②·규칙 제19조①: [3년 순손익 가중평균×50% − 자기자본×10%]를 5년간 10%로 현가 합산."""
    excess = avg_income_3y * 0.5 - equity * rate
    if excess <= 0:
        return 0.0, f"초과이익 {excess:,.0f} ≤ 0 → 영업권 0"
    pv = sum(excess / (1 + rate) ** n for n in range(1, years + 1))
    return pv, f"초과이익 {excess:,.0f} × Σ1/(1.1)^n(n=1..5)={sum(1/(1+rate)**n for n in range(1, years+1)):.4f}"


def unlisted_valuation(valuation_date: str, shares: int, incomes: list | None = None, net_asset=None, equity=None,
                       goodwill=None, real_estate_ratio=None, stock_asset_ratio=None, business_start: str = "", status: str = "",
                       is_max_shareholder: bool = False, ratio_over_50: bool | None = None, sme: bool | None = None, mid_sized: bool = False,
                       premium_exclusion: str | None = None, cap_rate: float = 0.10) -> dict[str, Any]:
    vd = _d(valuation_date)
    if shares is None or int(shares) <= 0:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["shares(평가기준일 현재 발행주식총수)가 필요"]}
    shares = int(shares)
    판단: list[dict] = []
    # 순자산가치
    if net_asset is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["net_asset(평가기준일 현재 순자산가액 = 상증법 평가 자산 − 부채, 영 제55조·규칙 제17조의2 가감 반영)이 필요"]}
    na = max(0.0, float(net_asset))
    if float(net_asset) < 0:
        판단.append({"항목": "순자산가액", "결론": "0보다 작아 0으로 봄", "근거": "상증법 시행령 제55조①"})
    # 순손익가치
    inc_items = incomes or []
    if inc_items and len(inc_items) not in (1, 2, 3):
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["incomes는 최근 3개 사업연도 [{사업연도, 순손익액, 주식수?}] 최근 연도부터"]}
    per_share = []
    for it in inc_items:
        n = float(it.get("순손익액") if it.get("순손익액") is not None else it.get("net_income", 0))
        sh = int(it.get("주식수") or it.get("shares") or shares)
        per_share.append((it.get("사업연도") or it.get("year"), n / sh))
    reasons, basis_na, limited = _net_asset_only_rule(vd)
    사유 = None
    if status in ("청산", "휴폐업", "존속3년"):
        사유 = status
    if business_start:
        bs = _d(business_start)
        yrs = (vd - bs).days / 365.25
        if yrs < 3 and "개시3년미만" in reasons:
            사유 = 사유 or "개시3년미만"
            판단.append({"항목": "사업 개시", "결론": f"개시일 {business_start} → 평가기준일까지 {yrs:.1f}년(3년 미만)", "근거": "상증법 시행령 제54조④2호"})
    if 사유 is None and per_share and len(per_share) == 3 and all(v < 0 for _, v in per_share) and "3년연속결손" in reasons:
        사유 = "3년연속결손"
    if 사유 is None and real_estate_ratio is not None and float(real_estate_ratio) >= 0.8 and "부동산80" in reasons:
        사유 = "부동산80"
    if 사유 is None and stock_asset_ratio is not None and float(stock_asset_ratio) >= 0.8 and "주식80" in reasons:
        사유 = "주식80"
    ev_per = None; ev_calc = ""
    if per_share:
        w = [3, 2, 1][:len(per_share)]
        if len(per_share) < 3:
            판단.append({"항목": "순손익 자료", "결론": f"{len(per_share)}개 연도만 주어짐 — 3년 가중평균(3:2:1)에 못 미쳐 참고 계산. 사업 개시 3년 미만이면 순자산가치만 평가", "근거": "상증법 시행령 제56조①"})
        avg = sum(v * k for (_, v), k in zip(per_share, w)) / 6 if len(per_share) == 3 else sum(v * k for (_, v), k in zip(per_share, w)) / sum(w)
        avg0 = max(0.0, avg)
        ev_per = avg0 / cap_rate
        ev_calc = f"가중평균 1주당 순손익액 {avg:,.2f}(음수면 0) ÷ 환원율 {cap_rate*100:g}% = {ev_per:,.2f}"
        if avg < 0:
            판단.append({"항목": "순손익가치", "결론": "가중평균 순손익액이 음수 → 0", "근거": "상증법 시행령 제56조① 후단"})
    # 영업권
    gw = 0.0; gw_note = "영업권 미반영(goodwill·equity 미입력)"
    if goodwill is not None:
        gw = float(goodwill); gw_note = f"영업권 {gw:,.0f}원(입력값) 자산에 가산"
    elif equity is not None and len(per_share) == 3:
        avg_total = sum(v * sh_ * k for (_, v), sh_, k in zip(per_share, [int(it.get('주식수') or it.get('shares') or shares) for it in inc_items], [3, 2, 1])) / 6
        gw, gw_note = goodwill_value(avg_total, float(equity), cap_rate)
        gw_note = f"영업권 {gw:,.0f}원 — {gw_note}"
    excl_gw = 사유 in ("청산", "휴폐업", "부동산80", "주식80", "3년연속결손") or (사유 == "개시3년미만")
    if excl_gw and gw:
        gw_note += " → 순자산가치만 평가하는 법인이라 영업권 합산 제외(영 제55조③ 단서)"; gw = 0.0
    nav_per = (na + gw) / shares
    판단.append({"항목": "순자산가치", "결론": f"({_won(na)} + 영업권 {_won(gw)}) ÷ {shares:,}주 = {nav_per:,.2f}원/주. {gw_note}", "근거": "상증법 시행령 제54조②·제55조·제59조②"})
    # 가중평균
    heavy = real_estate_ratio is not None and float(real_estate_ratio) >= 0.5
    w_e, w_n = (2, 3) if heavy else (3, 2)
    if ev_per is not None:
        weighted = (ev_per * w_e + nav_per * w_n) / 5
        판단.append({"항목": "가중평균", "결론": f"(순손익가치 {ev_per:,.2f}×{w_e} + 순자산가치 {nav_per:,.2f}×{w_n}) ÷ 5 = {weighted:,.2f}" + (" — 부동산 과다보유법인(자산 중 부동산 50% 이상) 2:3" if heavy else " — 3:2"), "근거": "상증법 시행령 제54조①" + (", 소득세법 제94조①4호다목" if heavy else "")})
    else:
        weighted = None
    floor_r, floor_basis = _floor_ratio_inh(vd)
    value = None; method = ""
    if 사유 and not (limited and 사유 in ("부동산80", "주식80") and weighted is not None and weighted >= nav_per):
        value = nav_per; method = f"순자산가치만 평가 — 사유 '{사유}'"
        판단.append({"항목": "평가 방법", "결론": method, "근거": basis_na})
    elif weighted is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["incomes(최근 3개 사업연도 순손익액)가 없고 순자산가치만 평가하는 사유도 없음"], "판단": 판단}
    else:
        if 사유 and limited:
            판단.append({"항목": "평가 방법", "결론": f"사유 '{사유}'지만 가중평균 {weighted:,.2f} ≥ 순자산가치 {nav_per:,.2f}라 가중평균 적용(2026.2.27.~ 한정 규정)", "근거": basis_na})
        value = weighted; method = "가중평균"
        if floor_r is not None and weighted < nav_per * floor_r:
            value = nav_per * floor_r; method = f"하한 적용 — 순자산가치 × {floor_r*100:g}%"
            판단.append({"항목": "하한", "결론": f"가중평균 {weighted:,.2f} < 순자산가치 {nav_per:,.2f} × {floor_r*100:g}% = {value:,.2f} → 하한 적용", "근거": floor_basis})
        elif floor_r is not None:
            판단.append({"항목": "하한", "결론": f"가중평균 ≥ 순자산가치 × {floor_r*100:g}% — 하한 미적용", "근거": floor_basis})
        else:
            판단.append({"항목": "하한", "결론": "하한 규정 없는 구간", "근거": floor_basis})
    # 할증
    if is_max_shareholder and sme is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["최대주주 할증 판정에 sme(중소기업 여부)가 필요(2023~ 중견기업은 mid_sized)"], "필요 입력": {"sme": "bool"}}
    prem, prem_basis, notes = _premium(vd, is_max_shareholder, ratio_over_50, bool(sme), mid_sized, premium_exclusion)
    final = value * (1 + prem)
    판단.append({"항목": "최대주주 할증", "결론": f"{prem*100:g}% → 1주당 {final:,.2f}원. {prem_basis}", "근거": "상속세 및 증여세법 제63조③, 시행령 제53조"})
    for n in notes:
        판단.append({"항목": "확인 필요", "결론": n, "근거": "상속세 및 증여세법 제63조③"})
    판단.append({"항목": "확인 필요", "결론": "순자산가액은 상증법 평가액 기준으로 사용자가 가감(지급 확정 권리 +, 선급비용·무형자산 −, 미지급 법인세·확정 배당·퇴직급여추계액 +, 충당금·준비금 −)을 끝낸 값을 넣어야 함. 발행주식총수의 자기주식 포함 여부는 조문에 명시 없음(통칙 확인)", "근거": "상증법 시행령 제55조, 시행규칙 제17조의2"})
    return {"결과": {"1주당_평가액": round(final, 2), "1주당_할증전": round(value, 2), "순손익가치": round(ev_per, 2) if ev_per is not None else None, "순자산가치": round(nav_per, 2), "가중평균": round(weighted, 2) if weighted is not None else None,
                   "평가방법": method, "할증률": prem, "총평가액(보유주식×)": None},
            "계산": {"순손익가치 산식": ev_calc, "연도별 1주당 순손익액": [{"사업연도": y, "1주당": round(v, 2)} for y, v in per_share], "가중치": f"{w_e}:{w_n}", "하한율": floor_r, "영업권": round(gw, 0), "환원율": cap_rate},
            "근거": "상속세 및 증여세법 제63조①1호나목·③, 시행령 제53조·제54조·제55조·제56조·제59조②, 시행규칙 제17조·제17조의2·제17조의3·제19조", "판단": 판단,
            "산식": "순손익가치 = (1년전×3+2년전×2+3년전×1)/6 ÷ 10% / 순자산가치 = (순자산가액+영업권) ÷ 발행주식총수 / 가중평균 3:2(부동산 과다 2:3), 하한 순자산가치×80%(2017.4~2018.3은 70%), 순자산가치만 평가 사유 있으면 순자산가치 / 최대주주 할증 20%(2019까지 50% 초과 30%, 중소 제외·2023~ 중견 제외)"}


# ── (B) 소득세법 기준시가(영 제165조④) — 양도세 기준시가·대주주 시가총액 ──────────────

def income_tax_unlisted_basis(transfer_date: str, shares: int, prior_year_income=None, book_net_asset=None, real_estate_ratio=None,
                              business_start: str = "", status: str = "", stock_asset_ratio=None, rate: float = 0.10) -> dict[str, Any]:
    td = _d(transfer_date)
    if shares is None or int(shares) <= 0 or book_net_asset is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["shares(직전 사업연도 종료일 발행주식총수)와 book_net_asset(직전 사업연도 종료일 장부가액 순자산, 토지는 기준시가)이 필요"]}
    shares = int(shares)
    판단: list[dict] = []
    nav = max(0.0, float(book_net_asset)) / shares
    ev = None
    if prior_year_income is not None:
        ev = max(0.0, float(prior_year_income)) / shares / rate
        판단.append({"항목": "순손익가치", "결론": f"직전 사업연도 순손익액 {float(prior_year_income):,.0f} ÷ {shares:,}주 ÷ 이자율 {rate*100:g}% = {ev:,.2f}(3년 가중평균 아님)", "근거": "소득세법 시행령 제165조④1호가목"})
    사유 = None
    if status in ("청산", "휴폐업", "존속3년"):
        사유 = status if not (status == "존속3년" and td < date(2023, 2, 28)) else None
    if business_start and (td - _d(business_start)).days < 365:
        사유 = 사유 or "개시1년미만"
    if 사유 is None and td < date(2023, 2, 28) and prior_year_income is not None and False:
        pass
    if 사유 is None and td >= date(2023, 2, 28) and stock_asset_ratio is not None and float(stock_asset_ratio) >= 0.8:
        사유 = "주식80"
    heavy = real_estate_ratio is not None and float(real_estate_ratio) >= 0.5
    w_e, w_n = (2, 3) if heavy else (3, 2)
    if 사유:
        value = nav; method = f"순자산가치만 — 사유 '{사유}'"
        판단.append({"항목": "평가 방법", "결론": method, "근거": "소득세법 시행령 제165조④3호(청산·사업개시 1년 미만·휴폐업·(2023.2.28.~) 주식 80%·존속 3년 이내; 2023.2.27.까지는 3년 연속 결손)"})
    else:
        if ev is None:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["prior_year_income(직전 사업연도 순손익액)이 필요"]}
        weighted = (ev * w_e + nav * w_n) / 5
        value = weighted; method = "가중평균 " + f"{w_e}:{w_n}"
        if td >= date(2018, 4, 1) and weighted < nav * 0.8:
            value = nav * 0.8; method = "하한 — 장부 순자산가치 × 80%"
            판단.append({"항목": "하한", "결론": f"가중평균 {weighted:,.2f} < 순자산가치 {nav:,.2f}×80% → {value:,.2f}", "근거": "소득세법 시행령 제165조④ 단서(2018.4.1. 이후 양도분, 제28637호 부칙 제1조)"})
        판단.append({"항목": "가중평균", "결론": f"({ev:,.2f}×{w_e} + {nav:,.2f}×{w_n}) ÷ 5 = {weighted:,.2f}", "근거": "소득세법 시행령 제165조④1호"})
    판단.append({"항목": "할증", "결론": "양도세 기준시가·대주주 시가총액에는 최대주주 할증을 적용하지 않음(법 제99조①4호는 상증법 제63조①1호나목만 준용, 영 제165조④·제157조에 할증 규정 없음)", "근거": "소득세법 제99조①4호, 시행령 제157조④·제165조④"})
    판단.append({"항목": "확인 필요", "결론": "이자율은 2023.2.27.까지 기획재정부 고시, 이후 시행규칙 — 이 도구는 10%로 계산(값 재확인). 상속·증여 평가(3년 가중·상증법 평가액·할증)와 다른 산식임", "근거": "소득세법 시행령 제165조④"})
    return {"결과": {"1주당_기준시가": round(value, 2), "순손익가치": round(ev, 2) if ev is not None else None, "순자산가치(장부)": round(nav, 2), "평가방법": method},
            "근거": "소득세법 제99조①4호, 시행령 제165조④(2016~2026; 하한 2018.4.1.~, 사유 개정 2023.2.28.)", "판단": 판단,
            "산식": "순손익가치 = 직전 사업연도 1주당 순손익액 ÷ 10% / 순자산가치 = 직전 사업연도 말 장부가 순자산 ÷ 발행주식총수 / 가중평균 3:2(부동산 과다 2:3), 2018.4.1.~ 하한 순자산가치×80%, 할증 없음"}
