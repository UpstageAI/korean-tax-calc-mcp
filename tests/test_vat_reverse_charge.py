"""국외사업자 용역등 대리납부 vat_reverse_charge — 정답 테스트(수정 금지, Claude 작성 2026-11-10).
근거: 부가가치세법 제52조제1항(과세사업 제공분 제외, 제39조 불공제 용역 포함 — 2025.3.14 개정)·제2항(제48조제2항·제49조제2항 준용),
시행령 제95조제1항·제2항(공통사용 안분: 총공급가액 × 면세공급가액/총공급가액), 국세기본법 제5조제1항(기한이 토·일이면 다음 날).
공개 검증 사례: 2026-11-10 트렌드 시나리오 S4(가상 의료법인, 싱가포르 법인 컨설팅 67,500,000원, 2026-05-31 지급) 손계산.
"""
from _helpers import call as c

M = 1_000_000
Y = {"year": 2026}


def _one(**kw):
    item = {"이름": "컨설팅", "공급자": "국내사업장_없음", "대가": 67_500_000, "지급일": "2026-05-31", "용도": "면세"}
    item.update(kw)
    return item


def test_s4_exempt_business_pays_reverse_charge_by_final_return_deadline():
    r = c("vat_reverse_charge", {**Y, "items": [_one()]})
    assert "error" not in r, r
    g = r["결과"]
    assert g["대리납부세액_합계"] == 6_750_000
    it = g["항목별"][0]
    assert it["대상"] is True and it["과세표준"] == 67_500_000 and it["세액"] == 6_750_000
    assert it["기한_법정"] == "2026-07-25" and it["기한_적용"] == "2026-07-27"      # 7.25 토요일 → 월요일
    assert "제52조" in r["근거"] and "제95조" in r["근거"]


def test_taxable_use_is_excluded():
    r = c("vat_reverse_charge", {**Y, "items": [_one(용도="과세")]})
    it = r["결과"]["항목별"][0]
    assert it["대상"] is False and it["세액"] == 0 and "과세사업" in it["사유"]
    assert r["결과"]["대리납부세액_합계"] == 0


def test_nondeductible_use_is_included():
    r = c("vat_reverse_charge", {**Y, "items": [_one(이름="접대 용역", 대가=10 * M, 용도="불공제")]})
    it = r["결과"]["항목별"][0]
    assert it["대상"] is True and it["세액"] == 1 * M and "제39조" in it["사유"]


def test_common_use_apportioned_by_exempt_ratio():
    r = c("vat_reverse_charge", {**Y, "taxable_supply": 300 * M, "exempt_supply": 100 * M,
                                 "items": [_one(대가=100 * M, 용도="공통")]})
    assert "error" not in r, r
    it = r["결과"]["항목별"][0]
    assert it["과세표준"] == 25 * M and it["세액"] == 2_500_000


def test_common_use_without_supply_amounts_refused():
    assert "error" in c("vat_reverse_charge", {**Y, "items": [_one(용도="공통")]})


def test_domestic_pe_attributed_is_not_reverse_charge():
    r = c("vat_reverse_charge", {**Y, "items": [_one(공급자="국내사업장_있음_귀속")]})
    it = r["결과"]["항목별"][0]
    assert it["대상"] is False and it["세액"] == 0 and "국내사업장" in it["사유"]


def test_deadlines_follow_payment_date_period():
    r = c("vat_reverse_charge", {**Y, "items": [_one(이름="1기 예정", 지급일="2026-02-10"), _one(이름="2기 예정", 지급일="2026-08-03"),
                                                 _one(이름="2기 확정", 지급일="2026-12-01")]})
    its = r["결과"]["항목별"]
    assert (its[0]["기한_법정"], its[0]["기한_적용"]) == ("2026-04-25", "2026-04-27")   # 토 → 월
    assert (its[1]["기한_법정"], its[1]["기한_적용"]) == ("2026-10-25", "2026-10-26")   # 일 → 월
    assert (its[2]["기한_법정"], its[2]["기한_적용"]) == ("2027-01-25", "2027-01-25")   # 월
    assert r["결과"]["대리납부세액_합계"] == 3 * 6_750_000


def test_bad_enums_and_negative_refused():
    r = c("vat_reverse_charge", {**Y, "items": [_one(용도="기타")]})
    assert "error" in r and "허용값" in r
    r = c("vat_reverse_charge", {**Y, "items": [_one(공급자="외국법인")]})
    assert "error" in r and "허용값" in r
    assert "error" in c("vat_reverse_charge", {**Y, "items": [_one(대가=-1)]})


def test_find_tool_surfaces_tool():
    r = c("find_tool", {"query": "국외사업자 용역 공급받는 면세사업자 부가가치세 대리납부", "n": 3})
    assert "vat_reverse_charge" in [x["도구"] for x in r["결과"]["후보"]], r
