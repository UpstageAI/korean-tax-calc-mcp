"""0.38.0 reduction_income_segments 정답 테스트(2026-11-12, Claude 손계산).
근거: 조세특례제한법 제143조①③·시행령 제136조·제2조③, 법인세법 제59조②·시행령 제96조·시행규칙 제75조②·제76조⑥⑦(2016·2025 시행본)."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(**k):
    return getattr(S.reduction_income_segments, "fn", S.reduction_income_segments)(**k)


def seg(name, eligible, revenue, direct_expenses, **k):
    return {"name": name, "eligible": eligible, "revenue": revenue * M, "direct_expenses": direct_expenses * M, **{a: b * M for a, b in k.items()}}


ABC = [seg("A", True, 100, 60), seg("B", False, 100, 40), seg("C", False, 50, 80)]


def rows(r):
    return {x["사업"]: x for x in r["계산"]["사업별"]}


def test_common_expenses_by_direct_expenses_when_industries_differ():
    # 공통손금 30억을 개별손금 80억:160억으로 → 10억·20억. 온라인 120−80−10 = 30억, 도매 180−160−20 = 0
    r = f(segments=[seg("온라인 직접 판매", True, 12_000, 8_000), seg("도매", False, 18_000, 16_000)], common_expenses=3_000 * M)
    y = rows(r)
    assert y["온라인 직접 판매"]["공통손금_배분"] == 1_000 * M and y["도매"]["공통손금_배분"] == 2_000 * M
    assert y["온라인 직접 판매"]["소득금액"] == 3_000 * M and y["도매"]["소득금액"] == 0
    assert r["결과"] == {"감면_대상_소득": 3_000 * M, "과세표준": 3_000 * M, "감면_소득_비율": 1.0, "각사업연도소득": 3_000 * M, "주된_사업": "도매"}
    assert r["계산"]["공통손금_기준"] == "개별손금" and any("제143조" in s for s in r["근거"])


def test_common_expenses_by_revenue_when_same_industry_and_common_income():
    # 공통손금 30을 수입금액 100:100:50 → 12·12·6, 공통익금 25 → 10·10·5
    r = f(segments=ABC, common_income=25 * M, common_expenses=30 * M, same_industry=True)
    y = rows(r)
    assert [y[n]["공통손금_배분"] for n in "ABC"] == [12 * M, 12 * M, 6 * M] and [y[n]["공통익금_배분"] for n in "ABC"] == [10 * M, 10 * M, 5 * M]
    assert [y[n]["소득금액"] for n in "ABC"] == [38 * M, 58 * M, -31 * M] and r["계산"]["공통손금_기준"] == "수입금액"


def test_loss_business_offset_in_proportion_to_income():
    # A 40, B 60, C −30 → 결손금 30을 40:60으로 12·18 → A 28, B 42. 감면 대상 28 / 과세표준 70 = 0.4
    r = f(segments=ABC)
    y = rows(r)
    assert y["A"]["결손금_안분_공제"] == 12 * M and y["B"]["결손금_안분_공제"] == 18 * M and y["C"]["공제_후_소득금액"] == 0
    assert r["결과"]["감면_대상_소득"] == 28 * M and r["결과"]["과세표준"] == 70 * M and r["결과"]["감면_소득_비율"] == 0.4
    assert r["결과"]["주된_사업"] is None and any("같은 사업이 여럿" in p for p in r["판단"])   # A·B 수입금액이 같음


def test_deducted_loss_carryforward_attribution():
    # 불분명 35 → 35 × 28/70 = 14, 감면 사업 발생 10은 전액 → 28 − 10 − 14 = 4, 과세표준 70 − 45 = 25
    r = f(segments=ABC, deductions={"eligible": 10 * M, "unclear": 35 * M})
    assert r["계산"]["불분명_공제액_안분"] == 14 * M and r["결과"]["감면_대상_소득"] == 4 * M and r["결과"]["과세표준"] == 25 * M
    # 그 밖의 사업에서 발생한 공제액은 감면 대상 소득에서 빼지 않음 → 28, 과세표준 70 − 20 = 50
    r = f(segments=ABC, deductions={"other": 20 * M})
    assert r["결과"]["감면_대상_소득"] == 28 * M and r["결과"]["과세표준"] == 50 * M


def test_ratio_capped_at_taxable_base():
    # A 40(감면), B 60, 그 밖의 사업 공제 70 → 과세표준 30 < 감면 대상 40 → 30, 비율 100%
    r = f(segments=[seg("A", True, 100, 60), seg("B", False, 100, 40)], deductions={"other": 70 * M})
    assert r["계산"]["한도_전_감면_대상_소득"] == 40 * M and r["결과"]["감면_대상_소득"] == 30 * M and r["결과"]["감면_소득_비율"] == 1.0
    assert any("100%" in p for p in r["판단"]) and r["결과"]["주된_사업"] is None


def test_feeds_startup_reduction():
    # 2024 과세표준 30억 가운데 감면 대상 12억 → 산출세액 5.5억 × 12/30 × 50% = 1.1억
    r = f(segments=[seg("온라인 직접 판매", True, 12_000, 9_800), seg("도매", False, 18_000, 15_200)], common_expenses=2_000 * M)
    # 공통손금 20억을 98억:152억 → 7.84억·12.16억. 온라인 120 − 98 − 7.84 = 14.16억, 도매 180 − 152 − 12.16 = 15.84억
    assert r["결과"]["감면_대상_소득"] == 1_416 * M and r["결과"]["과세표준"] == 3_000 * M and r["결과"]["주된_사업"] == "도매"
    s = getattr(S.startup_tax_reduction, "fn", S.startup_tax_reduction)(founded_on="2021-03-02", region="수도권과밀억제권역", year=2024, first_income_year=2023, tax=550 * M,
                                                                       taxable_base=r["결과"]["과세표준"], eligible_income=r["결과"]["감면_대상_소득"], youth=True, industry="통신판매업")
    assert s["결과"]["감면세액"] == 129_800_000   # 5.5억 × 14.16/30 × 50%


def test_input_errors():
    assert "error" in f(segments=[seg("A", True, 100, 60)])
    assert "error" in f(segments=[seg("A", True, 100, 0), seg("B", False, 100, 0)], common_expenses=10 * M)       # 개별손금이 없어 나눌 수 없음
    assert "error" in f(segments=ABC, deductions={"감면": 1})
    assert "error" in f(segments=[seg("A", True, 100, 60), {"name": "A", "eligible": False, "revenue": 1, "direct_expenses": 0}])
    assert "error" not in f(segments=[seg("A", True, 100, 0), seg("B", False, 100, 0)], common_expenses=10 * M, same_industry=True)
