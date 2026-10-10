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
