"""0.30.0 정답 테스트(수정 금지, Claude 작성) — individual_foreign_tax_credit · overseas_account_reporting · capital_gains_unfair_transaction.
근거: 소득세법 제57조·영 제117조 / 국조법 제53·54·90조·영 제92·93·94·147조 / 소득세법 제101조·영 제167조. 조문은 2026 시행본(korean-tax-mcp)으로 확인."""
from _helpers import call as c

M = 1_000_000


# ── 도구 1 individual_foreign_tax_credit ───────────────────────────────────────
def test_ftc_country_limits_and_carryforward_amount():
    r = c("individual_foreign_tax_credit", {"year": 2026, "calculated_tax": 100 * M, "total_income": 500 * M,
          "countries": [{"country": "미국", "foreign_income": 100 * M, "foreign_tax": 25 * M},
                        {"country": "일본", "foreign_income": 50 * M, "foreign_tax": 3 * M}]})
    assert "error" not in r, r
    g = r["결과"]
    assert g["외국납부세액공제액"] == 23 * M          # 미국 min(25, 한도 20) + 일본 min(3, 한도 10)
    assert g["공제한도_합계"] == 30 * M
    assert g["이월액"] == 5 * M
    us = [x for x in g["국가별"] if x["국가"] == "미국"][0]
    assert us["공제한도"] == 20 * M and us["공제액"] == 20 * M and us["이월액"] == 5 * M
    assert "제57조" in r["근거"] and "제117조" in r["근거"]
    assert any("2027~2036" in str(x) for x in [g.get("이월기간", ""), *r.get("주의", []), *r.get("판단", [])])


def test_ftc_prior_carryforward_used_within_limit_oldest_first():
    r = c("individual_foreign_tax_credit", {"year": 2026, "calculated_tax": 100 * M, "total_income": 500 * M,
          "countries": [{"country": "미국", "foreign_income": 100 * M, "foreign_tax": 15 * M}],
          "carryforward": [{"country": "미국", "year": 2024, "amount": 4 * M}, {"country": "미국", "year": 2023, "amount": 3 * M}]})
    g = r["결과"]
    us = g["국가별"][0]
    assert us["당기공제"] == 15 * M and us["이월공제"] == 5 * M and us["공제액"] == 20 * M   # 한도 20: 2023분 3 전부 + 2024분 2
    assert g["외국납부세액공제액"] == 20 * M and g["이월액"] == 2 * M                      # 2024분 남은 2는 계속 이월


def test_ftc_carryforward_expired_after_10_years():
    r = c("individual_foreign_tax_credit", {"year": 2026, "calculated_tax": 100 * M, "total_income": 500 * M,
          "countries": [{"country": "미국", "foreign_income": 100 * M, "foreign_tax": 0}],
          "carryforward": [{"country": "미국", "year": 2015, "amount": 4 * M}]})
    g = r["결과"]
    assert g["외국납부세액공제액"] == 0 and g["이월기간경과분"] == 4 * M
    assert any("필요경비" in str(x) for x in r.get("판단", []) + r.get("주의", []))


def test_ftc_treaty_rate_caps_recognized_foreign_tax():
    r = c("individual_foreign_tax_credit", {"year": 2026, "calculated_tax": 100 * M, "total_income": 500 * M,
          "countries": [{"country": "미국", "foreign_income": 100 * M, "foreign_tax": 30 * M, "treaty_rate": 0.15, "gross_amount": 100 * M}]})
    us = r["결과"]["국가별"][0]
    assert us["인정_외국소득세액"] == 15 * M and us["공제액"] == 15 * M and r["결과"]["이월액"] == 0


def test_ftc_retirement_income_no_carryforward():
    r = c("individual_foreign_tax_credit", {"year": 2026, "income_kind": "퇴직", "calculated_tax": 50 * M, "total_income": 200 * M,
          "countries": [{"country": "미국", "foreign_income": 100 * M, "foreign_tax": 40 * M}]})
    g = r["결과"]
    assert g["외국납부세액공제액"] == 25 * M and g["이월액"] == 0
    assert any("퇴직" in str(x) and "이월" in str(x) for x in r.get("주의", []) + r.get("판단", []))


def test_ftc_input_errors():
    assert "error" in c("individual_foreign_tax_credit", {"year": 2026, "calculated_tax": 1, "total_income": 0, "countries": [{"country": "미국", "foreign_income": 1, "foreign_tax": 1}]})
    assert "error" in c("individual_foreign_tax_credit", {"year": 2026, "calculated_tax": 1, "total_income": 1, "countries": [{"country": "미국", "foreign_income": -1, "foreign_tax": 1}]})
    assert "error" in c("individual_foreign_tax_credit", {"year": 2026, "income_kind": "사업", "calculated_tax": 1, "total_income": 1, "countries": []})


# ── 도구 2 overseas_account_reporting ────────────────────────────────────────
TOT = [100 * M, 120 * M, 300 * M, 480 * M, 500 * M, 520 * M, 410 * M, 200 * M, 100 * M, 90 * M, 80 * M, 70 * M]


def test_oar_duty_when_any_month_end_exceeds_500m():
    r = c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": TOT})
    assert "error" not in r, r
    g = r["결과"]
    assert g["신고의무"] is True and g["최고잔액"] == 520 * M and g["최고잔액_월"] == 6
    assert g["신고기한"] == "2026-06-30"
    assert g["위반금액"] == 520 * M and g["과태료"] == 52 * M                 # ×10%, 10억 한도 안
    assert g["과태료_범위"] == [26 * M, 78 * M]                                # ±50%
    assert "제53조" in r["근거"] and "제147조" in r["근거"]
    assert any("실질적 소유자" in str(x) for x in r.get("판단", []) + r.get("주의", []))


def test_oar_exactly_500m_is_not_over():
    g = c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": [500 * M] * 12})["결과"]
    assert g["신고의무"] is False and g["과태료"] == 0


def test_oar_accounts_summed_and_penalty_cap():
    r = c("overseas_account_reporting", {"year": 2025, "accounts": [{"name": "A", "month_end_krw": [6_000 * M] + [0] * 11},
                                                                    {"name": "B", "month_end_krw": [6_000 * M] + [0] * 11}]})
    g = r["결과"]
    assert g["최고잔액"] == 12_000 * M and g["과태료"] == 1_000 * M              # 12억 → 12,000M×10%=1,200M → 10억 한도


def test_oar_underreport_and_correction_discount():
    g = c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": TOT, "reported_amount_krw": 320 * M,
                                         "corrected_on": "2026-09-01"})["결과"]
    assert g["위반금액"] == 200 * M and g["과태료"] == 20 * M
    assert g["감경비율"] == 90 and g["감경후_과태료"] == 2 * M                 # 기한 후 6개월 이내 수정신고 90%


def test_oar_correction_after_four_years_no_discount():
    g = c("overseas_account_reporting", {"year": 2020, "month_end_totals_krw": TOT, "corrected_on": "2025-12-01"})["결과"]
    assert g["감경비율"] == 0 and g["감경후_과태료"] == g["과태료"]


def test_oar_exemptions():
    g = c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": TOT, "foreigner_resident_years_in_korea_last10": 4})["결과"]
    assert g["신고의무"] is False and "외국인 거주자" in "".join(g["면제사유"])
    g = c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": TOT, "overseas_korean_days_in_korea": 100})["결과"]
    assert g["신고의무"] is False and "재외국민" in "".join(g["면제사유"])
    g = c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": TOT, "overseas_korean_days_in_korea": 183})["결과"]
    assert g["신고의무"] is True
    g = c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": TOT, "treaty_resident_of_other_country": True})["결과"]
    assert g["신고의무"] is False


def test_oar_unexplained_penalty_and_errors():
    g = c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": TOT, "unexplained_amount_krw": 100 * M})["결과"]
    assert g["소명불이행_과태료"] == 20 * M
    assert "error" in c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": [1] * 11})
    assert "error" in c("overseas_account_reporting", {"year": 2025})
    assert "error" in c("overseas_account_reporting", {"year": 2025, "month_end_totals_krw": TOT, "accounts": [{"name": "A", "month_end_krw": [0] * 12}]})


# ── 도구 3 capital_gains_unfair_transaction ───────────────────────────────────
def test_cgut_low_price_transfer_3억_threshold():
    r = c("capital_gains_unfair_transaction", {"transaction": "양도", "market_value": 1_000 * M, "price": 700 * M, "related_party": True})
    assert "error" not in r, r
    g = r["결과"]
    assert g["부당행위계산"] is True and g["차액"] == 300 * M and g["기준_3억_충족"] is True
    assert g["조정후_양도가액"] == 1_000 * M
    assert "제101조" in r["근거"] and "제167조" in r["근거"]


def test_cgut_small_gap_not_unfair():
    g = c("capital_gains_unfair_transaction", {"transaction": "양도", "market_value": 1_000 * M, "price": 960 * M, "related_party": True})["결과"]
    assert g["부당행위계산"] is False and g["조정후_양도가액"] == 960 * M     # 0.4억 < 3억, < 5%(0.5억)


def test_cgut_five_percent_threshold():
    g = c("capital_gains_unfair_transaction", {"transaction": "양도", "market_value": 400 * M, "price": 370 * M, "related_party": True})["결과"]
    assert g["부당행위계산"] is True and g["기준_5퍼센트_충족"] is True and g["조정후_양도가액"] == 400 * M   # 0.3억 ≥ 5%(0.2억)


def test_cgut_high_price_acquisition():
    g = c("capital_gains_unfair_transaction", {"transaction": "취득", "market_value": 500 * M, "price": 600 * M, "related_party": True})["결과"]
    assert g["부당행위계산"] is True and g["조정후_취득가액"] == 500 * M


def test_cgut_direction_matters_and_unrelated():
    g = c("capital_gains_unfair_transaction", {"transaction": "양도", "market_value": 500 * M, "price": 900 * M, "related_party": True})["결과"]
    assert g["부당행위계산"] is False                                           # 고가 양도는 양도자에게 불리하지 않음
    g = c("capital_gains_unfair_transaction", {"transaction": "양도", "market_value": 1_000 * M, "price": 500 * M, "related_party": False})["결과"]
    assert g["부당행위계산"] is False


def test_cgut_corporate_counterparty_exception_and_fraud():
    base = {"transaction": "양도", "market_value": 1_000 * M, "price": 600 * M, "related_party": True,
            "counterparty_is_corporation": True, "corporate_tax_market_value_applies": True}
    assert c("capital_gains_unfair_transaction", base)["결과"]["부당행위계산"] is False
    assert c("capital_gains_unfair_transaction", {**base, "fraud": True})["결과"]["부당행위계산"] is True


def test_cgut_gift_then_transfer_comparison():
    r = c("capital_gains_unfair_transaction", {"mode": "증여후양도", "gift_date": "2020-03-01", "transfer_date": "2026-02-01",
          "donee_relation": "기타특수관계인", "donee_gift_tax": 100 * M, "donee_capital_gains_tax": 50 * M, "donor_direct_capital_gains_tax": 200 * M})
    g = r["결과"]
    assert g["증여자_직접양도_간주"] is True and g["수증자_세액합계"] == 150 * M
    assert any("증여세" in str(x) and "부과하지" in str(x) for x in r.get("판단", []))
    g = c("capital_gains_unfair_transaction", {"mode": "증여후양도", "gift_date": "2020-03-01", "transfer_date": "2026-02-01",
          "donee_relation": "기타특수관계인", "donee_gift_tax": 150 * M, "donee_capital_gains_tax": 100 * M, "donor_direct_capital_gains_tax": 200 * M})["결과"]
    assert g["증여자_직접양도_간주"] is False


def test_cgut_gift_then_transfer_exclusions():
    base = {"mode": "증여후양도", "gift_date": "2015-01-01", "transfer_date": "2026-02-01", "donee_relation": "기타특수관계인",
            "donee_gift_tax": 1, "donee_capital_gains_tax": 1, "donor_direct_capital_gains_tax": 100 * M}
    g = c("capital_gains_unfair_transaction", base)["결과"]
    assert g["증여자_직접양도_간주"] is False and "10년" in g["적용제외_사유"]
    g = c("capital_gains_unfair_transaction", {**base, "gift_date": "2020-01-01", "donee_relation": "배우자"})["결과"]
    assert g["증여자_직접양도_간주"] is False and "제97조의2" in g["적용제외_사유"]
    g = c("capital_gains_unfair_transaction", {**base, "gift_date": "2020-01-01", "income_belongs_to_donee": True})["결과"]
    assert g["증여자_직접양도_간주"] is False and "실질" in g["적용제외_사유"]


def test_cgut_errors():
    assert "error" in c("capital_gains_unfair_transaction", {"transaction": "교환", "market_value": 1, "price": 1, "related_party": True})
    assert "error" in c("capital_gains_unfair_transaction", {"transaction": "양도", "market_value": 0, "price": 1, "related_party": True})
    assert "error" in c("capital_gains_unfair_transaction", {"mode": "증여후양도", "gift_date": "2020-01-01", "transfer_date": "2019-01-01",
                                                               "donee_relation": "기타특수관계인", "donee_gift_tax": 1, "donee_capital_gains_tax": 1, "donor_direct_capital_gains_tax": 1})


def test_find_tool_surfaces_new_tools():
    names = lambda q: [x["도구"] for x in c("find_tool", {"query": q, "n": 4})["결과"]["후보"]]
    assert "individual_foreign_tax_credit" in names("개인 외국납부세액공제 종합소득")
    assert "overseas_account_reporting" in names("해외금융계좌 신고 의무 5억")
    assert "capital_gains_unfair_transaction" in names("양도소득 부당행위계산 저가 양도 시가")
