"""branch_profits_tax(지점세) · emigration_exit_tax(국외전출세) — Claude 작성(2026-11-14).

조문 대조(법제처 DRF 연혁본, 각 연말 시행본):
  · 법인세법 제96조 — 2016(20160125)~2026(20260701) 연말 시행본 11개. 제2항제1호가목 문언(2019 시행본·2021 시행본), 제2항제4호 인용 조문
    (2020 시행본까지 국조법 제14조, 2021 시행본부터 제22조), 제3항 인용 세율(2018 시행본까지 제98조제1항제3호, 2019 시행본부터 제2호)만 바뀜.
  · 법인세법 제98조제1항 — 2016(20160125)·2018(20181101)·2019(20190101)·2026(20260701) 시행본: 인용 세율은 모두 100분의 20.
  · 법인세법 시행령 제134조 — 2016(20161129)~2026(20261001) 연말 시행본: 2021 시행본에서 '대차대조표'→'재무상태표'만 바뀜.
  · 소득세법 제118조의9~제118조의18 — 2017(20170701, 조문 없음)·2018(20180921)~2026(20260701) 연말 시행본,
    부칙 2016.12.20. 제14389호 제1조·제9조, 2017.12.19. 제15225호 제9조, 2018.12.31. 제16104호 제1조 단서·제13조, 2025.12.23. 제21221호 제1조제2호·제8조.
  · 소득세법 시행령 제178조의8~제178조의12 — 2018(20181023)·2020(20201210)·2026(20261001) 시행본, 부칙 2017.2.3. 제27829호 제1조, 2019.2.12. 제29523호 제8조.
"""
from __future__ import annotations

from datetime import date

from .calc_deadline import month_end_plus

# ── 지점세 ────────────────────────────────────────────────────────────────────

STAT_RATE = 0.20   # 법인세법 제96조③ → 제98조①3호(2016~2018 시행본)·①2호(2019~2026 시행본) — 모두 100분의 20


def _bp_labels(year: int) -> dict:
    return {
        "세율 인용": "법인세법 제98조제1항제3호(100분의 20)" if year <= 2018 else "법인세법 제98조제1항제2호(100분의 20)",
        "과소자본 손금불산입": "「국제조세조정에 관한 법률」 제14조" if year <= 2020 else "「국제조세조정에 관한 법률」 제22조",
        "자본금상당액": "대차대조표" if year <= 2020 else "재무상태표",
    }


def branch_profits_tax(year: int, pe_income: int, corporate_tax: int, credits_reductions: int = 0, penalties_additional: int = 0,
                       local_income_tax: int = 0, thin_cap_disallowed: int = 0, capital_begin: int = 0, capital_end: int = 0,
                       untaxed_retained_prior: int = 0, treaty_allows_branch_tax: bool = False, treaty_branch_rate: float | None = None,
                       residence_country_taxes_korean_branches: bool = True, treaty_basis: str = "소득금액",
                       remitted_profit: int | None = None, prior_year_taxable: int | None = None, pe_closed: bool = False) -> dict:
    if not 2016 <= year <= 2026:
        raise ValueError("year는 2016~2026")
    for k, v in (("corporate_tax", corporate_tax), ("credits_reductions", credits_reductions), ("penalties_additional", penalties_additional),
                 ("local_income_tax", local_income_tax), ("thin_cap_disallowed", thin_cap_disallowed)):
        if v < 0:
            raise ValueError(f"{k}는 0 이상(원)")
    if treaty_basis not in ("소득금액", "송금액"):
        raise ValueError("treaty_basis는 '소득금액' 또는 '송금액'")
    if treaty_branch_rate is not None and not 0 <= treaty_branch_rate <= 1:
        raise ValueError("treaty_branch_rate는 0~1 사이 소수(예: 0.05)")
    lab = _bp_labels(year)
    basis = ["법인세법 제96조제1항·제2항·제3항", "법인세법 시행령 제134조"]
    limits = ["조세조약이 지점세를 허용하는지, 조약 세율·과세 기준(소득금액·송금액)은 입력값을 그대로 씀 — tax_treaty(조문 MCP)로 해당 국가 조약의 지점세 조항을 확인",
              "제96조제1항 단서(거주지국이 그 나라에 있는 우리나라 법인의 국외사업장에 추가 과세하지 않으면 제외)는 입력값 residence_country_taxes_korean_branches로만 판정",
              "미과세누적유보소득(시행령 제134조제3항)은 직전 사업연도 종료일 현재 금액을 입력받음 — 도구가 과거 연도 합계를 다시 계산하지 않음",
              "원 미만 처리 규정을 찾지 못해 최종 세액만 원 미만 버림"]
    if not treaty_allows_branch_tax:
        return {"결과": {"지점세": 0, "과세 여부": "과세 안 함", "사유": "제96조제1항은 '조세조약에 따라' 추가 납부 — 조약이 지점세를 허용하지 않는다고 입력됨"},
                "근거": "법인세법 제96조제1항", "연도별": lab, "한계": limits}
    if not residence_country_taxes_korean_branches:
        return {"결과": {"지점세": 0, "과세 여부": "과세 안 함", "사유": "제96조제1항 단서 — 거주지국이 그 나라에 있는 우리나라 법인의 국외사업장에 추가 과세하지 않는다고 입력됨"},
                "근거": "법인세법 제96조제1항 단서", "연도별": lab, "한계": limits}
    rate = STAT_RATE if treaty_branch_rate is None else treaty_branch_rate
    rate_src = lab["세율 인용"] if treaty_branch_rate is None else "조세조약 세율(입력값, 제96조제3항 후단)"
    if pe_closed:
        capital_end = 0   # 시행령 제134조⑥ 의제사업연도 종료일 자본금상당액 0
    calc = {}
    if treaty_basis == "송금액":
        if remitted_profit is None or prior_year_taxable is None:
            raise ValueError("송금액 기준이면 remitted_profit(실제 송금 이윤)과 prior_year_taxable(직전 사업연도 과세대상소득금액)이 필요")
        if remitted_profit < 0 or prior_year_taxable < 0:
            raise ValueError("remitted_profit·prior_year_taxable은 0 이상")
        within = min(remitted_profit, prior_year_taxable)
        over = max(0, remitted_profit - prior_year_taxable)
        over_taxed = min(over, max(0, untaxed_retained_prior))
        base = within + over_taxed
        calc = {"실제 송금 이윤": remitted_profit, "직전 사업연도 과세대상소득금액": prior_year_taxable, "초과 송금액": over,
                "초과분 중 과세(미과세누적유보소득 한도)": over_taxed, "과세대상 송금액": base}
        basis.append("법인세법 시행령 제134조제5항" + ("·제7항" if pe_closed else ""))
        limits.append("송금액 기준 산식은 시행령 제134조제5항 문언(직전 사업연도 과세대상소득금액 초과분은 미과세누적유보소득 한도) 그대로 — 해석례 확인 필요")
        if pe_closed:
            limits.append("의제사업연도는 미송금 이윤 상당액을 종료일에 전액 송금한 것으로 봄(시행령 제134조제7항) — remitted_profit에 포함해 넣어야 함")
    else:
        tax_item1 = corporate_tax - credits_reductions + penalties_additional
        a = pe_income - tax_item1 - local_income_tax - thin_cap_disallowed
        inc = max(0, capital_end - capital_begin)
        dec = max(0, capital_begin - capital_end)
        if pe_income < 0:
            loss = -pe_income
            excess = dec - loss
            base = min(excess, max(0, untaxed_retained_prior)) if excess > 0 else 0
            calc = {"결손금": loss, "자본금상당액감소액": dec, "감소액 중 결손금 초과분": max(0, excess), "과세대상소득금액": base}
            basis.append("법인세법 시행령 제134조제4항")
        else:
            neg = max(0, -untaxed_retained_prior)
            neg_used = min(neg, max(0, a - inc))
            reinvest = inc + neg_used
            add = min(dec, max(0, untaxed_retained_prior))
            base = max(0, a - reinvest + add)
            calc = {"각 사업연도 소득금액": pe_income,
                    "제2항제1호 법인세 등": tax_item1, "제2항제2호 법인지방소득세": local_income_tax,
                    f"제2항제4호 {lab['과소자본 손금불산입']} 손금불산입액": thin_cap_disallowed,
                    "자본금상당액증가액": inc, "미과세누적유보소득(음수) 공제액": neg_used, "제2항제3호 재투자 등 공제 합계": reinvest,
                    "자본금상당액감소액 합산액(미과세누적유보소득 한도)": add, "과세대상소득금액": base}
        if pe_closed:
            basis.append("법인세법 시행령 제134조제6항")
    tax = int(base * rate)   # 원 미만 버림(규정 미확인 — 최종 금액만)
    return {"결과": {"지점세": tax, "과세대상 금액": int(base), "세율": rate, "세율 근거": rate_src, "과세 기준": treaty_basis, "과세 여부": "과세"},
            "계산": calc, "근거": "·".join(basis) + f"·{lab['세율 인용'] if treaty_branch_rate is None else '조세조약'}",
            "연도별": lab, "한계": limits,
            "다음 단계": ["조문 MCP tax_treaty(country=거주지국, keyword='지점')로 조약의 지점세·세율 확인", "법인세 산출세액은 corporate_tax로 먼저 계산"]}


# ── 국외전출세 ─────────────────────────────────────────────────────────────────

BASIC_DED = 2_500_000          # 제118조의10④ 연 250만원 (2018~2026 시행본 같음)
_PROG_START = date(2019, 1, 1)  # 2018.12.31. 제16104호 부칙 제1조·제13조① — 이후 출국분부터 누진(3억 이하 20%, 초과 25%)
_SME_PROG_START = date(2020, 1, 1)  # 같은 부칙 제1조 단서 — 중소기업 주식등 부분은 2020.1.1. 시행
_LAST = date(2026, 12, 31)      # 2025.12.23. 제21221호 부칙 제1조제2호·제8조: 2027.1.1. 이후 출국분은 개정규정(미확인)


def _prog(base: int) -> int:
    """제118조의11(2019.1.1. 이후 출국분): 3억원 이하 20%, 초과 6천만원 + 초과액×25%."""
    if base <= 300_000_000:
        return base * 20 // 100
    return 60_000_000 + (base - 300_000_000) * 25 // 100


def _d(s, name):
    try:
        return date.fromisoformat(str(s))
    except ValueError:
        raise ValueError(f"{name}는 YYYY-MM-DD")


def emigration_exit_tax(departure_date: str, residence_years_in_10: float, major_shareholder: bool, holdings: list,
                        holdings_reported: bool = True, unreported_face_value: int = 0, manager_reported: bool = False) -> dict:
    d = _d(departure_date, "departure_date")
    if d < date(2018, 1, 1):
        return {"결과": {"납세의무": "없음", "사유": "국외전출세(소득세법 제118조의9~제118조의18)는 2018.1.1. 이후 출국하는 경우부터 적용(2016.12.20. 법률 제14389호 부칙 제1조·제9조)"},
                "근거": "소득세법 부칙(2016.12.20. 제14389호) 제1조·제9조"}
    if d > _LAST:
        raise ValueError("2027.1.1. 이후 출국분은 2025.12.23. 개정규정(법률 제21221호 부칙 제8조)이 적용되는데 그 문언을 대조하지 못해 계산하지 않음")
    if not holdings:
        raise ValueError("holdings에 출국 당시 소유한 국내주식등을 1건 이상 넣어야 함")
    reasons = []
    if residence_years_in_10 < 5:
        reasons.append(f"출국일 10년 전부터 출국일까지 국내 주소·거소 기간 합계 {residence_years_in_10}년 — 5년 미만(제118조의9제1항제1호)")
    if not major_shareholder:
        reasons.append("출국일이 속하는 연도의 직전 연도 종료일 현재 대주주가 아님(제118조의9제1항제2호, 시행령 제178조의8 → 제167조의8제1항)")
    if reasons:
        return {"결과": {"납세의무": "없음", "사유": reasons}, "근거": "소득세법 제118조의9제1항"}
    rows, price, cost, sme_gain, gen_gain = [], 0, 0, 0, 0
    for i, h in enumerate(holdings):
        try:
            mv, ac = int(h["market_value"]), int(h["acquisition_cost"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"holdings[{i}]에 market_value(출국일 시가)와 acquisition_cost(필요경비)를 원 단위로")
        if mv < 0 or ac < 0:
            raise ValueError(f"holdings[{i}] 금액은 0 이상")
        sme = bool(h.get("sme", False))
        g = mv - ac
        rows.append({"종목": h.get("name", f"{i + 1}"), "양도가액(출국일 시가)": mv, "필요경비": ac, "양도소득금액": g, "중소기업": sme})
        price += mv
        cost += ac
        if sme:
            sme_gain += g
        else:
            gen_gain += g
    gain = price - cost
    base = max(0, gain - BASIC_DED)
    notes, limits = [], []
    if d < _PROG_START:
        tax = base * 20 // 100
        regime = "2018.1.1.~2018.12.31. 출국분 — 과세표준의 100분의 20(2018 시행본 제118조의11)"
        single_rate = 0.20
    elif d < _SME_PROG_START and sme_gain > 0:
        # 2019년 출국분: 중소기업 주식등은 종전 20%, 그 밖의 주식등은 누진(부칙 제1조 단서)
        gen_net, sme_net = (0, sme_gain + gen_gain) if gen_gain < 0 else (gen_gain, sme_gain)
        ded_gen = min(BASIC_DED, gen_net)
        gen_base = gen_net - ded_gen
        sme_base = max(0, sme_net - (BASIC_DED - ded_gen))
        tax = _prog(gen_base) + sme_base * 20 // 100
        base = gen_base + sme_base
        regime = "2019.1.1.~2019.12.31. 출국분 — 중소기업 주식등은 100분의 20, 그 밖의 주식등은 3억원 이하 20%·초과 25%(2018.12.31. 제16104호 부칙 제1조 단서)"
        single_rate = 0.20 if gen_base <= 300_000_000 else None
        limits.append("2019년 출국분에서 중소기업 주식등과 그 밖의 주식등이 섞이면 연 250만원 공제와 손익 통산 순서를 정한 문언을 찾지 못함 — "
                      "그 밖의 주식등 소득에서 먼저 공제하고 손실은 서로 통산해 계산(확인 필요)")
    else:
        tax = _prog(base)
        regime = ("2019.1.1. 이후 출국분" if d < _SME_PROG_START else "2020.1.1. 이후 출국분") + " — 3억원 이하 20%, 초과 6천만원 + 초과액×25%(제118조의11)"
        single_rate = 0.20 if base <= 300_000_000 else None
    penalty = 0
    if d >= _PROG_START and not holdings_reported:
        if unreported_face_value < 0:
            raise ValueError("unreported_face_value는 0 이상")
        penalty = unreported_face_value * 2 // 100
        notes.append(f"보유현황 미신고·누락 — 액면금액(출자가액) {unreported_face_value:,}원 × 100분의 2 = {penalty:,}원을 산출세액에 더함(제118조의15제4항, 2019.1.1. 이후 출국분)")
    elif not holdings_reported:
        notes.append("2018년 출국분에는 보유현황 미신고 가산(제118조의15제4항)이 없음 — 2018.12.31. 제16104호 부칙 제13조①")
    due = month_end_plus(d, 3)
    filing = {"납세관리인·보유현황 신고": f"출국일 전날({(date.fromordinal(d.toordinal() - 1)).isoformat()})까지(제118조의15제1항)",
              "과세표준 신고·납부": f"출국일이 속하는 달의 말일부터 3개월 이내 — {due.isoformat()}(제118조의15제2항·제3항)"}
    if d >= _PROG_START and manager_reported:
        filing["과세표준 신고·납부"] += " / 납세관리인을 신고했으면 제110조제1항의 양도소득과세표준 확정신고 기간 내(2019.1.1. 이후 출국분) — 기간은 제110조 원문 확인"
    result = {"납세의무": "있음", "양도가액 합계": price, "필요경비 합계": cost, "양도소득금액": gain, "기본공제": min(BASIC_DED, max(0, gain)),
              "과세표준": base, "산출세액": tax, "보유현황 미신고 가산": penalty, "납부할 세액(감면·공제 전)": tax + penalty, "세율 구간": regime}
    later = {
        "조정공제(제118조의12)": "출국 후 실제 양도가액이 출국일 시가보다 낮으면 (출국일 시가 − 실제 양도가액) × 제118조의11 세율을 산출세액에서 공제"
                          + (f" — 이 입력의 세율은 {int(single_rate * 100)}%" if single_rate is not None else
                             " — 과세표준이 3억원을 넘어 20%·25% 중 어느 세율을 쓰는지 문언으로 정해지지 않음(확인 필요)"),
        "외국납부세액공제(제118조의13)": "외국에 낸 세액 × (출국일 시가[조정공제 대상이면 실제 양도가액] − 필요경비) ÷ (실제 양도가액 − 필요경비), 한도는 산출세액 − 조정공제액. "
                                  "외국이 산출세액에 외국납부세액공제를 허용하거나 취득가액을 출국일 시가로 조정해 주면 적용 안 함",
        "비거주자 국내원천소득 세액공제(제118조의14)": "실제 양도가 비거주자 국내원천소득으로 국내에서 과세되면 그 원천징수 세액(제156조)을 산출세액 − 조정공제액 한도로 공제, 이때 외국납부세액공제는 적용 안 함",
        "경정청구": "위 공제는 실제 양도한 날부터 2년 이내 경정청구(제118조의15제5항 — 2019.1.1. 이후 양도분, 시행령 제178조의10·제178조의11제4항)",
        "취득가액 의제": "2018 시행본 제118조의15제4항은 국외전출세를 납부하면 출국일 시가로 양도하고 다시 취득한 것으로 봄. 2019 시행본부터 이 항은 보유현황 미신고 가산으로 바뀌어 이 문언이 이 조에 없음 — 이후 취득가액 처리는 확인 필요",
    }
    deferral = {
        "요건": "납세담보 제공(시행령 인용 조문: 2018 시행본 국세기본법 제29조, 2026 시행본 국세징수법 제18조)과 납세관리인 신고를 모두 갖추고 신청(제118조의16제1항, 시행령 제178조의12제1항)",
        "기간": "출국일부터 실제 양도할 때까지. 5년(국외유학이면 10년, 시행령 제178조의12제2항) 이내 양도하지 않으면 5년이 되는 날이 속하는 달의 말일부터 3개월 이내 납부(제118조의16제2항)",
        "실제 양도 시": "양도일이 속하는 달의 말일부터 3개월 이내 납부(제118조의16제3항, 2018.1.1. 이후 출국분)",
        "이자상당액": "유예세액 × 신고기한 다음 날부터 납부일까지 일수 × 납부유예 신청일 현재 국세기본법 시행령 제43조의3제2항 이자율(시행령 제178조의12제3항)",
        "신청": "과세표준신고서와 함께 납부유예신청서 제출(시행령 제178조의12제4항)",
    }
    refund = "출국일부터 5년 이내 양도 없이 재입국해 거주자가 되거나, 거주자에게 증여하거나, 상속되면 사유 발생일부터 1년 이내 환급·유예 취소 신청(제118조의17). " \
             "보유현황 미신고 가산액은 환급하지 않음(제118조의17제3항, 2021.12.8. 신설), 증여·상속 환급에는 환급가산금 없음"
    limits += ["대주주 해당 여부(시행령 제167조의8제1항의 지분율·시가총액 기준)는 입력값으로 받음 — 연도별 기준은 이 도구가 판정하지 않음",
               "출국일 시가(시행령 제178조의9: 거래가액, 산정 어려우면 상장주식 기준시가·비상장주식 매매사례가액→기준시가)와 필요경비(제97조)는 입력값",
               "양도소득금액은 입력 주식등 전체를 합산해 계산(제118조의10제3항) — 종목별 손익 통산 방법은 문언 그대로 합계",
               "감면세액·세액공제(제118조의15제3항)는 반영하지 않음",
               "2027.1.1. 이후 출국분 개정규정(2025.12.23. 법률 제21221호)은 대조하지 못함",
               "원 미만 처리 규정을 찾지 못해 산출세액·가산액만 원 미만 버림"]
    return {"결과": result, "종목": rows, "신고·납부": filing, "실제 양도 후 조정": later, "납부유예": deferral, "재전입 등 환급": refund,
            "주의": notes, "근거": "소득세법 제118조의9~제118조의11·제118조의15·제118조의16, 시행령 제178조의8·제178조의9·제178조의12", "한계": limits}
