"""tax_crime_settlement_amount — 조세범 처벌절차법 시행령 별표(2014.6.30.·2019.2.12.·2026.2.27. 개정본, 국세법령정보시스템 HWP 원문). Claude 작성(2026-11-14)."""
from korean_tax_calc_mcp import server as S

E8 = 100_000_000


def one(o, nd="2026-06-01", **kw):
    r = S.tax_crime_settlement_amount([o], nd, **kw)
    assert "error" not in r, r
    return r["결과"]


def test_evasion_counts():
    assert one({"offense": "제3조제1항본문", "count": 1, "base": 100_000_000})["벌금상당액_합계"] == 50_000_000
    assert one({"offense": "제3조제1항본문", "count": 2, "base": 100_000_000})["벌금상당액_합계"] == 100_000_000
    assert one({"offense": "제3조제1항본문", "count": 5, "base": 100_000_000})["벌금상당액_합계"] == 200_000_000      # 3차 이상 2배 = 상한 2배
    assert one({"offense": "제3조제1항단서", "count": 3, "base": 600_000_000})["벌금상당액_합계"] == 1_800_000_000


def test_cap_applies():
    r = one({"offense": "제3조제1항본문", "count": 3, "base": 100_000_000, "habitual": True})      # 2배 × 1.5 = 3배 > 상한 2배
    assert r["벌금상당액_합계"] == 200_000_000 and r["범칙행위별"][0]["상한_적용"] is True


def test_voluntary_reduction():
    v = {"type": "수정신고", "due_date": "2025-03-31", "filed_on": "2025-09-30", "before_investigation": True, "additional_tax_paid": True}
    assert one({"offense": "제3조제1항본문", "base": 100_000_000, "voluntary": v})["벌금상당액_합계"] == 25_000_000
    v2 = dict(v, filed_on="2025-10-01")
    assert one({"offense": "제3조제1항본문", "base": 100_000_000, "voluntary": v2})["벌금상당액_합계"] == 40_000_000
    v3 = dict(v, additional_tax_paid=False)
    assert one({"offense": "제3조제1항본문", "base": 100_000_000, "voluntary": v3})["벌금상당액_합계"] == 50_000_000
    late = {"type": "기한후신고", "due_date": "2025-03-31", "filed_on": "2025-04-30", "before_investigation": True, "additional_tax_paid": True}
    assert one({"offense": "제3조제1항본문", "base": 100_000_000, "voluntary": late})["벌금상당액_합계"] == 25_000_000


def test_items():
    assert one({"offense": "제4조제1항", "base": 3 * E8})["벌금상당액_합계"] == 700_000_000                     # 1억 + 2억×3
    assert one({"offense": "제4조제1항", "count": 2, "base": 3 * E8})["벌금상당액_합계"] == 1_400_000_000
    assert one({"offense": "제8조", "base": 1_000_000_000})["벌금상당액_합계"] == 20_000_000                # 10% = 1억 → 2천만 한도
    assert one({"offense": "제8조", "base": 10_000_000})["벌금상당액_합계"] == 5_000_000                    # 하한 500만
    assert one({"offense": "제11조제1항", "base": 0})["벌금상당액_합계"] == 500_000
    assert one({"offense": "제11조제2항", "base": 30_000_000})["벌금상당액_합계"] == 7_500_000                  # 너목 1차 1,500만 × 1/2
    assert one({"offense": "제10조제3항", "base": 1_000_000_000})["벌금상당액_합계"] == 100_000_000
    assert one({"offense": "제10조제4항", "base": 1_000_000_000, "professional": True})["벌금상당액_합계"] == 150_000_000
    assert one({"offense": "제12조제4호", "base": 100_000})["벌금상당액_합계"] == 1_000_000
    assert one({"offense": "제13조제2항", "base": 300_000})["벌금상당액_합계"] == 1_000_000
    assert one({"offense": "제16조제1항", "base": 6_000_000_000})["벌금상당액_합계"] == 780_000_000
    assert one({"offense": "제7조제1항·제2항", "base": 100_000_000, "property_value": 40_000_000})["벌금상당액_합계"] == 30_000_000
    assert one({"offense": "제7조제3항", "base": 10_000_000})["벌금상당액_합계"] == 6_666_660                    # 2/3, 10원 미만 절사


def test_liquor():
    assert one({"offense": "제6조", "liquor": {"kind": "위스키·브랜디", "liters": 50}})["벌금상당액_합계"] == 2_000_000
    assert one({"offense": "제6조", "liquor": {"kind": "탁주", "liters": 600, "act": "나"}})["벌금상당액_합계"] == 1_500_000
    assert one({"offense": "제6조", "liquor": {"kind": "그 밖", "liters": 20000, "liquor_tax": 20_000_000}})["벌금상당액_합계"] == 60_000_000


def test_concurrence():
    r = S.tax_crime_settlement_amount([{"offense": "제9조제1항"}, {"offense": "제8조", "base": 100_000_000}], "2026-06-01")["결과"]
    assert r["벌금상당액_합계"] == 15_000_000            # max 1천만 + 1/2 = 1,500만 ≤ 합산 2천만
    r = S.tax_crime_settlement_amount([{"offense": "제9조제1항"}, {"offense": "제3조제1항본문", "base": 10_000_000}], "2026-06-01")["결과"]
    assert r["벌금상당액_합계"] == 15_000_000            # 1)그룹 1천만 + 2)그룹 500만


def test_table_versions():
    assert "error" in S.tax_crime_settlement_amount([{"offense": "제15조제1항"}], "2019-01-20")
    r = S.tax_crime_settlement_amount([{"offense": "제15조제1항"}], "2019-03-01", act_date="2019-01-20")
    assert r["결과"]["적용_별표"].endswith("2019.2.12.>") and len(r["경고"]) == 2
    r = S.tax_crime_settlement_amount([{"offense": "제9조제1항"}, {"offense": "제15조제1항"}], "2018-12-01")
    assert "error" in r
    assert "2026.2.27." in S.tax_crime_settlement_amount([{"offense": "제9조제1항"}], "2026-03-01")["결과"]["적용_별표"]


def test_input_errors():
    assert "error" in S.tax_crime_settlement_amount([{"offense": "제5조①"}], "2026-01-01")
    assert "error" in S.tax_crime_settlement_amount([{"offense": "제8조", "base": 1, "habitual": True}], "2026-01-01")
    assert "error" in S.tax_crime_settlement_amount([{"offense": "제3조제1항본문"}], "2026-01-01")
