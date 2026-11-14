"""branch_profits_tax(지점세) · emigration_exit_tax(국외전출세) — Claude 작성(2026-11-14).

조문 대조(법제처 DRF 연혁본, 각 연말 시행본):
  · 법인세법 제96조 — 2016(20160125)~2026(20260701) 연말 시행본 11개. 제2항제1호가목 문언(2019 시행본·2021 시행본), 제2항제4호 인용 조문
    (2020 시행본까지 국조법 제14조, 2021 시행본부터 제22조), 제3항 인용 세율(2018 시행본까지 제98조제1항제3호, 2019 시행본부터 제2호)만 바뀜.
  · 법인세법 제98조제1항 — 2016(20160125)·2018(20181101)·2019(20190101)·2026(20260701) 시행본: 인용 세율은 모두 100분의 20.
  · 법인세법 시행령 제134조 — 2016(20161129)~2026(20261001) 연말 시행본: 2021 시행본에서 '대차대조표'→'재무상태표'만 바뀜.
  · 소득세법 제118조의9~제118조의18 — 2017(20170701, 조문 없음)·2018(20180921)~2026(20260701) 연말 시행본, 2027.1.1. 시행 예정본(법률 제21221호),
    부칙 2016.12.20. 제14389호 제1조·제9조, 2017.12.19. 제15225호 제9조, 2018.12.31. 제16104호 제1조 단서·제13조, 2025.12.23. 제21221호 제1조제2호·제8조.
  · 소득세법 시행령 제178조의8~제178조의12 — 2018(20181023)·2020(20201210)·2026(20261001) 시행본, 부칙 2017.2.3. 제27829호 제1조, 2019.2.12. 제29523호 제8조.
"""
from __future__ import annotations

from datetime import date
from fractions import Fraction
from itertools import permutations

from .calc_deadline import month_end_plus

# 끝수(국고금 관리법 제47조 — 2011.10.5.·2026.1.2. 시행본 같은 문언, 2011.4.4. 전문개정 뒤 그대로):
#   제2항 "국세의 과세표준액을 산정할 때 1원 미만의 끝수가 있으면 이를 계산하지 아니한다",
#   제1항 "국고금의 수입 또는 지출에서 10원 미만의 끝수가 있을 때에는 그 끝수는 계산하지 아니하고, 전액이 10원 미만일 때에도 그 전액을 계산하지 아니한다"
#   (단서: 분할 징수·수납 때 끝수를 최초 수입금에 합산 — 시행령 제109조의2제1항).
ROUNDING_BASIS = "국고금 관리법 제47조제1항(수입·지출 10원 미만 끝수 버림)·제2항(과세표준 1원 미만 버림)"
ROUNDING_NOTE = "끝수: 과세표준은 1원 미만, 세액은 원 미만을 버리고 계산 — 납부할 때 10원 미만 끝수는 버림(" + ROUNDING_BASIS + ")"


def pay_amount(tax: int) -> int:
    """납부(수납)할 금액 — 10원 미만 끝수 버림, 전액이 10원 미만이면 0(국고금 관리법 제47조제1항)."""
    return tax // 10 * 10 if tax > 0 else tax

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
              ROUNDING_NOTE]
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
        limits.append("송금액 기준: 실제로 송금되는 이윤에 조약 세율을 적용한다는 회신(재국조46017-216, 2001.12.29.)은 있으나, 직전 사업연도 과세대상소득금액을 넘는 송금액을 "
                      "미과세누적유보소득 한도로 과세하는 시행령 제134조제5항 산식을 다룬 해석례는 근거 없음 — 국세법령정보시스템 검색('지점세 송금액 직전 사업연도 과세대상소득금액 초과', 2026-11-15), "
                      "서면질의 필요. 이 도구는 문언 그대로 계산")
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
    tax = int(Fraction(int(base)) * Fraction(str(rate)))   # 과세표준 1원 미만·세액 원 미만 버림
    return {"결과": {"지점세": tax, "납부할 금액(10원 미만 버림)": pay_amount(tax), "과세대상 금액": int(base), "세율": rate, "세율 근거": rate_src, "과세 기준": treaty_basis, "과세 여부": "과세"},
            "계산": calc, "근거": "·".join(basis) + f"·{lab['세율 인용'] if treaty_branch_rate is None else '조세조약'}",
            "연도별": lab, "한계": limits,
            "다음 단계": ["조문 MCP tax_treaty(country=거주지국, keyword='지점')로 조약의 지점세·세율 확인", "법인세 산출세액은 corporate_tax로 먼저 계산"]}


# ── 국외전출세 ─────────────────────────────────────────────────────────────────

BASIC_DED = 2_500_000          # 제118조의10④ 연 250만원 (2018~2026 시행본 같음)
_PROG_START = date(2019, 1, 1)  # 2018.12.31. 제16104호 부칙 제1조·제13조① — 이후 출국분부터 누진(3억 이하 20%, 초과 25%)
_SME_PROG_START = date(2020, 1, 1)  # 같은 부칙 제1조 단서 — 중소기업 주식등 부분은 2020.1.1. 시행
# 2025.12.23. 법률 제21221호 부칙 제1조제2호(제118조의9~제118조의18: 2027.1.1. 시행)·제8조("2027년 1월 1일 이후 거주자가 출국하는 경우부터 적용").
# 2027.1.1. 시행 예정본(법제처 2026-11-15 조회, 원자료 raw_wp2) 대조:
#   · 제118조의9제1항: 대상에 제94조제1항제3호다목 주식등(국외주식등)을 더함. 대주주 판정(제2호)에서는 다목 주식등을 뺌.
#   · 제118조의11: 제1호 제94조제1항제3호가목·나목, 제4호다목·라목 주식등 — 3억원 이하 20%, 초과 6천만원 + 초과액 25%(종전과 같음)
#                  제2호 제94조제1항제3호다목 주식등 — 중소기업 주식등 10%, 그 밖의 주식등 20%.
#   · 제118조의10제2항~제5항은 그대로(연 250만원 공제), 제118조의12~제118조의18은 '국외전출자 국내주식등' → '국외전출자 주식등' 용어만.
#   · 시행령 제178조의8제2항(대통령령 제36129호, 2026.2.27., 2027.1.1. 시행): 국외주식등 중 ① 출국 당시 양도가액 합계 5억원 이하인 것,
#     ② 외국인근로자가 소유한 것, ③ 그 배우자·20세 이하 직계비속이 외국인근로자의 국내 근로 시작 전에 취득한 것은 대상에서 뺌.
#     제178조의9제2항제3호: 국외주식등 시가는 제178조의3에 따라 산정.
_NEW_START = date(2027, 1, 1)
_LAST = date(2027, 12, 31)      # 2027.1.1. 시행 예정본까지 대조 — 그 뒤 출국분은 계산하지 않음
_FOREIGN_FLOOR = 500_000_000    # 시행령 제178조의8제2항제1호


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


def _split_tax(groups: list) -> dict:
    """세율이 다른 묶음의 과세표준·세액. groups = [(이름, 양도소득금액, 세액함수)] — 앞에 둔 묶음부터 연 250만원을 공제(기본 결과).
    양도차손은 다른 세율 묶음의 양도소득금액 비율로 나눠 공제(제118조의18제1항 → 제102조제2항, 시행령 제167조의2제1항제2호).
    연 250만원(제118조의10제4항)을 어느 묶음에서 먼저 빼는지는 문언이 없어 순서별 세액 범위를 함께 돌려준다."""
    pos = [(n, g, f) for n, g, f in groups if g > 0]
    loss = sum(-g for _, g, _ in groups if g < 0)
    total = sum(g for _, g, _ in pos)
    if not pos or loss >= total:
        return {"과세표준": 0, "산출세액": 0, "묶음": [], "범위": None, "차손": loss}
    net = [(n, Fraction(g) * (total - loss) / total, f) for n, g, f in pos]

    def run(order):
        left, rows, tax = Fraction(BASIC_DED), [], 0
        for n, g, f in order:
            d = min(left, g)
            left -= d
            b = int(g - d)          # 과세표준 1원 미만 버림
            x = f(b)
            rows.append({"구분": n, "양도소득금액(차손 통산 후)": int(g), "기본공제": int(d), "과세표준": b, "세액": x})
            tax += x
        return rows, tax

    rows, tax = run(net)
    alts = sorted({run(list(o))[1] for o in permutations(net)}) if len(net) > 1 else [tax]
    return {"과세표준": sum(r["과세표준"] for r in rows), "산출세액": tax, "묶음": rows,
            "범위": {"최소": alts[0], "최대": alts[-1]} if alts[0] != alts[-1] else None, "차손": loss}


def emigration_exit_tax(departure_date: str, residence_years_in_10: float, major_shareholder: bool, holdings: list,
                        holdings_reported: bool = True, unreported_face_value: int = 0, manager_reported: bool = False,
                        foreign_worker_exempt: bool = False) -> dict:
    d = _d(departure_date, "departure_date")
    if d < date(2018, 1, 1):
        return {"결과": {"납세의무": "없음", "사유": "국외전출세(소득세법 제118조의9~제118조의18)는 2018.1.1. 이후 출국하는 경우부터 적용(2016.12.20. 법률 제14389호 부칙 제1조·제9조)"},
                "근거": "소득세법 부칙(2016.12.20. 제14389호) 제1조·제9조"}
    if d > _LAST:
        raise ValueError("2028.1.1. 이후 출국분은 계산하지 않음 — 2027.1.1. 시행 예정본(법률 제21221호·대통령령 제36129호)까지만 대조")
    if not holdings:
        raise ValueError("holdings에 출국 당시 소유한 국내주식등을 1건 이상 넣어야 함")
    reasons = []
    if residence_years_in_10 < 5:
        reasons.append(f"출국일 10년 전부터 출국일까지 국내 주소·거소 기간 합계 {residence_years_in_10}년 — 5년 미만(제118조의9제1항제1호)")
    if not major_shareholder:
        reasons.append("출국일이 속하는 연도의 직전 연도 종료일 현재 대주주가 아님(제118조의9제1항제2호, 시행령 제178조의8 → 제167조의8제1항)")
    if reasons:
        return {"결과": {"납세의무": "없음", "사유": reasons}, "근거": "소득세법 제118조의9제1항"}
    new = d >= _NEW_START
    notes, limits = [], []
    foreign_mv = 0
    for i, h in enumerate(holdings):
        if h.get("foreign"):
            try:
                foreign_mv += int(h["market_value"])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"holdings[{i}]에 market_value(출국일 시가)와 acquisition_cost(필요경비)를 원 단위로")
    foreign_in = new and foreign_mv > _FOREIGN_FLOOR and not foreign_worker_exempt
    if foreign_mv and not new:
        notes.append("국외주식등(제94조제1항제3호다목)은 2027.1.1. 이후 출국분부터 대상(법률 제21221호 부칙 제8조) — 이 출국일에는 계산에서 뺌")
    elif foreign_mv and not foreign_in:
        notes.append("국외주식등 제외 — " + ("외국인근로자 등이 소유한 국외주식등(시행령 제178조의8제2항제2호·제3호, 입력값)" if foreign_worker_exempt else
                                       f"출국 당시 국외주식등 양도가액 합계 {foreign_mv:,}원이 5억원 이하(시행령 제178조의8제2항제1호)"))
    rows, price, cost = [], 0, 0
    gains = {"일반": 0, "중소": 0, "국외중소": 0, "국외일반": 0}
    for i, h in enumerate(holdings):
        try:
            mv, ac = int(h["market_value"]), int(h["acquisition_cost"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"holdings[{i}]에 market_value(출국일 시가)와 acquisition_cost(필요경비)를 원 단위로")
        if mv < 0 or ac < 0:
            raise ValueError(f"holdings[{i}] 금액은 0 이상")
        sme, foreign = bool(h.get("sme", False)), bool(h.get("foreign", False))
        g = mv - ac
        row = {"종목": h.get("name", f"{i + 1}"), "양도가액(출국일 시가)": mv, "필요경비": ac, "양도소득금액": g, "중소기업": sme}
        if foreign:
            row["국외주식등"] = True
            if not foreign_in:
                row["대상"] = "제외"
                rows.append(row)
                continue
        rows.append(row)
        price += mv
        cost += ac
        gains[("국외중소" if sme else "국외일반") if foreign else ("중소" if sme else "일반")] += g
    if not any(r.get("대상") != "제외" for r in rows):
        return {"결과": {"납세의무": "없음", "사유": notes}, "종목": rows, "근거": "소득세법 제118조의9제1항, 시행령 제178조의8제2항"}
    gain = price - cost
    if d < _PROG_START:
        sp = _split_tax([("주식등", gain, lambda b: b * 20 // 100)])
        regime = "2018.1.1.~2018.12.31. 출국분 — 과세표준의 100분의 20(2018 시행본 제118조의11)"
        single_rate = 0.20
    elif d < _SME_PROG_START and gains["중소"] != 0:
        # 2019년 출국분: 중소기업 주식등은 종전 20%, 그 밖의 주식등은 누진(부칙 제1조 단서)
        sp = _split_tax([("그 밖의 주식등(3억원 이하 20%·초과 25%)", gains["일반"], _prog), ("중소기업 주식등(20%)", gains["중소"], lambda b: b * 20 // 100)])
        regime = "2019.1.1.~2019.12.31. 출국분 — 중소기업 주식등은 100분의 20, 그 밖의 주식등은 3억원 이하 20%·초과 25%(2018.12.31. 제16104호 부칙 제1조 단서)"
        gen_base = next((r["과세표준"] for r in sp["묶음"] if r["구분"].startswith("그 밖")), 0)
        single_rate = 0.20 if gen_base <= 300_000_000 else None
    elif new and (gains["국외중소"] != 0 or gains["국외일반"] != 0):
        sp = _split_tax([("제118조의11제1호 주식등(3억원 이하 20%·초과 25%)", gains["일반"] + gains["중소"], _prog),
                         ("제2호나목 국외 그 밖의 주식등(20%)", gains["국외일반"], lambda b: b * 20 // 100),
                         ("제2호가목 국외 중소기업 주식등(10%)", gains["국외중소"], lambda b: b * 10 // 100)])
        regime = ("2027.1.1. 이후 출국분 — 제94조제1항제3호가목·나목, 제4호다목·라목 주식등은 3억원 이하 20%·초과 25%, "
                  "같은 항 제3호다목 주식등은 중소기업 10%·그 밖 20%(법률 제21221호 제118조의11, 부칙 제8조)")
        single_rate = None
    else:
        sp = _split_tax([("주식등", gain, _prog)])
        regime = (("2019.1.1. 이후 출국분" if d < _SME_PROG_START else "2020.1.1. 이후 출국분" if not new else "2027.1.1. 이후 출국분(법률 제21221호)")
                  + " — 3억원 이하 20%, 초과 6천만원 + 초과액×25%(제118조의11)")
        single_rate = 0.20 if sp["과세표준"] <= 300_000_000 else None
    base, tax = sp["과세표준"], sp["산출세액"]
    if len(sp["묶음"]) > 1 or (sp["차손"] and len([g for g in gains.values() if g]) > 1):
        notes.append("세율이 다른 주식등의 양도차손은 다른 세율 주식등의 양도소득금액 비율로 나눠 공제(제118조의18제1항이 준용하는 제102조제2항, 시행령 제167조의2제1항제2호)")
    if sp["범위"]:
        limits.append("세율이 다른 주식등이 섞일 때 연 250만원(제118조의10제4항)을 어느 쪽에서 먼저 빼는지 — 근거 없음(제118조의18제1항 준용 조문에 제103조 없음, "
                      "국세법령정보시스템 검색 '국외전출세 중소기업 주식 기본공제 250만원 세율' 2026-11-15 해당 문서 없음), 서면질의 필요. "
                      f"이 결과는 위 '세율 묶음' 순서대로 공제한 {tax:,}원이고, 순서에 따라 {sp['범위']['최소']:,}원~{sp['범위']['최대']:,}원")
    if new:
        limits.append("2027.1.1. 이후 출국분은 2026.11.15. 조회한 시행 예정본(법률 제21221호, 대통령령 제36129호) 기준 — 시행 전에 다시 개정되면 달라짐")
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
              "과세표준": base, "산출세액": tax, "보유현황 미신고 가산": penalty, "납부할 세액(감면·공제 전)": tax + penalty,
              "납부할 금액(10원 미만 버림)": pay_amount(tax + penalty), "세율 구간": regime}
    if len(sp["묶음"]) > 1:
        result["세율 묶음"] = sp["묶음"]
    if sp["범위"]:
        result["기본공제 순서에 따른 산출세액 범위"] = sp["범위"]
    later = {
        "조정공제(제118조의12)": "출국 후 실제 양도가액이 출국일 시가보다 낮으면 (출국일 시가 − 실제 양도가액) × 제118조의11 세율을 산출세액에서 공제"
                          + (f" — 이 입력의 세율은 {int(single_rate * 100)}%" if single_rate is not None else
                             " — 과세표준이 3억원을 넘거나 세율이 다른 주식등이 섞이면 20%·25%(국외주식등은 10%·20%) 중 어느 세율을 쓰는지: 근거 없음"
                             "(제118조의12제1항은 '제118조의11에 따른 세율'이라고만 함, 국세법령정보시스템 검색 2026-11-15 해당 문서 없음), 서면질의 필요 — "
                             "차액에 낮은 세율을 곱한 금액과 높은 세율을 곱한 금액 사이"),
        "외국납부세액공제(제118조의13)": "외국에 낸 세액 × (출국일 시가[조정공제 대상이면 실제 양도가액] − 필요경비) ÷ (실제 양도가액 − 필요경비), 한도는 산출세액 − 조정공제액. "
                                  "외국이 산출세액에 외국납부세액공제를 허용하거나 취득가액을 출국일 시가로 조정해 주면 적용 안 함",
        "비거주자 국내원천소득 세액공제(제118조의14)": "실제 양도가 비거주자 국내원천소득으로 국내에서 과세되면 그 원천징수 세액(제156조)을 산출세액 − 조정공제액 한도로 공제, 이때 외국납부세액공제는 적용 안 함",
        "경정청구": "위 공제는 실제 양도한 날부터 2년 이내 경정청구(제118조의15제5항 — 2019.1.1. 이후 양도분, 시행령 제178조의10·제178조의11제4항)",
        "취득가액": "2019년 이후 시행본에는 출국일 시가를 취득가액으로 다시 보는 문언이 없음(2019.1.1.·2026.7.1.·2027.1.1. 시행본 제118조의9~제118조의18, 2026.7.1. 시행본 전문에서 '국외전출자'를 든 조문은 이 절뿐) — "
                 "실제 양도 때의 이중과세는 위 조정공제·외국납부세액공제·비거주자 국내원천소득 세액공제로 조정. 2018 시행본 제118조의15제4항은 국외전출세를 납부하면 출국일 시가로 양도하고 다시 취득한 것으로 봄",
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
               ROUNDING_NOTE]
    return {"결과": result, "종목": rows, "신고·납부": filing, "실제 양도 후 조정": later, "납부유예": deferral, "재전입 등 환급": refund,
            "주의": notes, "근거": "소득세법 제118조의9~제118조의11·제118조의15·제118조의16, 시행령 제178조의8·제178조의9·제178조의12", "한계": limits}
