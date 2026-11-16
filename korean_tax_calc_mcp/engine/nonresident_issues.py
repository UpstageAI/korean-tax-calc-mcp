"""nonresident_withholding의 짧은 쟁점 줄 — 금액을 바꾸는 사실과 입력만 한 줄씩.

요건·소득 구분·조약 적용 판단(판례, 판단 순서)은 조문 MCP(korean-tax-mcp) `royalty_withholding_guide`·`treaty_withholding_rates`·`tax_treaty`에 둔다.
이 모듈은 계산에 쓰는 조문 표기와 그 도구들로 가는 안내만 담는다.

대조한 원문(2026-11-15 조회, as_of 2026-12-31 시행본): 법인세법 제98조제1항, 제98조의4, 제98조의6(2025.12.23. 개정 — 제4항 신설, 경정청구 제5항),
제98조의7제1항, 제120조의2제1항, 법인세법 시행령 제137조, 법인세법 기본통칙 98-0…2(2024년 고시본),
소득세법 제156조제1항·제156조의6·제156조의8제1항·제164조의2제1항, 지방세법 제103조의18제1항·제103조의52제1항,
국제조세조정에 관한 법률 시행령 제36조제1호, 부가가치세법 제52조제1항, 관세법 제30조제1항제4호, 한미 조세조약 제1조(대상조세).
유추·미확인은 그 표시 그대로 내보낸다.
"""

from __future__ import annotations

JUDGE = "전문가 확인 필요"
GUIDE = "korean-tax-mcp royalty_withholding_guide"
_RATE_TOOL = "korean-tax-mcp treaty_withholding_rates"
POINTER = ("요건·소득구분·조약 적용 판단은 korean-tax-mcp `royalty_withholding_guide`(사용료)·`treaty_withholding_rates`·`tax_treaty`로 먼저 확인 — "
           "이 도구는 주어진 세율·사실로 금액만 계산")
POINTER_EN = ("Check requirements, income characterization and treaty eligibility first with korean-tax-mcp `royalty_withholding_guide` (royalties), "
              "`treaty_withholding_rates` and `tax_treaty`; this tool only computes the amount from the rate and facts you give it.")

# 조약 대상조세 조문 번호 — 원문으로 확인한 나라만. 그 밖은 번호를 쓰지 않는다.
COVERED_TAXES_ARTICLE = {"미국": "제1조"}


def covered_taxes_phrase(country_kr: str | None, article: str | None) -> str:
    """'조약 대상조세 조문' 표기 — 입력한 조문 번호, 확인된 나라의 번호, 둘 다 없으면 번호 없이."""
    if article:
        return f"조약 {article}(대상조세 — 입력값)"
    if country_kr in COVERED_TAXES_ARTICLE:
        name = "한미 조세조약" if country_kr == "미국" else f"{country_kr} 조세조약"
        return f"{name} {COVERED_TAXES_ARTICLE[country_kr]}(대상조세)"
    return "조약의 대상조세 조문(번호는 조약마다 다름 — 조문 MCP tax_treaty로 확인. 한미 조약은 제1조)"


def local_tax_basis(side: int, included: bool | None) -> str:
    """지방소득세 특별징수 근거 — 법인: 지방세법 제103조의52제1항, 개인: 제103조의18제1항."""
    if side:
        return ("법인세법 제98조의7제1항제2호" if included else "법인세법 제98조의7제1항제1호") + \
               " · 지방세법 제103조의52제1항(외국법인 특별징수 — 원천징수하는 법인세의 10%)"
    return ("소득세법 제156조의8제1항제2호" if included else "소득세법 제156조의8제1항제1호") + \
           " · 지방세법 제103조의18제1항(비거주자 특별징수 — 원천징수할 소득세의 10%)"


def _issue(구분, 쟁점, 참고):
    return {"구분": 구분, "쟁점": 쟁점, "참고": 참고, "판단": JUDGE}


def pointer_issue() -> dict:
    return {"구분": "안내", "쟁점": POINTER, "en": POINTER_EN,
            "참고": [GUIDE, _RATE_TOOL, "korean-tax-mcp tax_treaty"], "판단": JUDGE}


def relief_issue(side: int, treaty_rate_given: bool) -> dict:
    art = "법인세법 제98조의6" if side else "소득세법 제156조의6"
    head = ("" if treaty_rate_given else
            f"treaty_rate가 없어 국내세율로 계산함 — 조약 제한세율 상한은 {_RATE_TOOL}로 확인해 treaty_rate에 넣는다. ")
    return _issue("조약 적용 절차",
                  head + f"제한세율 적용신청서를 지급 전에 받지 못하면 treaty_rate 없이 국내세율로 원천징수({art}제3항), 뒤에 5년 내 경정청구(제5항). "
                  "받은 신청서는 다음 해 2월 말일까지 세무서 제출(제4항, 2025.12.23. 신설" + (" — 2026년 신청분부터)" if side else " — 적용례는 부칙 확인)"),
                  [f"{art}제3항·제4항·제5항", _RATE_TOOL])


def exemption_issue(side: int) -> dict:
    art = "법인세법 제98조의4" if side else "소득세법 제156조의2"
    return _issue("조약 면제 신청",
                  f"조약상 면제(고정사업장 없음 등)에 해당하면 세액 0 — 비과세·면제신청서({art})가 있어야 하고, 없으면 국내세율. 면제 여부 판단은 조문 MCP tax_treaty로(유추 — 직접 회신 없음)",
                  [art + ("제1항·제3항" if side else "(세부 요건은 조문 MCP로 확인)"), "korean-tax-mcp tax_treaty"])


def compliance_issue(side: int, kind: str) -> dict:
    if side:
        txt = "지급할 때 징수해 다음 달 10일까지 납부(법인세법 제98조제1항), 지급명세서는 다음 해 2월 말일(제120조의2제1항)"
        refs = ["법인세법 제98조제1항", "법인세법 제120조의2제1항", "지방세법 제103조의52제1항·제2항"]
    else:
        txt = "지급할 때 징수해 다음 달 10일까지 납부(소득세법 제156조제1항), 지급명세서는 다음 해 2월 말일(제164조의2제1항)"
        refs = ["소득세법 제156조제1항", "소득세법 제164조의2제1항", "지방세법 제103조의18제1항"]
    txt += " — 기한을 넘기면 가산세는 withholding_late_payment_penalty(함께 특별징수한 지방소득세분은 tax='local')"
    if kind == "사용료":
        txt += ". 미지급으로 계상만 한 사용료는 지급 전까지 원천징수 없음(지급시기 의제 규정 없음, 법인세법 시행령 제137조 — 유추)"
        refs.append("법인세법 시행령 제137조")
    elif kind == "배당":
        txt += ". 미지급 배당은 지급시기 의제 여부 확인(법인세법 시행령 제137조제1항, 기본통칙 98-137…1)"
        refs.append("법인세법 시행령 제137조제1항")
    return _issue("납부·신고 기한", txt, refs + ["withholding_late_payment_penalty 도구"])


def gross_up_issue(side: int, net_of_tax: bool, bears_local: bool) -> dict:
    if net_of_tax:
        txt = ("순액 약정으로 보고 과세표준을 역산함(약정액 ÷ (1 − 세율), 법인세법 기본통칙 98-0…2)"
               + (" — 지방소득세분을 세율에 더한 것은 유추(국이22601-403 요지)" if bears_local else " — 지방소득세도 지급자가 부담하면 payer_bears_local_tax=True"))
    else:
        txt = ("amount를 총액으로 계산함 — 세금 공제 후 금액을 지급하는 순액 약정이면 net_of_tax=True로 역산(법인세법 기본통칙 98-0…2), "
               "지방소득세도 지급자가 부담하면 payer_bears_local_tax=True(유추)")
    if not side:
        txt += ". 비거주자(개인)에 이 통칙 산식을 쓰는 것은 유추"
    return _issue("순액(세금부담) 약정", txt, ["법인세법 기본통칙 98-0…2", "국이22601-403(1991.7.19.)"])


def royalty_issues(side: int, treaty_rate_given: bool, base_amount: int, net_of_tax: bool, bears_local: bool) -> list[dict]:
    """사용료 — 금액을 바꾸는 사실 한 줄씩. 판단 근거는 조문 MCP royalty_withholding_guide."""
    lim = 100_000_000
    if base_amount > lim:
        thr = f"이 건 {base_amount:,}원은 무형자산거래 1억원을 넘음(국제거래명세서 대상)"
    elif base_amount == lim:
        thr = "이 건은 정확히 1억원 — 국제거래명세서 면제 기준(1억원 이하)의 경계값, 다른 무형자산거래와 합산"
    else:
        thr = f"이 건 {base_amount:,}원은 무형자산거래 1억원 이하 — 다른 무형자산거래와 합산"
    if net_of_tax:
        thr += "(역산 과세표준 기준 — 대납세액 포함 여부는 미확인)"
    return [
        _issue("국내 미등록 특허",
               "국내에 등록되지 않은 특허라도 특허기술이 국내 제조·판매에 사실상 사용되면 국내원천 사용료(대법원 2025.9.18. 선고 2021두59908 전원합의체) — "
               f"국외 사용으로 입증된 부분만 amount에서 뺀다. 판단은 {GUIDE}",
               [GUIDE]),
        _issue("소득 구분·세율",
               "대가의 성격(특허·노하우, 저작권, 소프트웨어, 용역, 양도대가, 침해 배상)에 따라 income_kind와 treaty_rate가 달라짐 — "
               f"구분은 {GUIDE}, 세율은 {_RATE_TOOL}",
               [GUIDE, _RATE_TOOL]),
        relief_issue(side, treaty_rate_given),
        compliance_issue(side, "사용료"),
        _issue("정상가격(이전가격)",
               "특수관계인에게 준 금액이 정상가격을 넘으면 초과분은 제한세율 상한 밖일 수 있고 손금 부인 대상 — arm_length_range. "
               + thr + "(국제조세조정에 관한 법률 시행령 제36조제1호) — international_transaction_statement",
               ["국제조세조정에 관한 법률 제7조 · 시행령 제36조제1호", "arm_length_range · international_transaction_statement 도구", GUIDE]),
        _issue("다른 세목",
               "사용료를 면세사업에 쓰면 부가가치세 대리납부(부가가치세법 제52조제1항) — vat_reverse_charge. "
               "수입물품과 관련된 권리사용료는 관세 과세가격에 더함(관세법 제30조제1항제4호 — 판례는 미확인)",
               ["부가가치세법 제52조제1항", "관세법 제30조제1항제4호", "vat_reverse_charge 도구"]),
        gross_up_issue(side, net_of_tax, bears_local),
    ]


def common_issues(side: int, kind: str, treaty_rate_given: bool, net_of_tax: bool, bears_local: bool) -> list[dict]:
    """이자·배당·인적용역·기타 — 절차와 기한."""
    out = [exemption_issue(side) if kind == "인적용역" else relief_issue(side, treaty_rate_given), compliance_issue(side, kind)]
    if net_of_tax:
        out.append(gross_up_issue(side, True, bears_local))
    return out
