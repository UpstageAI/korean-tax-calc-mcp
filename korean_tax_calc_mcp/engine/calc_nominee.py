"""명의신탁재산 증여의제(상속세 및 증여세법 제45조의2) 증여세 — 증여의제일의 시행본으로 과세표준·산출세액·신고세액공제·납부할세액과
납세의무자(2019.1.1. 이후 의제분 실제소유자)를 계산. Claude 작성(2026-11-14).

대조한 원문(국세법령정보시스템 연혁본, 2026-11-14):
- 상속세 및 증여세법 2016.1.1.~2026.1.1. 연말 시행본 제4조의2·제45조의2·제47조·제55조·제68조, 부칙 법률 제16102호 제3조·제6조
- 제55조제1항제1호(명의신탁재산의 증여 의제: 그 명의신탁재산의 금액 − 감정평가수수료)는 2016~2026 시행본 모두 같음 → 증여재산공제(제53조, 같은 항 제4호) 없음
- 2019.1.1. 이후 증여 의제분: 납세의무자 실제소유자(제4조의2제2항), 명의자 물적납세의무(제9항), 합산배제(제47조제1항) — 부칙 제3조.
  2018.12.31. 이전 소유권 취득 + 명의개서 해태로 2019.1.1. 이후 의제되는 분은 종전 규정(부칙 제6조)
세율·과세최저한·신고세액공제율·감정평가수수료 한도는 gift_tax와 같은 연도표(calc_inhgift)를 쓴다.
"""
from datetime import date, timedelta

from .. import vocab
from .calc_inhgift import _감정평가수수료, 증여세_산출세액
from .exact import floor_won as _floor

_L = "상속세 및 증여세법"
D2019 = date(2019, 1, 1)


def deemed_date(trust_type, registration_date=None, acquisition_date=None):
    if trust_type == "명의개서해태":
        return date(acquisition_date.year + 2, 1, 1)
    return registration_date


def regime(deemed, trust_type, acquisition=None):
    if deemed < D2019:
        return "종전", "2018.12.31. 이전 증여 의제분 — 법률 제16102호 개정 전 규정"
    if trust_type == "명의개서해태" and acquisition is not None and acquisition < D2019:
        return "종전", "2018.12.31. 이전 소유권 취득 + 명의개서 해태로 2019.1.1. 이후 의제되는 분 — 법률 제16102호 부칙 제6조(종전 규정)"
    return "신", "2019.1.1. 이후 증여로 의제되는 분 — 법률 제16102호 부칙 제3조"


def due_date(deemed):
    """증여의제일이 속하는 달의 말일부터 3개월(제68조제1항) — 휴일 이월 전."""
    m = deemed.month + 3
    y, m = deemed.year + (m - 1) // 12, (m - 1) % 12 + 1
    return date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)


def nominee_gift_tax(asset_value, trust_type="타인명의", deemed_gift_date=None, acquisition_date=None, appraisal_fee=0,
                     share_appraisal_fee=0, share_appraisal_count=1, filed=True, nominee_kind="개인", prior_gifts_same_donor=0,
                     prior_gift_tax_paid=0, prior_gifts_deduction=0):
    문제 = []
    if trust_type not in ("타인명의", "명의개서해태"):
        문제.append(f"trust_type='{trust_type}' — 타인명의 | 명의개서해태")
    if nominee_kind not in ("개인", "영리법인", "비영리법인"):
        문제.append(f"nominee_kind='{nominee_kind}' — 개인 | 영리법인 | 비영리법인")
    for n, v in (("asset_value", asset_value), ("appraisal_fee", appraisal_fee), ("share_appraisal_fee", share_appraisal_fee),
                 ("prior_gifts_same_donor", prior_gifts_same_donor), ("prior_gift_tax_paid", prior_gift_tax_paid),
                 ("prior_gifts_deduction", prior_gifts_deduction)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            문제.append(f"{n} — 0 이상의 정수(원)")
    dd = acq = None
    try:
        dd = date.fromisoformat(deemed_gift_date) if deemed_gift_date else None
        acq = date.fromisoformat(acquisition_date) if acquisition_date else None
    except (TypeError, ValueError):
        문제.append("날짜 — YYYY-MM-DD")
    if not 문제:
        if trust_type == "명의개서해태":
            if acq is None:
                문제.append("acquisition_date — 명의개서해태는 소유권취득일이 필요(증여의제일은 다음 해 말일의 다음 날, 평가기준일은 취득일)")
            else:
                calc_dd = deemed_date(trust_type, None, acq)
                if dd is not None and dd != calc_dd:
                    문제.append(f"deemed_gift_date {dd} ≠ 소유권취득일 {acq}의 다음 해 말일의 다음 날 {calc_dd}(제45조의2제1항)")
                dd = calc_dd
        elif dd is None:
            문제.append("deemed_gift_date — 명의자 명의로 등기등·명의개서를 한 날")
    if not 문제 and not (date(2016, 1, 1) <= dd <= date(2026, 12, 31)):
        문제.append(f"증여의제일 {dd} — 2016-01-01~2026-12-31 의제분만 지원(연도표 없는 해는 계산하지 않음)")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    reg, why = regime(dd, trust_type, acq)
    # 종전 체계(2018.12.31. 이전 의제분 등): 제47조제1항 괄호(합산배제증여재산)에 제45조의2가 없어 같은 증여자 10년 내 증여재산가액을 가산(제47조제2항, 1천만원 이상).
    # 제55조제1항제1호는 명의신탁재산에 공제를 인정하지 않는다는 뜻이고 재차증여 가산을 배제하지 않음 — 서면-2016-상속증여-5376(2016.10.21.), 서울고등법원 2016누33027(2016.8.16.)
    합산 = reg == "종전" and prior_gifts_same_donor >= 10_000_000
    if 합산 and prior_gifts_deduction > prior_gifts_same_donor:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["prior_gifts_deduction이 prior_gifts_same_donor보다 큼"]}
    if not 합산 and (prior_gift_tax_paid or prior_gifts_deduction):
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["prior_gift_tax_paid·prior_gifts_deduction은 종전 체계 의제분에 1천만원 이상의 prior_gifts_same_donor를 가산할 때만 씀(2019.1.1. 이후 의제분은 합산배제)"]}
    year = dd.year
    ymd = year * 10000 + dd.month * 100 + dd.day
    수수료 = _감정평가수수료(year, appraisal_fee, share_appraisal_fee, share_appraisal_count)
    가산분_과세표준 = (prior_gifts_same_donor - prior_gifts_deduction) if 합산 else 0
    과세표준 = max(0, asset_value + 가산분_과세표준 - 수수료)
    최저 = vocab.rule("상증_과세최저한", year)["금액"]
    산출세액 = 0 if 과세표준 < 최저 else 증여세_산출세액(과세표준, year)
    율 = vocab.rule_on("상증_신고세액공제율", ymd)["율"]
    납부세액공제_한도 = _floor(산출세액, 가산분_과세표준, div=과세표준) if (합산 and 과세표준) else 0
    납부세액공제 = min(prior_gift_tax_paid, 납부세액공제_한도) if 합산 else 0
    신고공제 = _floor(산출세액 - 납부세액공제, 율) if filed else 0
    납부 = 산출세액 - 납부세액공제 - 신고공제

    corp = nominee_kind == "영리법인"
    if reg == "신":
        납세 = {"납세의무자": "실제소유자", "납세의무 근거": f"{_L} 제4조의2제2항(명의자가 영리법인이어도 같음)",
              "연대납세의무": "없음(구 제4조의2제5항제4호 삭제)",
              "물적납세의무": "명의자 — 실제소유자 체납 + 다른 재산으로 징수 부족 시 명의신탁재산으로 징수(제4조의2제9항)",
              "합산": "합산배제증여재산(제47조제1항) — 같은 증여자 10년 합산 없음" + (f", 입력한 prior_gifts_same_donor {prior_gifts_same_donor:,}원은 쓰지 않음" if prior_gifts_same_donor else "")}
    else:
        납세 = {"납세의무자": "실제소유자(명의자가 영리법인 — 구 제45조의2제2항)" if corp else "명의자(수증자)",
              "납세의무 근거": f"{_L} 구 제45조의2제2항" if corp else f"{_L} 제4조의2제1항",
              "연대납세의무": "해당 없음" if corp else "실제소유자(구 제4조의2제5항제4호)",
              "물적납세의무": "없음",
              "합산": (f"같은 증여자 10년 내 증여재산가액 {prior_gifts_same_donor:,}원을 가산(제47조제2항) — 가산분 과세표준 {가산분_과세표준:,}원" if 합산
                     else "가산 없음(같은 증여자 10년 내 증여재산가액 합계 1천만원 미만 — 제47조제2항)")}
    결과 = {"증여의제일": dd.isoformat(), "평가기준일": (acq or dd).isoformat(), "적용 규정": "2019.1.1. 이후 체계" if reg == "신" else "종전 체계",
          "재산가액": asset_value, "감정평가수수료": 수수료, "증여재산공제": 0, "과세표준": 과세표준, "과세최저한": 과세표준 < 최저,
          "산출세액": 산출세액, "신고세액공제율": 율, "신고세액공제": 신고공제, "납부할세액": 납부,
          **({"가산한_증여재산가액": prior_gifts_same_donor, "가산분_공제": prior_gifts_deduction, "가산분_과세표준": 가산분_과세표준,
              "납부세액공제": 납부세액공제, "납부세액공제_한도": 납부세액공제_한도} if 합산 else {}),
          "법정신고기한(이월 전)": due_date(dd).isoformat(), **납세}
    판단 = [{"항목": "적용 규정", "결론": why, "근거": "법률 제16102호 부칙 제3조·제6조"},
          ({"항목": "과세표준", "결론": f"명의신탁재산의 금액 {asset_value:,} + 10년 내 같은 증여자 증여재산 과세표준 {가산분_과세표준:,}"
                                  f"({prior_gifts_same_donor:,} − 그 증여의 공제 {prior_gifts_deduction:,}) − 감정평가수수료 {수수료:,} = {과세표준:,} — 명의신탁재산에는 증여재산공제 없음",
            "근거": f"{_L} 제47조제2항·제55조제1항제1호(2016~2018 시행본), 서면-2016-상속증여-5376(2016.10.21.), 서울고등법원 2016누33027(2016.8.16.)"} if 합산 else
           {"항목": "과세표준", "결론": f"명의신탁재산의 금액 {asset_value:,} − 감정평가수수료 {수수료:,} = {과세표준:,} — 증여재산공제 없음", "근거": f"{_L} 제55조제1항제1호"}),
          {"항목": "평가기준일", "결론": (f"소유권취득일 {acq} 기준 평가액을 asset_value로 넣어야 함" if trust_type == "명의개서해태"
                                     else f"증여의제일 {dd} 기준 평가액"), "근거": f"{_L} 제45조의2제1항"}]
    근거 = [[_L, "제45조의2", "①", "명의신탁재산의 증여 의제"], [_L, "제4조의2", "②⑨" if reg == "신" else "①", "납부의무"],
          [_L, "제47조", "①", "합산배제증여재산"], [_L, "제55조", "①1호·②", "과세표준·과세최저한"], [_L, "제56조", "", "세율(제26조 준용)"],
          [_L, "제69조", "②", "신고세액공제"], [_L, "제68조", "①", "신고기한"]]
    주의 = ["요건(대상 재산, 조세회피목적 추정·반증, 반복 과세 제한)은 조문 MCP nominee_trust_guide로 확인 — 이 도구는 증여의제를 전제로 세액만 계산",
          "세대생략 할증(제57조)은 계산하지 않음 — 조세심판원이 명의신탁 증여의제에 할증과세를 적용한 처분을 잘못이라고 결정(조심 2014서5656, 2015.5.21.). 법원 판결·예규는 찾지 못함(국세법령정보시스템 검색 2026-11-15)",
          "무신고·납부지연 가산세는 계산하지 않음"]
    if 합산:
        판단.insert(2, {"항목": "납부세액공제", "결론": f"한도 = 산출세액 {산출세액:,} × 가산분 과세표준 {가산분_과세표준:,} ÷ 과세표준 {과세표준:,} = {납부세액공제_한도:,}, "
                                            f"가산한 증여에 대한 증여세 산출세액 {prior_gift_tax_paid:,} → 공제 {납부세액공제:,}", "근거": f"{_L} 제58조"})
        주의.append("가산한 증여가 일반 증여일 때 그 증여의 증여재산공제를 합산 과세표준에서 빼는지는 해석을 찾지 못함(국세법령정보시스템 검색 2026-11-15) — "
                  "prior_gifts_deduction에 넣은 금액만 뺌(가산분이 명의신탁 의제분이면 0)")
    return {"결과": 결과, "판단": 판단, "근거": 근거, "주의": 주의}
