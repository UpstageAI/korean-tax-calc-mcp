"""겸영사업자 공통매입세액 끝에서 끝까지 계산기 정답 테스트 (Claude 작성 2026-10-13) — 수정 금지.
공개 검증 사례(세무사 1차 2023-77·2024-76·2025-71·2026-77, 출처 Q-Net)는 부가가치세법 제29조⑧⑨·제40조·제41조,
영 제63조·제64조·제81조~제83조로 손계산해 공식 정답과 일치 확인. 실무형 사례는 Claude 손계산.
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp
from tests._legacy_to_ledger import to_ledger   # 0.9.0: 옛 입력은 테스트에서 원장형으로 변환해 호출


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, to_ledger(n, a))).content[0].text)


# ── common_input_tax: 안분·정산·공통사용재화 공급 ──
def test_public_case_2024_76():  # 확정신고 정산: 과세기간 전체 면세비율 70%, 예정 불공제 600,000 반영
    r = c("common_input_tax", {"year": 2024, "period": "1기", "filing": "확정",
                               "supplies": {"예정": {"taxable": 400_000_000, "exempt": 600_000_000}, "확정": {"taxable": 200_000_000, "exempt": 800_000_000}},
                               "input_tax": {"taxable_only": 700_000, "exempt_only": 800_000,
                                             "attributed": [{"input_tax": 100_000, "taxable_ratio": 0.7}],
                                             "common": {"예정": 1_000_000, "확정": 1_200_000}},
                               "prior_nondeductible": 600_000})
    k = r["계산"]
    assert k["면세비율_과세기간"] == 0.7 and k["불공제_과세기간합계"] == 1_540_000 and k["불공제_확정"] == 940_000
    assert k["공통매입세액_공제"] == 260_000
    assert r["결과"]["공제매입세액"] == 1_030_000


def test_public_case_2023_77_new_business():  # 신규 사업: 공통사용재화 공급은 전액 과세표준(영 제63조③3호), 그 매입세액 전액 공제(영 제81조②3호)
    r = c("common_input_tax", {"year": 2023, "period": "2기", "filing": "확정", "new_business": True,
                               "supplies": {"예정": None, "확정": {"taxable": 200_000_000, "exempt": 100_000_000}},
                               "input_tax": {"taxable_only": 6_000_000, "taxable_only_nondeductible": 500_000, "exempt_only": 4_000_000,
                                             "common": {"예정": 0, "확정": 4_500_000}},
                               "common_asset_sales": [{"sale_price": 12_000_000, "input_tax": 3_000_000}]})
    k = r["계산"]
    assert k["공통사용재화_공급_과세표준"] == 12_000_000 and k["공통사용재화_매입세액_공제"] == 3_000_000
    assert k["공통매입세액_공제"] == 3_000_000
    assert r["결과"]["공제매입세액"] == 11_500_000 and r["결과"]["추가_매출세액"] == 1_200_000


def test_public_case_2026_77_settlement():  # 예정 불공제를 주지 않으면 예정 비율(70/160)로 계산해 정산
    r = c("common_input_tax", {"year": 2026, "period": "1기", "filing": "확정",
                               "supplies": {"예정": {"taxable": 90_000_000, "exempt": 70_000_000}, "확정": {"taxable": 100_000_000, "exempt": 120_000_000}},
                               "input_tax": {"taxable_only": 5_000_000, "exempt_only": 4_000_000, "common": {"예정": 3_000_000, "확정": 4_000_000}}})
    k = r["계산"]
    assert k["불공제_예정반영"] == 1_312_500 and k["면세비율_과세기간"] == 0.5 and k["공통매입세액_공제"] == 1_812_500
    assert r["결과"]["공제매입세액"] == 6_812_500


def test_prelim_filing_uses_prelim_ratio():
    r = c("common_input_tax", {"year": 2024, "period": "1기", "filing": "예정",
                               "supplies": {"예정": {"taxable": 400_000_000, "exempt": 600_000_000}, "확정": None},
                               "input_tax": {"common": {"예정": 1_000_000, "확정": 0}}})
    assert r["계산"]["공통매입세액_공제"] == 400_000 and r["결과"]["공제매입세액"] == 400_000


def test_small_exempt_ratio_full_credit():  # 면세비율 5% 미만: 공통매입세액 5백만 미만이면 전액 공제, 이상이면 안분(영 제81조②1호)
    base = {"year": 2025, "period": "1기", "filing": "확정", "supplies": {"예정": None, "확정": {"taxable": 96_000_000, "exempt": 4_000_000}}}
    r = c("common_input_tax", {**base, "input_tax": {"common": {"예정": 0, "확정": 3_000_000}}})
    assert r["계산"]["공통매입세액_공제"] == 3_000_000
    r = c("common_input_tax", {**base, "input_tax": {"common": {"예정": 0, "확정": 6_000_000}}})
    assert r["계산"]["공통매입세액_공제"] == 5_760_000


def test_asset_sale_prior_ratio_and_small_sale():  # 직전 과세기간 과세비율 60% → 과세표준 60%; 50만 원 미만은 전액
    r = c("common_input_tax", {"year": 2025, "period": "2기", "filing": "확정",
                               "supplies": {"예정": None, "확정": {"taxable": 50_000_000, "exempt": 50_000_000}},
                               "input_tax": {"common": {"예정": 0, "확정": 0}},
                               "prior_period_supplies": {"taxable": 60_000_000, "exempt": 40_000_000},
                               "common_asset_sales": [{"sale_price": 10_000_000, "input_tax": 0}, {"sale_price": 400_000, "input_tax": 0}]})
    assert r["계산"]["공통사용재화_공급_과세표준"] == 6_400_000


def test_common_input_validation():
    r = c("common_input_tax", {"year": 2025, "period": "3기", "filing": "확정", "supplies": {"예정": None, "확정": {"taxable": 1, "exempt": 1}}, "input_tax": {}})
    assert "error" in r
    r = c("common_input_tax", {"year": 2025, "period": "1기", "filing": "확정", "supplies": {"예정": None, "확정": None}, "input_tax": {"common": {"예정": 0, "확정": 100}}})
    assert "error" in r                                             # 공급가액 없이는 안분 불가


# ── input_tax_recalculation: 감가상각자산 재계산 ──
RATIOS_2025_71 = [{"year": 2022, "period": "2기", "exempt_ratio": 0.50}, {"year": 2023, "period": "1기", "exempt_ratio": 0.54},
                  {"year": 2023, "period": "2기", "exempt_ratio": 0.45}, {"year": 2024, "period": "1기", "exempt_ratio": 0.49},
                  {"year": 2024, "period": "2기", "exempt_ratio": 0.44}, {"year": 2025, "period": "1기", "exempt_ratio": 0.51}]


def test_public_case_2025_71_building():  # 2023-2기 재계산(45%)이 기준이 되어 2025-1기 +6%p, 경과 5기 → 45,756,000 × 0.75 × 6%
    r = c("input_tax_recalculation", {"asset_type": "건물·구축물", "input_tax": 45_756_000, "acquired": {"year": 2022, "period": "2기"}, "ratios": RATIOS_2025_71})
    hist = {(h["year"], h["period"]): h for h in r["이력"]}
    assert hist[(2023, "2기")]["재계산"] is True and hist[(2023, "2기")]["세액"] == -2_059_020
    assert hist[(2024, "1기")]["재계산"] is False and hist[(2024, "2기")]["재계산"] is False
    assert hist[(2025, "1기")]["경과과세기간수"] == 5 and hist[(2025, "1기")]["세액"] == 2_059_020
    assert r["결과"]["당기_납부세액_가산"] == 2_059_020


def test_public_case_2026_77_machine():  # 기타 감가상각자산 25%, 1기 경과, 40% → 50%
    r = c("input_tax_recalculation", {"asset_type": "기타감가상각자산", "input_tax": 5_000_000, "acquired": {"year": 2025, "period": "2기"},
                                      "ratios": [{"year": 2025, "period": "2기", "exempt_ratio": 0.40}, {"year": 2026, "period": "1기", "exempt_ratio": 0.50}]})
    assert r["결과"]["당기_납부세액_가산"] == 375_000


def test_recalculation_below_threshold_and_fully_depreciated():
    r = c("input_tax_recalculation", {"asset_type": "기타감가상각자산", "input_tax": 5_000_000, "acquired": {"year": 2025, "period": "2기"},
                                      "ratios": [{"year": 2025, "period": "2기", "exempt_ratio": 0.40}, {"year": 2026, "period": "1기", "exempt_ratio": 0.44}]})
    assert r["결과"]["당기_납부세액_가산"] == 0 and r["이력"][-1]["재계산"] is False
    r = c("input_tax_recalculation", {"asset_type": "기타감가상각자산", "input_tax": 5_000_000, "acquired": {"year": 2023, "period": "1기"},
                                      "ratios": [{"year": 2023, "period": "1기", "exempt_ratio": 0.10}, {"year": 2023, "period": "2기", "exempt_ratio": 0.10},
                                                 {"year": 2024, "period": "1기", "exempt_ratio": 0.10}, {"year": 2024, "period": "2기", "exempt_ratio": 0.10},
                                                 {"year": 2025, "period": "1기", "exempt_ratio": 0.60}]})
    assert r["결과"]["당기_납부세액_가산"] == 0                        # 4기 경과 → (1 − 25% × 4) = 0


# ── bundled_supply_split: 토지·건물 일괄공급 안분 ──
def test_public_case_2025_71_split():  # 762,600,000(부가세 포함) ÷ 감정가 432:244.8 → 건물 457,560,000, 부가세 45,756,000
    r = c("bundled_supply_split", {"total_price": 762_600_000, "vat_included": True, "appraisal": {"building": 432_000_000, "land": 244_800_000}})
    assert r["결과"]["건물_공급가액"] == 457_560_000 and r["결과"]["부가가치세"] == 45_756_000 and r["결과"]["토지_가액"] == 259_284_000


def test_split_without_vat_and_basis_priority():
    r = c("bundled_supply_split", {"total_price": 1_000_000_000, "vat_included": False, "standard_value": {"building": 300_000_000, "land": 700_000_000}})
    assert r["결과"]["건물_공급가액"] == 300_000_000 and r["결과"]["부가가치세"] == 30_000_000 and r["결과"]["토지_가액"] == 700_000_000
    r = c("bundled_supply_split", {"total_price": 1_000_000_000, "vat_included": False,
                                   "appraisal": {"building": 500_000_000, "land": 500_000_000}, "standard_value": {"building": 300_000_000, "land": 700_000_000}})
    assert r["결과"]["건물_공급가액"] == 500_000_000 and "감정평가" in json.dumps(r["판단"], ensure_ascii=False)
