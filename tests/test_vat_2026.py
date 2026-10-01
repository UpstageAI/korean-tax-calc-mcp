"""2026년 1기 부가가치세 신고안내 예시 재현(플레이북 13 §12-2). 쪽 = 책 인쇄 쪽(PDF = 책 + 6)."""

from korean_tax_calc_mcp.engine import calc_vat as V, calc


def test_T1_T3_fake_invoice_20_37():
    assert calc.penalty_fake_invoice(10_000_000, "2026-03-01") == 400_000 and calc.penalty_fake_invoice(10_000_000, "2025-12-01") == 300_000


def test_T4_T7_invoice_119():
    assert [V.invoice_penalties(10_000_000, k) for k in ("지연전송", "미전송")] == [30_000, 50_000]
    assert [V.invoice_penalties(20_000_000, k) for k in ("지연발급", "지연수취", "미발급")] == [200_000, 100_000, 400_000]


def test_T8_T12():
    assert V.deemed_rent(365_000_000, 181) == 5_611_000
    assert V.bad_debt_vat(11_000_000) == 1_000_000
    assert V.deemed_input(21_800_000, 100_000_000, 9, 109, 0.75) == 1_800_000
    assert V.deemed_input(80_000_000, 106_000_000, 6, 106, 0.50) == 3_000_000
    assert V.recycled_scrap(50_000_000, 29_700_000, 20_600_000) == {"한도": 10_300_000, "공제": 300_000}


def test_T19_T21_T26():
    assert V.simplified_tax(55_000_000, 0.15, 22_000_000) == 715_000
    assert V.late_payment(1_000_000, 30) == 6_600
    assert V.cash_sales_statement(10_000_000) == 100_000


def test_value_added_rate_statute():
    """부가령 제111조② 표"""
    assert (V.value_added_rate("음식점업"), V.value_added_rate("제조업"), V.value_added_rate("숙박업"),
            V.value_added_rate("정보통신업"), V.value_added_rate("부동산임대업"), V.value_added_rate("그 밖의 서비스업"),
            V.value_added_rate("인물사진 및 행사용 영상 촬영업")) == (0.15, 0.20, 0.25, 0.30, 0.40, 0.30, 0.30)
    assert abs(V.mixed_value_added_rate([("소매업", 60), ("제조업", 40)]) - 0.17) < 1e-12


def test_common_input_allocation_81():
    """부가령 제81조 — 조문 산식으로 직접 계산한 값"""
    assert V.common_input_allocation(10_000_000, 1_000_000_000, 300_000_000)["불공제"] == 3_000_000
    assert V.common_input_allocation(4_000_000, 1_000_000_000, 40_000_000)["불공제"] == 0           # ②1호: 4% · 500만 미만
    assert V.common_input_allocation(6_000_000, 1_000_000_000, 40_000_000)["불공제"] == 240_000     # ②1호 단서: 500만 이상이면 안분
    assert V.common_input_allocation(40_000, 1_000_000_000, 500_000_000)["불공제"] == 0              # ②2호: 5만원 미만
    r = V.common_input_allocation(10_000_000, 0, 0, ("예정사용면적", 300, 1000))                     # ④3호
    assert r["불공제"] == 3_000_000 and "제82조" in r["근거"]


def test_common_input_settlement_82():
    assert V.common_input_settlement(10_000_000, 0.4, 3_000_000)["가산또는공제"] == 1_000_000
    assert V.common_input_settlement(10_000_000, 0.2, 3_000_000)["가산또는공제"] == -1_000_000


def test_common_input_recalc_83():
    # 건물 매입세액 1억, 2024년 1기 취득(면세비율 30%), 2026년 1기 면세비율 40% → 경과 4기, 경감률 80%, +10%p
    r = V.common_input_recalc(100_000_000, "건물", "2024-03-10", "2026-06-30", 0.30, 0.40)
    assert (r["경과과세기간"], r["경감률"], r["재계산"]) == (4, 0.8, 8_000_000)
    # 기계(그 밖의 감가상각자산) 2025년 2기 취득 → 1기 경과 75%, 비율 50%→35% → 환급(−)
    r = V.common_input_recalc(20_000_000, "기타", "2025-08-01", "2026-06-30", 0.50, 0.35)
    assert (r["경과과세기간"], r["재계산"]) == (1, -2_250_000)
    assert V.common_input_recalc(20_000_000, "기타", "2025-08-01", "2026-06-30", 0.50, 0.46)["재계산"] == 0   # 5% 미만
    assert V.common_input_recalc(20_000_000, "기타", "2020-01-01", "2026-06-30", 0.10, 0.50)["재계산"] == 0   # 4기 상한 → 경감률 0


