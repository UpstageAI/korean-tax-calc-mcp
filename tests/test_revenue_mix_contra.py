"""매출 표의 차감 행(매출할인·에누리·환입) 처리와 비중 범위 검사. 실제 사례: 비상장 화장품 도매사 감사보고서(2024) —
상품매출 261,006,553,234 / 매출할인 -43,547,188,253 / 임대료수입 39,600,000 / 기타매출 10,543,199,547, 합계 = 손익계산서 매출 228,042,164,528.
종전: 상품 비중 114%(차감 행을 '기타'로 따로 둠). Claude 작성(2026-11-17)."""
import pytest

from korean_tax_calc_mcp.engine.kr_comparables import revenue_mix as RM

ROWS = [("상품매출", 261006553234), ("매출할인", -43547188253), ("임대료수입", 39600000), ("기타매출", 10543199547)]
CLS = {0: ("merchandise", "원문 계정명"), 1: ("other", "모델"), 2: ("service", "모델"), 3: ("other", "모델")}


def test_untargeted_discount_is_netted_proportionally():
    al = RM.allocate(ROWS, CLS, {"merch_ratio": 1.0})
    pos = 261006553234 + 39600000 + 10543199547
    k = 1 - 43547188253 / pos
    tot = 228042164528
    assert al["total"] == tot and al["conflict"] is None
    assert al["shares"]["merchandise"] == pytest.approx(261006553234 * k / tot, rel=1e-12)   # 약 96.1%
    assert al["shares"]["other"] == pytest.approx(10543199547 * k / tot, rel=1e-12)
    assert sum(al["shares"].values()) == pytest.approx(1.0, abs=1e-12)
    assert al["contra_rows"] == {1: "차감 행 — 양수 매출 갈래에 금액 비율로 나눠 뺌"}


def test_targeted_discount_comes_off_its_own_line():
    rows = [("상품매출", 100), ("상품 매출할인", -10), ("용역매출", 50)]
    al = RM.allocate(rows, {0: ("merchandise", ""), 1: ("other", ""), 2: ("service", "")}, {})
    assert al["shares"]["merchandise"] == pytest.approx(90 / 140) and al["shares"]["service"] == pytest.approx(50 / 140)
    assert "merchandise에서 뺌" in al["contra_rows"][1]


def test_goods_bucket_takes_its_share_of_discount():
    rows = [("화장품", 200), ("매출에누리", -20), ("서비스", 20)]
    al = RM.allocate(rows, {0: (RM.GOODS, "모델"), 1: ("other", ""), 2: ("service", "")}, {"merch_ratio": 0.5, "source": "재고"})
    k = 200 / 220                     # 양수 매출 220 중 차감 20을 금액 비율로 — 남는 비율 200/220
    assert al["shares"]["merchandise"] == pytest.approx(200 * k * 0.5 / 200) and al["shares"]["product"] == pytest.approx(200 * k * 0.5 / 200)
    assert al["shares"]["service"] == pytest.approx(20 * k / 200)


def test_out_of_range_share_becomes_conflict():
    """차감이 다른 행에 걸려 있어도 비중이 0~100%를 벗어나면 숫자를 내지 않음."""
    rows = [("상품매출", 100), ("용역매출", 50), ("기타", -60)]
    cls = {0: ("merchandise", ""), 1: ("service", ""), 2: ("other", "")}
    al = RM.allocate(rows, cls, {})
    assert al["conflict"] is None and sum(al["shares"].values()) == pytest.approx(1.0)
    # 이름으로 대상이 정해진 차감이 그 매출보다 크면 그 갈래가 음수 → 숫자를 내지 않음
    al = RM.allocate([("상품매출", 100), ("상품매출할인", -150), ("용역매출", 200)], {0: ("merchandise", ""), 1: ("other", ""), 2: ("service", "")}, {})
    assert al["conflict"] and "범위 밖" in al["conflict"] and "merchandise" in al["conflict"]


def test_no_negative_rows_unchanged():
    rows = [("상품매출", 80), ("용역매출", 20)]
    al = RM.allocate(rows, {0: ("merchandise", ""), 1: ("service", "")}, {})
    assert al["shares"]["merchandise"] == 0.8 and al["contra_rows"] == {}
