"""세액 계산은 LLM이 하지 않는다. 적출 사실(JSON)을 받아 법정 산식으로 계산. 작성 Mia(윤승미)
세율·이자율은 연도표(calc_cit.YEAR) 기준. hardcode 대신 사업연도별 표(2016~2026)를 경유한다."""
from datetime import date

RATE_OVERDRAFT = 0.046  # 당좌대출이자율 (법인세법 시행규칙 제43조제2항) — 연도별 변동 없음, 조문 조회로 확인


def won(x): return int(round(x))


def corp_tax(base, year=2025):
    """법인세 산출세액(calc_cit.YEAR[year]['세율'] 경유). year=2025가 기본."""
    from .calc_cit import YEAR as CIT_YEAR
    tiers = CIT_YEAR[year]["세율"]
    tax, prev = 0, 0
    for cap, r in tiers:
        if base > prev: tax += (min(base, cap) - prev) * r
        prev = cap
    return won(tax)


def days(a, b): return (date.fromisoformat(b) - date.fromisoformat(a)).days + 1


def deemed_interest(segments, year_end=None, rate=RATE_OVERDRAFT):
    """segments=[{from:'2025-01-01', 잔액:800000000}, ...] — 그날부터 다음 구간 전날까지의 잔액으로 적수 계산.
    year_end 미지정 시 사업연도 종료일( Calc_cit.YEAR 기준 2025-12-31 )."""
    if year_end is None: year_end = "2025-12-31"
    seg = sorted(({"from": s["from"], "bal": int(s.get("잔액", s.get("amount", 0)))} for s in segments), key=lambda x: x["from"])
    """segments=[{from:'2025-01-01', 잔액:800000000}, {from:'2025-04-01', 잔액:1200000000}] — 그날부터 다음 구간 전날까지의 잔액으로 적수 계산."""
    seg = sorted(({"from": s["from"], "bal": int(s.get("잔액", s.get("amount", 0)))} for s in segments), key=lambda x: x["from"])
    parts, jeoksu = [], 0
    for i, s in enumerate(seg):
        end = (date.fromisoformat(seg[i + 1]["from"]).toordinal() - 1) if i + 1 < len(seg) else date.fromisoformat(year_end).toordinal()
        d = end - date.fromisoformat(s["from"]).toordinal() + 1; jeoksu += s["bal"] * d; parts.append(f"{s['bal']:,}원×{d}일")
    return {"적수": jeoksu, "이자율": rate, "인정이자": won(jeoksu * rate / 365), "산식": " + ".join(parts) + f" = 적수 {jeoksu:,} × {rate*100:.1f}% ÷ 365"}


def interest_disallow(interest_paid, loan_jeoksu, borrow_amount, year_days=365):
    b = borrow_amount * year_days
    return {"지급이자": interest_paid, "가지급금적수": loan_jeoksu, "차입금적수": b,
            "손금불산입": won(interest_paid * min(1, loan_jeoksu / b)), "산식": f"{interest_paid:,} × {loan_jeoksu:,} / {b:,}"}


def entertain_limit(revenue, sme=True, months=12):
    base = (36_000_000 if sme else 12_000_000) * months / 12
    r = min(revenue, 10_000_000_000) * 0.003 + max(0, min(revenue, 50_000_000_000) - 10_000_000_000) * 0.002 + max(0, revenue - 50_000_000_000) * 0.0003
    return {"기본한도": won(base), "수입금액한도": won(r), "한도": won(base + r)}


def cb_conversion_gain(pre_price, pre_shares, conv_price, new_shares):
    """상증법 시행령 제30조: 교부받은 주식가액 = (전환 전 1주 평가액×전환 전 주식수 + 전환가액×증가 주식수) ÷ 전환 후 주식수"""
    after = (pre_price * pre_shares + conv_price * new_shares) / (pre_shares + new_shares)
    return {"교부주식가액": round(after, 2), "전환이익": won((after - conv_price) * new_shares),
            "산식": f"({pre_price:,}×{pre_shares:,} + {conv_price:,}×{new_shares:,}) ÷ {pre_shares+new_shares:,} = {after:,.2f}원; ({after:,.2f}−{conv_price:,})×{new_shares:,}"}


def vat_input_disallow(supply): return won(supply * 0.1)


def penalty_underreport(tax, fraud):
    return won(tax * (0.4 if fraud else 0.1))  # 국세기본법 제47조의3


def penalty_late(tax, due, until):
    return won(tax * 0.00022 * (date.fromisoformat(until) - date.fromisoformat(due)).days)  # 국세기본법 제47조의4


def fake_invoice_rate(issued_on=""):
    """가공 세금계산서 발급·수취 가산세율(부가가치세법 제60조③1·2호, 발급·수취일 기준 — 각 개정 부칙 경과조치):
    2017.12.31. 이전 2%(구 ③ 본문, 2016.12.20. 개정본 포함), 2018.1.1. 이후 3%(2017.12.19. 개정, 부칙 제6조),
    2026.1.1. 이후 4%(2025.12.23. 개정, 부칙 제3조). 날짜 미입력은 종전 호환 3%.
    과세표준: 2019.12.31. 이전은 '세금계산서등에 적힌 금액', 2020.1.1. 이후 '적힌 공급가액'(2019.12.31. 개정)."""
    if issued_on and issued_on >= "2026-01-01": return 0.04
    if issued_on and issued_on < "2018-01-01": return 0.02
    return 0.03


def penalty_fake_invoice(supply, issued_on=""): return won(supply * fake_invoice_rate(issued_on))  # 부가가치세법 제60조③2호(가공 수취)


# ── 결손금·이월결손금 공제(소득세법 제45조) ──────────────────────────────────────────


def _income_loss_offset_core(year, incomes, carryforwards, estimated, financial_flat_rate, business):
    """income_loss_offset 내부 계산 로직. history 계산에도 재사용."""

    # 사업소득 계산 (business 인자 사용 시)
    사업소득_계산과정 = None
    if business is not None:
        if "사업" in incomes and incomes["사업"] != 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["incomes['사업']과 business를 함께 입력할 수 없음 — 둘 중 하나만 사용"]}
        book_income = int(business.get("book_income", 0))
        adjustments = business.get("adjustments", [])
        # 조정 항목별로 가산/차감 구분
        가산합계 = 0
        차감합계 = 0
        조정내역 = []
        for adj in adjustments:
            kind = adj.get("kind")
            amount = int(adj.get("amount", 0))
            if kind == "사업주_본인_급여":
                가산합계 += amount
                조정내역.append({"항목": "사업주 본인 급여 (필요경비 불산입)", "금액": amount, "구분": "가산",
                                 "근거": "질의회신 소득46011-21386(2000.11.30): 개인기업체 사업주 급료는 필요경비 불산입"})
            elif kind == "가사관련경비":
                가산합계 += amount
                조정내역.append({"항목": "가사관련경비 (필요경비 불산입)", "금액": amount, "구분": "가산",
                                 "근거": "소득세법 제33조①: 가사 관련 경비는 필요경비 불산입"})
            elif kind == "기타_가산":
                가산합계 += amount
                조정내역.append({"항목": "기타 가산", "금액": amount, "구분": "가산"})
            elif kind == "기타_차감":
                차감합계 += amount
                조정내역.append({"항목": "기타 차감", "금액": amount, "구분": "차감"})
            else:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"지원하지 않는 adjustment kind='{kind}' — 허용: 사업주_본인_급여, 가사관련경비, 기타_가산, 기타_차감"]}
        사업소득금액 = book_income + 가산합계 - 차감합계
        사업소득_계산과정 = {
            "장부상 사업 손익": book_income,
            "가산 합계": 가산합계,
            "차감 합계": 차감합계,
            "사업소득금액": 사업소득금액,
            "조정 내역": 조정내역,
        }
        after = {
            "사업": 사업소득금액,
            "부동산임대": incomes.get("부동산임대", 0),
            "근로": incomes.get("근로", 0),
            "연금": incomes.get("연금", 0),
            "기타": incomes.get("기타", 0),
            "이자": incomes.get("이자", 0),
            "배당": incomes.get("배당", 0),
        }
    else:
        # business 없이 incomes['사업']만 오면 오류 (옛 금액 입력 거절)
        if "사업" in incomes:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["사업소득은 business로 넣어 주세요. "
                             "예: business={\"book_income\": 장부 손익, \"adjustments\": [{\"kind\": \"사업주_본인_급여\", \"amount\": ...}]}"]}
        after = {
            "사업": incomes.get("사업", 0),
            "부동산임대": incomes.get("부동산임대", 0),
            "근로": incomes.get("근로", 0),
            "연금": incomes.get("연금", 0),
            "기타": incomes.get("기타", 0),
            "이자": incomes.get("이자", 0),
            "배당": incomes.get("배당", 0),
        }

    공제내역 = []
    소멸목록 = []

    # 주거용 건물 임대업 결손금은 부동산임대업 결손금 제한(제45조②)의 예외 — 사업 결손금처럼 다른 소득에서 공제
    주거용임대 = int(incomes.get("주거용임대", 0) or 0)
    if 주거용임대:
        after["사업"] += 주거용임대
        공제내역.append({"결손금": "주거용 건물 임대업", "공제한 소득": "사업소득에 합산(제45조② 단서)", "금액": 주거용임대})

    # 이자·배당 중 원천징수세율 적용분(금융소득 분리과세분) 제외
    이자대상 = after["이자"]
    배당대상 = after["배당"]
    from_이자 = 0
    from_배당 = 0
    if financial_flat_rate > 0:
        from_이자 = min(이자대상, financial_flat_rate)
        남은요율 = financial_flat_rate - from_이자
        from_배당 = min(배당대상, 남은요율)
        이자대상 -= from_이자
        배당대상 -= from_배당

    # after에는 분리과세분 포함 전체 금액을 저장 (결과 출력용)
    after["이자"] = from_이자 + max(0, 이자대상)
    after["배당"] = from_배당 + max(0, 배당대상)

    # --- 1) 당기 사업 결손금 공제 ---
    사업결손 = after["사업"]
    if 사업결손 >= 0:
        사업_이월잔액 = 0
    else:
        사업결손 = abs(사업결손)
        after["사업"] = 0

        # 공제 순서: 부동산임대 → 근로 → 연금 → 기타 → 이자(공제 대상분) → 배당(공제 대상분)
        공제순서 = [
            ("부동산임대", after["부동산임대"]),
            ("근로", after["근로"]),
            ("연금", after["연금"]),
            ("기타", after["기타"]),
            ("이자", max(0, 이자대상)),
            ("배당", max(0, 배당대상)),
        ]

        남은결손 = 사업결손
        for 소득명, 소득금액 in 공제순서:
            if 남은결손 > 0 and 소득금액 > 0:
                공제액 = min(남은결손, 소득금액)
                if 소득명 == "이자":
                    after["이자"] -= 공제액
                    이자대상 -= 공제액
                elif 소득명 == "배당":
                    after["배당"] -= 공제액
                    배당대상 -= 공제액
                else:
                    after[소득명] -= 공제액
                남은결손 -= 공제액
                공제내역.append({"결손금": "사업(당기)", "공제한 소득": 소득명, "금액": 공제액})

        사업_이월잔액 = 남은결손

    # --- 2) 당기 부동산임대 결손금: 다른 소득에서 공제 안 함. 전액 이월결손금 ---
    부동산임대결손 = after["부동산임대"]
    if 부동산임대결손 < 0:
        부동산임대_이월잔액 = abs(부동산임대결손)
        after["부동산임대"] = 0
    else:
        부동산임대_이월잔액 = 0

    # --- 3) 이월결손금 ---
    # 발생연도별로 남은 금액을 따로 들고 다님 — 소멸기한(제45조③: 2019년 이전 발생 10년, 2020년 이후 발생 15년)이
    # 발생연도 기준이므로 다음 연도로 넘길 때 연도를 덮어쓰지 않는다.
    # 추계신고·추계결정 연도(estimated=True)는 이월결손금을 공제하지 않지만(제45조④) 소멸시키지도 않는다 — 그대로 다음 연도로.
    남은_목록 = []
    추계_공제배제 = []
    sorted_cf = sorted(carryforwards, key=lambda x: x["year"])
    for cf in sorted_cf:
        cf_year = cf["year"]
        cf_kind = cf["kind"]
        cf_amount = cf["amount"]
        if cf_amount <= 0:
            continue

        유효기간 = 15 if cf_year >= 2020 else 10
        if cf_year + 유효기간 < year:
            소멸목록.append({
                "연도": cf_year, "종류": cf_kind, "금액": cf_amount,
                "사유": f"{cf_year}년 발생 이월결손금({유효기간}년 경과) 소멸",
            })
            continue

        amount = cf_amount

        if estimated:
            추계_공제배제.append({"연도": cf_year, "종류": cf_kind, "금액": amount,
                              "사유": "추계 연도 — 공제하지 않고 다음 연도로 이월(제45조④)"})
        elif cf_kind == "사업":
            공제순서_cf = [
                ("사업", after["사업"]),
                ("부동산임대", after["부동산임대"]),
                ("근로", after["근로"]),
                ("연금", after["연금"]),
                ("기타", after["기타"]),
                ("이자", max(0, 이자대상)),
                ("배당", max(0, 배당대상)),
            ]
            for 소득명, 공제대상금액 in 공제순서_cf:
                if amount > 0 and 공제대상금액 > 0:
                    공제액 = min(amount, 공제대상금액)
                    if 소득명 == "이자":
                        after["이자"] -= 공제액
                        이자대상 -= 공제액
                    elif 소득명 == "배당":
                        after["배당"] -= 공제액
                        배당대상 -= 공제액
                    else:
                        after[소득명] -= 공제액
                    amount -= 공제액
                    공제내역.append({"결손금": f"사업(이월 {cf_year}년)", "공제한 소득": 소득명, "금액": 공제액})

        elif cf_kind == "부동산임대":
            if after["부동산임대"] > 0:
                공제액 = min(amount, after["부동산임대"])
                after["부동산임대"] -= 공제액
                amount -= 공제액
                공제내역.append({"결손금": f"부동산임대(이월 {cf_year}년)", "공제한 소득": "부동산임대", "금액": 공제액})

        if amount > 0:
            if cf_kind == "사업":
                사업_이월잔액 += amount
            elif cf_kind == "부동산임대":
                부동산임대_이월잔액 += amount
            남은_목록.append({"year": cf_year, "kind": cf_kind, "amount": amount})

    # 당기 발생분은 당기 연도로 이월
    당기_사업 = 사업_이월잔액 - sum(x["amount"] for x in 남은_목록 if x["kind"] == "사업")
    당기_임대 = 부동산임대_이월잔액 - sum(x["amount"] for x in 남은_목록 if x["kind"] == "부동산임대")
    if 당기_사업 > 0:
        남은_목록.append({"year": year, "kind": "사업", "amount": 당기_사업})
    if 당기_임대 > 0:
        남은_목록.append({"year": year, "kind": "부동산임대", "amount": 당기_임대})
    남은_목록.sort(key=lambda x: x["year"])

    종합소득금액 = sum(after.values())

    return {
        "after": after,
        "사업_이월잔액": 사업_이월잔액,
        "부동산임대_이월잔액": 부동산임대_이월잔액,
        "공제내역": 공제내역,
        "소멸목록": 소멸목록,
        "사업소득_계산과정": 사업소득_계산과정,
        "종합소득금액": 종합소득금액,
        "이월잔액_목록": 남은_목록,
        "추계_공제배제": 추계_공제배제,
    }


def income_loss_offset(year, incomes, carryforwards=None, estimated=False, financial_flat_rate=0, business=None, history=None):
    """결손금·이월결손금 공제 후 종합소득금액. 소득세법 제45조.

    입력:
      year: 귀속연도(2016~2026)
      incomes: {"부동산임대":, "주거용임대":, "근로":, "연금":, "기타":, "이자":, "배당"} (소득금액, 음수=결손금)
        부동산임대 = 주거용 건물 임대업을 뺀 부동산임대업(결손금은 부동산임대 소득에서만 공제, 제45조②)
        주거용임대 = 주거용 건물 임대업(제45조② 단서 — 결손금도 사업 결손금처럼 다른 종합소득에서 공제)
      carryforwards: [{year, kind: "사업"|"부동산임대", amount}] (기본 [])
      estimated: 추계 여부(True면 그 연도 이월결손금 공제 안 함 — 소멸되지 않고 다음 연도로 이월, 제45조④)
      financial_flat_rate: 이자·배당 중 원천징수세율 적용분 합계(이자에서 먼저, 남으면 배당에서 뺀 금액이 공제 대상)
      business: {book_income: 장부상 사업 손익(원, 손실은 음수), adjustments:[{kind, amount}]} — 사업소득은 business로 입력
      history: [{year, incomes, business?, financial_flat_rate?, estimated?}] — 대상 연도보다 앞선 연도들. year 오름차순으로 계산 후 이월결손금을 다음 연도로 넘김.
    결과: {"공제 후 소득금액": {7개 소득별}, "종합소득금액"(합계),
           "이월결손금(다음 연도로)": {"사업", "부동산임대"},
           "공제 내역": [{"결손금", "공제한 소득", "금액"}], "소멸": [...],
           "이력_계산": [{year, 종합소득금액, 남은_결손금}]}
    """
    if year < 2016 or year > 2026:
        return {"error": f"입력 확인 필요 — 계산하지 않음", "문제": [f"year={year}은(는) 지원 범위(2016~2026) 밖"]}

    if carryforwards is None:
        carryforwards = []

    # history와 carryforwards 동시 입력 금지
    if history is not None and carryforwards:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["history와 carryforwards 중 하나만 사용"]}

    # history 입력 시 검증
    if history is not None:
        for h in history:
            if h["year"] >= year:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"history의 year({h['year']})는 대상 연도({year})보다 작아야 함"]}

    # history가 있으면 history 연도부터 순서대로 계산
    if history is not None:
        # history를 year 오름차순으로 정렬
        sorted_history = sorted(history, key=lambda x: x["year"])
        current_carryforwards = []
        이력_계산 = []

        for h in sorted_history:
            h_result = _income_loss_offset_core(
                h["year"],
                h.get("incomes", {}),
                current_carryforwards,
                h.get("estimated", False),
                h.get("financial_flat_rate", 0),
                h.get("business", None),
            )
            if "error" in h_result:
                return h_result
            # 발생연도별 잔액을 그대로 넘김(소멸기한은 발생연도 기준, 제45조③)
            current_carryforwards = h_result["이월잔액_목록"]
            이력_계산.append({
                "year": h["year"],
                "종합소득금액": h_result["종합소득금액"],
                "남은_결손금": {"사업": h_result["사업_이월잔액"], "부동산임대": h_result["부동산임대_이월잔액"]},
                "남은_결손금_발생연도별": [dict(x) for x in h_result["이월잔액_목록"]],
                "소멸": h_result["소멸목록"],
            })

        # 대상 연도 계산 (history의 이월결손금을 carryforwards로 사용)
        core_result = _income_loss_offset_core(
            year,
            incomes,
            current_carryforwards,
            estimated,
            financial_flat_rate,
            business,
        )
        if "error" in core_result:
            return core_result

        종합소득금액 = core_result["종합소득금액"]
        사업_이월잔액 = core_result["사업_이월잔액"]
        부동산임대_이월잔액 = core_result["부동산임대_이월잔액"]
        공제내역 = core_result["공제내역"]
        소멸목록 = core_result["소멸목록"]
        after = core_result["after"]
        사업소득_계산과정 = core_result["사업소득_계산과정"]
    else:
        # history 없이 기존 방식으로 계산
        core_result = _income_loss_offset_core(
            year,
            incomes,
            carryforwards,
            estimated,
            financial_flat_rate,
            business,
        )
        if "error" in core_result:
            return core_result

        종합소득금액 = core_result["종합소득금액"]
        사업_이월잔액 = core_result["사업_이월잔액"]
        부동산임대_이월잔액 = core_result["부동산임대_이월잔액"]
        공제내역 = core_result["공제내역"]
        소멸목록 = core_result["소멸목록"]
        after = core_result["after"]
        사업소득_계산과정 = core_result["사업소득_계산과정"]
        이력_계산 = []

    결과 = {
        "공제 후 소득금액": {k: after[k] for k in ["사업", "부동산임대", "근로", "연금", "기타", "이자", "배당"]},
        "종합소득금액": 종합소득금액,
        "이월결손금(다음 연도로)": {"사업": 사업_이월잔액, "부동산임대": 부동산임대_이월잔액},
        "공제 내역": 공제내역,
        "소멸": 소멸목록,
        "이력_계산": 이력_계산,
        "이월결손금_발생연도별": core_result["이월잔액_목록"],
    }
    if core_result["추계_공제배제"]:
        결과["추계_공제배제"] = core_result["추계_공제배제"]
    if 사업소득_계산과정 is not None:
        결과["사업소득_계산과정"] = 사업소득_계산과정

    return {
        "결과": 결과,
        "근거": "소득세법 제45조",
    }


# ── 법인 재해손실세액공제(법인세법 제58조, 시행령 제95조) ─────────────────────────────


def disaster_loss_credit(year, assets_before=0, assets_lost=0, current_tax=0,
                         other_credits=0, unpaid_prior_tax=0, penalty=0, assets=None,
                         credit_items=None, penalty_items=None):
    """법인 재해손실세액공제. 법인세법 제58조, 시행령 제95조.

    입력:
      year: 사업연도(2016~2026)
      assets_before: 재해 전 자산총액(토지 제외 사업용자산 + 변상책임 있는 타인 자산, 장부가액) — assets 사용 시 생략
      assets_lost: 상실 자산가액(토지 제외) — assets 사용 시 생략
      current_tax: 재해 발생 사업연도 법인세 산출세액 (공제·감면 전)
      other_credits: 그 법인세에서 먼저 빼는 다른 감면·공제세액 (기존 호환용)
      unpaid_prior_tax: 재해일 현재 미납·미부과 법인세
      penalty: 가산세 (기존 호환용)
      assets: [{구분, 장부가액, 상실액}] — assets_before/assets_lost 대신 사용
      credit_items: [{종류:'조세특례제한법'|'법인세법', 금액}] — 항목형 공제 입력. '조세특례제한법'만 current_tax에서 차감.
      penalty_items: [{근거:'법인세법 제75조의3'|'국세기본법 제47조의2'|'국세기본법 제47조의3'|'국세기본법 제47조의4'|'국세기본법 제47조의5'|'기타', 금액}] — 항목형 가산세 입력.
    결과: {"자산상실비율", "공제대상 법인세", "재해손실세액공제", "판정", "자산계산과정"(assets 사용 시), "판단"(credit_items·penalty_items 사용 시)}
    """
    if year < 2016 or year > 2026:
        return {"error": f"입력 확인 필요 — 계산하지 않음", "문제": [f"year={year}은(는) 지원 범위(2016~2026) 밖"]}

    # credit_items / other_credits 호환 처리
    판단 = []
    if credit_items is not None:
        if other_credits != 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["other_credits와 credit_items를 함께 입력할 수 없음 — 둘 중 하나만 사용"]}
        공제대상_조세특례제한법 = 0
        법인세법상_공제 = []
        for item in credit_items:
            종류 = item["종류"]
            금액 = int(item["금액"])
            if 종류 == "조세특례제한법":
                공제대상_조세특례제한법 += 금액
            elif 종류 == "법인세법":
                법인세법상_공제.append({"종류": "법인세법", "금액": 금액})
            else:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"credit_items: 지원하지 않는 종류='{종류}' — 허용: 조세특례제한법, 법인세법"]}
        other_credits = 공제대상_조세특례제한법
        for item in 법인세법상_공제:
            판단.append({"항목": "법인세법상 공제", "내용": f"법인세법 공제 {item['금액']:,}원 — 공제대상 법인세에서 빼지 않음",
                         "근거": "법인세법 제58조①"})
    elif other_credits != 0:
        pass  # 기존 호환: other_credits 그대로 사용

    # penalty_items / penalty 호환 처리
    if penalty_items is not None:
        if penalty != 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["penalty와 penalty_items를 함께 입력할 수 없음 — 둘 중 하나만 사용"]}
        penalty = 0
        for item in penalty_items:
            근거 = item["근거"]
            금액 = int(item["금액"])
            if 근거 == "기타":
                판단.append({"항목": "가산세(기타)", "내용": f"{근거} {금액:,}원 — 시행령 제95조③ 가산세 대상 아님, 공제대상 법인세에 포함 안 함",
                             "근거": "법인세법 시행령 제95조③"})
                continue
            if 근거 not in ("법인세법 제75조의3", "국세기본법 제47조의2", "국세기본법 제47조의3", "국세기본법 제47조의4", "국세기본법 제47조의5"):
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"penalty_items: 지원하지 않는 근거='{근거}' — 허용: 법인세법 제75조의3, 국세기본법 제47조의2·제47조의3·제47조의4·제47조의5, 기타"]}
            penalty += 금액
    elif penalty != 0:
        pass  # 기존 호환: penalty 그대로 사용

    # assets 목록 처리
    자산계산과정 = None
    if assets is not None:
        if assets_before != 0 or assets_lost != 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["assets와 assets_before·assets_lost를 함께 입력할 수 없음 — assets 또는 assets_before/assets_lost 중 하나만 사용"]}
        # assets 목록 검증 및 합산
        총자산 = 0
        총상실 = 0
        자산내역 = []
        for i, a in enumerate(assets):
            구분 = a.get("구분")
            장부가액 = int(a.get("장부가액", 0))
            상실액 = int(a.get("상실액", 0))
            if 구분 not in ("사업용", "토지", "타인소유_변상책임있음", "타인소유_변상책임없음"):
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"자산 {i+1}: 구분='{구분}'은(는) 지원하지 않음 — 허용: 사업용(토지 제외), 토지, 타인소유_변상책임있음, 타인소유_변상책임없음"]}
            포함여부 = 구분 in ("사업용", "타인소유_변상책임있음")
            자산내역.append({"구분": 구분, "장부가액": 장부가액, "상실액": 상실액, "포함": 포함여부})
            if 포함여부:
                총자산 += 장부가액
                총상실 += 상실액
        if 총자산 <= 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["assets: 포함되는 자산(사업용 또는 변상책임 있는 타인 자산)의 장부가액이 0보다 커야 함"]}
        if 총상실 > 총자산:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"assets: 총상실액({총상실}) > 총자산액({총자산}) 불가능"]}
        assets_before = 총자산
        assets_lost = 총상실
        자산계산과정 = {
            "자산 목록": 자산내역,
            "포함 자산 합계(총자산)": 총자산,
            "포함 상실액 합계": 총상실,
            "제외 자산": [a for a in 자산내역 if not a["포함"]],
            "근거": "법인세법 시행령 제95조①②: 사업용자산(토지 제외) + 변상책임 있는 타인 소유 자산 기준, 장부가액 기준",
        }
    else:
        # assets 없이 assets_before/assets_lost만 오면 오류 (옛 금액 입력 거절)
        if assets_before != 0 or assets_lost != 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["자산은 assets 목록으로 넣어 주세요. "
                             "구분: 사업용 / 토지 / 타인소유_변상책임있음 / 타인소유_변상책임없음"]}

    if assets_before <= 0:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"assets_before({assets_before})는 0보다 커야 함(토지 제외 자산총액)"]}
    if assets_lost > assets_before:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"assets_lost({assets_lost}) > assets_before({assets_before}) 불가능"]}

    자산상실비율 = assets_lost / assets_before

    if 자산상실비율 < 0.2:
        return {
            "결과": {
                "자산상실비율": 자산상실비율,
                "공제대상 법인세": 0,
                "재해손실세액공제": 0,
                "판정": "자산총액의 20% 미만 상실 — 공제 대상 아님",
            },
            "근거": "법인세법 제58조, 시행령 제95조",
        }

    공제대상_법인세 = unpaid_prior_tax + max(current_tax - other_credits, 0) + penalty

    공제액 = int(공제대상_법인세 * 자산상실비율)
    공제액 = min(공제액, assets_lost)

    결과 = {
        "자산상실비율": 자산상실비율,
        "공제대상 법인세": 공제대상_법인세,
        "재해손실세액공제": 공제액,
        "판정": "공제 대상",
    }
    if 자산계산과정 is not None:
        결과["자산계산과정"] = 자산계산과정
        결과["계산안내"] = "시행령 제95조③: 공제대상 법인세에 가산세 포함. 시행령 제95조②: 장부가액 기준."
    if 판단:
        결과["판단"] = 판단

    return {
        "결과": 결과,
        "근거": "법인세법 제58조, 시행령 제95조",
    }
