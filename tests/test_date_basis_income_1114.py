"""소득세 기준일(지급일·발생일·과세기간) 점검 반영 — 정답 테스트. Claude 작성(2026-11-14).

대조한 원문(국세법령정보시스템 응답 캐시 발췌, 고도화_1114/raw_inc_interest·raw_inc_business):
  · 소득세법 2016.1.1.~2026.4.21. 시행본 제12조·제17조③·제86조, 부칙 법률 제14389호·제16104호·제15225호·제18975호·제19196호·제19933호·제20615호·제21221호
  · 소득세법 시행령 2026.10.1. 시행본 부칙 제33267호(제7조①)·제34265호(제4조①)·제36129호(제3조), 2023.10.1.·2024.11.12. 시행본 제143조④·제18조③·제208조⑤
  · 조세특례제한법 제104조의27(2025.12.23. 신설) — 세율표는 원문 그림이라 대조하지 못함(계산하지 않고 '미지원 — 확인 필요')
기대값은 위 조문으로 손으로 계산한 값. 경계일 양쪽과 날짜를 주지 않은 경우를 함께 본다.
"""
from korean_tax_calc_mcp import server as S, vocab
from korean_tax_calc_mcp.audit.agents.precheck import REGISTRY, Data, Missing
from korean_tax_calc_mcp.audit.agents.precheck import income  # noqa: F401 — 규칙 등록

M = 10_000_000


def ok(r):
    assert "error" not in r, r
    return r


# ── vocab.rule_paid ─────────────────────────────────────────────────────────
def test_rule_paid_only_for_payment_basis_boundaries():
    assert vocab.rule_paid("식사대", 2022, "2023-01-10") == (vocab.rule("식사대", 2023), True)        # 받는 분 기준(법률 제18975호 부칙)
    assert vocab.rule_paid("식사대", 2022, "2022-12-30")[0]["월한도"] == 100_000
    assert vocab.rule_paid("식사대", 2022, None)[1] is False
    # 연장근로 2020 기준(영 2020.2.11. 개정)은 과세기간 기준 — 지급일이 다음 해여도 귀속연도 규칙
    assert vocab.rule_paid("연장근로수당", 2019, "2020-01-10") == (vocab.rule("연장근로수당", 2019), False)
    # 2026 기준(영 제36129호 부칙 제3조)은 지급받는 급여부터
    assert vocab.rule_paid("연장근로수당", 2025, "2026-01-10")[0]["직전연도총급여한도"] == 37_000_000


# ── 우선순위 1: 퇴직 후 직무발명보상금 특수관계자 비과세 제외(2024.1.1. 이후 지급분) ──
def _inv(year, **k):
    r = ok(S.other_income_aggregate(year, [{"kind": "직무발명보상금_퇴직후", "amount": M, "employment_exempt_used": 0, **k}]))
    return r, r["항목별"][0]


def test_retired_invention_related_party():
    r, it = _inv(2025, related_party=True)
    assert (it["비과세"], it["소득금액"], it["원천징수세액"]) == (0, M, 2_000_000)
    r, it = _inv(2025, related_party=False)
    assert (it["비과세"], it["소득금액"]) == (7_000_000, 3_000_000) and "주의" not in r
    r, it = _inv(2024, related_party=True, paid_date="2024-01-02")       # 경계 뒤
    assert it["비과세"] == 0
    r, it = _inv(2023, related_party=True)                                # 경계 앞 — 단서 없음
    assert it["비과세"] == 5_000_000


def test_retired_invention_no_related_party_input():
    r, it = _inv(2025)
    assert it["비과세"] == 7_000_000 and any("related_party" in n for n in r["주의"])


# ── 우선순위 1: Gross-up 제외(제17조③1호·6호·7호, 법률 제20615호 부칙 — 2025.1.1. 이후 취득·지급분) ──
def _gu(year, items):
    return ok(S.financial_income_aggregate(year, items))["결과"]["Gross-up"]


def test_capital_reserve_reduction_dividend():
    k = {"kind": "자본준비금감액배당", "amount": 5 * M}
    assert _gu(2025, [{**k, "paid_date": "2025-03-31"}]) == 0
    assert _gu(2024, [{**k, "paid_date": "2024-12-20"}]) == 3_000_000          # (5천만 − 2천만) × 10%
    assert _gu(2024, [{**k, "paid_date": "2025-01-10"}]) == 0                  # 2024 귀속이라도 2025 지급분은 제외
    r = ok(S.financial_income_aggregate(2024, [k]))                             # 날짜 없음 — 귀속연도 기준 + 주의
    assert r["결과"]["Gross-up"] == 3_000_000 and any("paid_date" in n for n in r["주의"])
    assert _gu(2025, [{"kind": "재평가적립금감액배당", "amount": 5 * M}]) == 0


def test_capital_reduction_deemed_dividend():
    k = {"kind": "의제배당_감자", "amount": 5 * M}
    assert _gu(2025, [{**k, "corp_tax_paid": False}]) == 0
    assert _gu(2025, [{**k, "corp_tax_paid": True}]) == 3_000_000
    assert _gu(2024, [{**k, "paid_date": "2024-12-31"}]) == 3_000_000           # 경계 앞 — 제외 사유 없음
    r = S.financial_income_aggregate(2025, [k])
    assert "error" in r and "corp_tax_paid" in r["문제"][0]
    # 의제배당 기존 도구 어휘(취득구분 등)는 그대로
    assert vocab.rule("의제배당_감자", 2025)["단기소각_기간_년"] == 2


def test_dividend_tax_credit_uses_exclusion_and_shows_rates():
    a = ok(S.dividend_tax_credit(2025, items=[{"kind": "자본준비금감액배당", "amount": 5 * M}], other_base=50 * M))
    assert a["결과"]["Gross-up"] == 0
    b = ok(S.dividend_tax_credit(2023, items=[{"kind": "상장법인현금배당", "amount": 5 * M, "paid_date": "2024-01-15"}], other_base=50 * M))
    assert b["계산"]["Gross-up 가산율"].startswith("10%")


# ── 우선순위 1: 고배당기업 배당 특례(조특법 제104조의27, 2026.1.1. 이후 받는 배당) — 신청 여부를 받아 계산 ──
def test_high_dividend_not_silently_listed():
    r = S.financial_income_aggregate(2026, [{"kind": "고배당기업배당", "amount": 5 * M}])
    assert "error" in r and "separate_election" in r["문제"][0]                 # 신청 여부 없으면 계산하지 않음(2026-11-14 특례 계산 반영)
    r = S.financial_income_aggregate(2026, [{"kind": "고배당기업배당", "amount": 5 * M, "separate_election": False}])
    assert r["결과"]["Gross-up"] == 3_000_000 and any("특례 미신청" in n for n in r["주의"])
    r = S.financial_income_aggregate(2025, [{"kind": "고배당기업배당", "amount": 5 * M, "separate_election": False}])
    assert r["error"] == "미지원 — 확인 필요"                                     # 2025.12.31.까지는 이 특례 없음
    r = S.financial_income_aggregate(2025, [{"kind": "고배당기업배당", "amount": 5 * M, "paid_date": "2026-01-05", "separate_election": False}])
    assert r["결과"]["Gross-up"] == 3_000_000


# ── 우선순위 1: 인적용역 단순경비율 직전 수입 기준 3,600만원(영 제143조④2호나목, 2023 과세기간부터) ──
def _est(year, ps):
    return ok(S.estimated_business_income(year=year, industry_group="다", prior_year_revenue=30_000_000,
                                          revenues=[{"구분": "매출", "금액": 30_000_000}], expenses=[],
                                          base_rate=0.2, simple_rate=0.6, personal_service=ps))


def test_personal_service_simple_rate_threshold():
    assert _est(2025, True)["결과"]["사업소득금액"] == 12_000_000       # 단순경비율: 3천만 × (1 − 60%)
    assert _est(2023, True)["계산"]["적용방법"] == "단순경비율"
    assert _est(2022, True)["결과"]["사업소득금액"] == 24_000_000       # 2022 과세기간은 다목 2,400만 → 기준경비율 3천만 − 3천만×20%
    r = _est(2025, False)
    assert r["결과"]["사업소득금액"] == 24_000_000 and any("personal_service" in j["결론"] for j in r["판단"])
    assert "error" in S.estimated_business_income(year=2025, industry_group="나", prior_year_revenue=1, revenues=[], expenses=[],
                                                  base_rate=0.2, simple_rate=0.6, personal_service=True)


# ── 우선순위 1: 보육·식사대·연장근로 — 부칙 '지급받는 분부터' ───────────────────────
def _egp(year, items):
    return ok(S.earned_income_gross_pay(year, items))


def test_childcare_2025_paid_in_2026_per_child():
    f = {"purpose": "보육", "months": 1, "child_ages": [3, 5]}
    r = _egp(2025, [{"kind": "출산·보육수당", "amount": 400_000, "facts": {**f, "paid_date": "2026-01-10"}}])
    assert r["결과"]["비과세_합계"] == 400_000 and any("국세청 해석" in n for n in r["주의"])   # 자녀 1명당 20만 × 2
    r = _egp(2025, [{"kind": "출산·보육수당", "amount": 400_000, "facts": {**f, "paid_date": "2025-12-26"}}])
    assert r["결과"]["비과세_합계"] == 200_000 and "주의" not in r
    r = _egp(2025, [{"kind": "출산·보육수당", "amount": 400_000, "facts": f}])                    # 날짜 없음 — 경계 연도 안내
    assert r["결과"]["비과세_합계"] == 200_000 and any("paid_date" in n for n in r["주의"])


def test_childcare_2023_paid_in_2024():
    f = {"purpose": "보육", "months": 1, "child_age": 3}
    assert _egp(2023, [{"kind": "출산·보육수당", "amount": 200_000, "facts": {**f, "paid_date": "2024-01-10"}}])["결과"]["비과세_합계"] == 200_000
    assert _egp(2023, [{"kind": "출산·보육수당", "amount": 200_000, "facts": f}])["결과"]["비과세_합계"] == 100_000


def test_meal_split_by_paid_date():
    f = {"meal_provided": False}
    a = {"kind": "식사대", "amount": 2_200_000, "facts": {**f, "months": 11, "paid_date": "2022-11-25"}}
    r = _egp(2022, [a, {"kind": "식사대", "amount": 200_000, "facts": {**f, "months": 1, "paid_date": "2023-01-10"}}])
    assert r["결과"]["비과세_합계"] == 1_100_000 + 200_000
    r = _egp(2022, [a, {"kind": "식사대", "amount": 200_000, "facts": {**f, "months": 1, "paid_date": "2022-12-30"}}])
    assert r["결과"]["비과세_합계"] == 1_100_000 + 100_000
    r = _egp(2022, [{"kind": "식사대", "amount": 2_400_000, "facts": {**f, "months": 12}}])
    assert r["결과"]["비과세_합계"] == 1_200_000 and any("paid_date" in n for n in r["주의"])
    assert "주의" not in _egp(2024, [{"kind": "식사대", "amount": 2_400_000, "facts": {**f, "months": 12}}])
    # 같은 종류 두 항목은 지급일이 없으면 여전히 거절
    assert "error" in S.earned_income_gross_pay(2022, [{"kind": "식사대", "amount": 1, "facts": {**f, "months": 1}}] * 2)


def test_overtime_2025_paid_in_2026():
    f = {"eligible_occupation": True, "prior_year_gross": 35_000_000, "monthly_regular_wage": 2_500_000}
    r = _egp(2025, [{"kind": "연장근로수당", "amount": 1_000_000, "facts": {**f, "paid_date": "2026-01-10"}}])
    assert r["결과"]["비과세_합계"] == 1_000_000                       # 2026 기준 월정액 260만·직전 3,700만 충족
    r = _egp(2025, [{"kind": "연장근로수당", "amount": 1_000_000, "facts": f}])
    assert r["결과"]["비과세_합계"] == 0 and any("paid_date" in n for n in r["주의"])   # 2025 기준 210만·3,000만 초과
    r = _egp(2019, [{"kind": "연장근로수당", "amount": 1_000_000, "facts": {**f, "prior_year_gross": 28_000_000, "monthly_regular_wage": 2_000_000, "paid_date": "2020-01-10"}}])
    assert r["결과"]["비과세_합계"] == 0                                # 2020 기준은 과세기간 기준 — 2019 귀속은 2,500만 그대로


# ── 우선순위 2: 주택자금대여이익 특수관계자 제외는 2024.2.29. 이후 발생분(영 제34265호 부칙 제4조①) ──
def test_housing_loan_benefit_accrual_split():
    f = {"sme": True, "related_party": True}
    r = _egp(2024, [{"kind": "주택자금대여이익", "amount": 1_200_000, "facts": {**f, "accrued_before_20240229": 200_000}}])
    assert (r["결과"]["비과세_합계"], r["결과"]["총급여액"]) == (200_000, 1_000_000)
    r = _egp(2024, [{"kind": "주택자금대여이익", "amount": 1_200_000, "facts": f}])
    assert r["결과"]["비과세_합계"] == 0 and any("accrued_before_20240229" in n for n in r["주의"])
    r = _egp(2025, [{"kind": "주택자금대여이익", "amount": 1_200_000, "facts": {**f, "accrued_before_20240229": 200_000}}])
    assert r["결과"]["비과세_합계"] == 0


# ── 우선순위 2: 비실명 원천징수세율은 지급분 기준 ─────────────────────────────────
def _unnamed_reason(year, **k):
    r = ok(S.financial_income_aggregate(year, [{"kind": "비실명배당", "amount": M, **k}]))
    return r, next(j["이유"] for j in r["판단"] if j["항목"] == "비실명배당")


def test_unnamed_rate_by_paid_date():
    r, why = _unnamed_reason(2022, paid_date="2023-01-10")
    assert "45%" in why and "4,500,000원" in why
    r, why = _unnamed_reason(2022, paid_date="2022-12-30")
    assert "42%" in why
    r, why = _unnamed_reason(2022)
    assert "42%" in why and any("paid_date" in n for n in r["주의"])


# ── 우선순위 2: 일용 근로소득공제 15만원은 2019.1.1. 이후 발생(근로 제공)분 ──────────────
def test_daily_worker_work_date():
    assert S.daily_worker_withholding(200_000, 2019, work_date="2018-12-28")["결과"]["원천징수세액"] == 2_700   # (20만−10만)×6%×45%
    assert S.daily_worker_withholding(200_000, 2019, work_date="2019-01-02")["결과"]["원천징수세액"] == 1_350
    r = S.daily_worker_withholding(200_000, 2019)
    assert r["결과"]["원천징수세액"] == 1_350 and "work_date" in r["주의"]
    assert "10만원" in S.daily_worker_withholding(200_000, 2018)["산식"]                # 산식 문구도 연도별


# ── 우선순위 2: 소액부징수(제86조제1호) ───────────────────────────────────────────
def _wh(kind, amount, year, **k):
    return S.withholding_tax(kind, amount, year, **k)["결과"]["원천징수세액"]


def test_small_amount_not_collected():
    assert _wh("기타", 4_000, 2025) == 0                 # 800원 → 부징수
    assert _wh("이자", 5_000, 2025) == 700               # 이자소득은 제외
    assert _wh("사업", 20_000, 2025) == 0                # 600원, 인적용역 계속·반복 아님
    assert _wh("사업", 20_000, 2025, continuous_personal_service=True) == 600
    assert _wh("사업", 20_000, 2024, continuous_personal_service=True, paid_date="2024-06-30") == 0
    assert _wh("사업", 20_000, 2024, continuous_personal_service=True, paid_date="2024-07-01") == 600
    assert _wh("사업", 20_000, 2023, continuous_personal_service=True) == 0
    assert _wh("기타", 5_000, 2025) == 1_000             # 1천원 이상은 그대로


# ── 우선순위 3: 표시 문구 ─────────────────────────────────────────────────────
def test_display_fixes():
    # 장특공 근거 조문 경계 — 시행령 제31442호 2021.2.17. 공포·시행
    data = vocab.load()
    it = next(x for x in data["항목"] if x["이름"] == "양도소득_장기보유특별공제")
    new = next(a for a in it["적용"] if a["부터"] == "20210217")
    assert any(b[1] == "제159조의4" for b in new["근거"]) and not any(a["부터"] == "20210219" for a in it["적용"])
    # 비거주자 국외 인적용역 3% 단서 안내 — 용역 제공일 기준
    r = S.nonresident_withholding("인적용역", 1_000_000, "개인", "US", service_location="국외", year=2017)
    assert "용역 제공일" in str(r)
    # 의제배당 재원 분류는 호출 연도로 조회(오늘 연도 고정 아님)
    assert S._bonus_share_sources(2016) == S._bonus_share_sources(2026)


# ── 사전검토 I-PR05·07·09 ─────────────────────────────────────────────────────
R = {r.id: r for r in REGISTRY}


def _pre(rid, data):
    try:
        return R[rid].fn(Data(data))
    except Missing as e:
        return {"결과": "자료 부족", "내용": str(e)}


def W(**k): return {"성명": "갑", "주민번호": "x", "근무월수": 12, **k}


def test_precheck_meal_next_year_month():
    w = W(**{"비과세.식대": 1_300_000})
    r = _pre("I-PR05", {"귀속연도": 2022, "근로자": [w]})
    assert r["결과"] == "오류 의심" and "다음해지급월수" in r["내용"]
    assert _pre("I-PR05", {"귀속연도": 2022, "근로자": [{**w, "다음해지급월수": 1}]})["결과"] == "이상 없음"   # 11×10만 + 1×20만


def test_precheck_childcare_next_year_month():
    kids = [{"주민번호": "k1", "관계": "직계비속", "생년월일": "2021-05-01"},
            {"주민번호": "k2", "관계": "직계비속", "생년월일": "2023-05-01"}]
    w = W(**{"비과세.보육수당": 2_600_000}, 부양가족=kids)
    assert _pre("I-PR07", {"귀속연도": 2025, "근로자": [w]})["결과"] == "오류 의심"                   # 12×20만
    assert _pre("I-PR07", {"귀속연도": 2025, "근로자": [{**w, "다음해지급월수": 1}]})["결과"] == "이상 없음"   # 11×20만 + 1×20만×2명


def test_precheck_overtime_next_year():
    w = W(**{"비과세.야간근로": 1_000_000}, 직전연도총급여=35_000_000)
    r = _pre("I-PR09", {"귀속연도": 2025, "근로자": [w]})
    assert r["결과"] == "오류 의심" and "야간근로_다음해지급" in r["내용"]
    assert _pre("I-PR09", {"귀속연도": 2025, "근로자": [{**w, "야간근로_다음해지급": True}]})["결과"] == "이상 없음"
    w19 = W(**{"비과세.야간근로": 1_000_000}, 직전연도총급여=28_000_000, 야간근로_다음해지급=True)
    assert _pre("I-PR09", {"귀속연도": 2019, "근로자": [w19]})["결과"] == "오류 의심"            # 2020 기준은 과세기간 기준
