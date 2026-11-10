"""외화 대가 부가가치세 과세표준 환산 vat_foreign_currency_base — 정답 테스트(수정 금지, Claude 작성 2026-11-10).
근거: 부가가치세법 제29조제3항제1호 단서, 시행령 제59조 1호(공급시기 전 환가 → 환가액)·2호(공급시기 이후 → 공급시기 기준환율),
대리납부는 시행령 제95조제3항 1호(원화로 매입 → 지급일 대고객외국환매도율)·2호(보유 외화 → 지급일 기준환율). 원 미만 절사.
공개 검증 사례: 2026-11-10 트렌드 시나리오 S1(가상 (주)가나무역)·S4(가상 의료법인) 손계산.
"""
from _helpers import call as c

M = 1_000_000


def test_s1_partial_prepayment_converted_before_shipping():
    r = c("vat_foreign_currency_base", {"context": "공급", "items": [
        {"이름": "수출", "외화금액": 100_000, "통화": "USD", "공급시기": "2026-05-15", "공급시기_환율": 1380,
         "환가": [{"환가일": "2026-04-20", "외화금액": 30_000, "원화금액": 40_500_000}]}]})
    assert "error" not in r, r
    g = r["결과"]
    assert g["과세표준_합계"] == 137_100_000
    it = g["항목별"][0]
    assert it["환가분"] == {"외화": 30_000, "원화": 40_500_000}
    assert it["미환가분"] == {"외화": 70_000, "환율": 1380, "원화": 96_600_000}
    assert it["과세표준"] == 137_100_000 and it["적용"] == "시행령 제59조 1호·2호"
    assert "제59조" in r["근거"]


def test_fully_converted_before_supply_needs_no_rate():
    r = c("vat_foreign_currency_base", {"items": [
        {"외화금액": 10_000, "공급시기": "2026-05-15", "환가": [{"환가일": "2026-04-20", "외화금액": 10_000, "원화금액": 13_500_000}]}]})
    assert "error" not in r, r
    assert r["결과"]["과세표준_합계"] == 13_500_000 and r["결과"]["항목별"][0]["적용"] == "시행령 제59조 1호"


def test_conversion_after_supply_time_uses_supply_time_rate():
    r = c("vat_foreign_currency_base", {"items": [
        {"외화금액": 10_000, "공급시기": "2026-05-15", "공급시기_환율": 1380,
         "환가": [{"환가일": "2026-05-20", "외화금액": 10_000, "원화금액": 13_900_000}]}]})
    assert "error" not in r, r
    it = r["결과"]["항목별"][0]
    assert it["과세표준"] == 13_800_000 and it["적용"] == "시행령 제59조 2호"
    assert any("공급시기 이후" in str(j) for j in r["판단"])


def test_truncates_won_and_sums_items():
    r = c("vat_foreign_currency_base", {"items": [
        {"이름": "a", "외화금액": 1234.56, "공급시기": "2026-03-02", "공급시기_환율": 1380.25},
        {"이름": "b", "외화금액": 1000, "통화": "EUR", "공급시기": "2026-03-03", "공급시기_환율": 1500}]})
    assert "error" not in r, r
    assert [x["과세표준"] for x in r["결과"]["항목별"]] == [1_704_001, 1_500_000]
    assert r["결과"]["과세표준_합계"] == 3_204_001


def test_reverse_charge_bought_won_uses_selling_rate():
    r = c("vat_foreign_currency_base", {"context": "대리납부", "items": [
        {"외화금액": 50_000, "지급일": "2026-05-31", "지급방식": "원화매입", "지급일_환율": 1365.5}]})
    assert "error" not in r, r
    it = r["결과"]["항목별"][0]
    assert it["과세표준"] == 68_275_000 and it["적용"] == "시행령 제95조 제3항 1호"
    assert "제95조" in r["근거"]


def test_reverse_charge_held_currency_uses_base_rate():
    r = c("vat_foreign_currency_base", {"context": "대리납부", "items": [
        {"외화금액": 50_000, "지급일": "2026-05-31", "지급방식": "보유외화", "지급일_환율": 1350}]})
    it = r["결과"]["항목별"][0]
    assert it["과세표준"] == 67_500_000 and it["적용"] == "시행령 제95조 제3항 2호"


def test_errors():
    assert "error" in c("vat_foreign_currency_base", {"items": [{"외화금액": 10_000, "공급시기": "2026-05-15"}]})          # 환율 없음
    assert "error" in c("vat_foreign_currency_base", {"items": [{"외화금액": 10_000, "공급시기": "2026-05-15", "공급시기_환율": 1380,
        "환가": [{"환가일": "2026-04-01", "외화금액": 20_000, "원화금액": 1}]}]})                                                # 환가 > 외화
    assert "error" in c("vat_foreign_currency_base", {"items": [{"외화금액": -1, "공급시기": "2026-05-15", "공급시기_환율": 1380}]})
    r = c("vat_foreign_currency_base", {"context": "대리납부", "items": [{"외화금액": 1, "지급일": "2026-05-31", "지급일_환율": 1350}]})
    assert "error" in r and "허용값" in r                                                                                # 지급방식 없음
    assert "error" in c("vat_foreign_currency_base", {"context": "수입", "items": []})


def test_find_tool_surfaces_tool():
    r = c("find_tool", {"query": "외화 수출대금 원화 환산 과세표준 기준환율", "n": 3})
    assert "vat_foreign_currency_base" in [x["도구"] for x in r["결과"]["후보"]], r
