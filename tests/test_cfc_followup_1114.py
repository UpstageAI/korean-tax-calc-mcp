"""cfc_actual_dividend · cfc_share_disposal — Claude 작성(2026-11-14).
조문 대조: 국조법 2016·2019 시행본 제20조①②, 2020 시행본 제19조의2①②, 2021·현행 제32조①②, 시행령 2016 제36조의6, 2020 제35조, 현행 제68조,
법인세법 제18조의4③④(2023 시행본·현행). 국세법령정보시스템 연혁본."""
from korean_tax_calc_mcp import server as S

M = 10_000_000


def test_partial_dividend_consumes_and_reverses():
    r = S.cfc_actual_dividend(2025, 6 * M, [{"year": 2023, "amount": 10 * M, "used": 0}], cfc_name="A사")
    assert r["결과"]["익금불산입"] == 6 * M and r["결과"]["일반배당"] == 0
    assert r["결과"]["원장_갱신"] == [{"year": 2023, "amount": 10 * M, "used": 6 * M}]
    adj = r["세무조정"][0]
    assert (adj["조정"], adj["금액"], adj["소득처분"]) == ("익금불산입", 6 * M, "△유보") and "A사" in adj["구분"]
    assert "제32조①" in r["근거"] and "제68조①" in r["근거"]


def test_excess_dividend_and_18_4_note():
    r = S.cfc_actual_dividend(2025, 15 * M, [{"year": 2023, "amount": 10 * M}])
    assert r["결과"]["익금불산입"] == 10 * M and r["결과"]["일반배당"] == 5 * M
    assert any("제18조의4" in p["근거"] for p in r["판단"])
    r = S.cfc_actual_dividend(2022, 15 * M, [{"year": 2021, "amount": 10 * M}])
    assert not any("제18조의4" in p["근거"] for p in r["판단"])


def test_order_of_consumption():
    r = S.cfc_actual_dividend(2025, 4 * M, [{"year": 2022, "amount": 5 * M}, {"year": 2021, "amount": 3 * M}])
    assert [(x["배당간주_사업연도"], x["소진"]) for x in r["결과"]["소진_내역"]] == [(2021, 3 * M), (2022, 1 * M)]


def test_intermediate_limit():
    r = S.cfc_actual_dividend(2025, 5 * M, [{"year": 2023, "amount": 10 * M}],
                              intermediate={"cfc_to_intermediate": [{"amount": 10 * M, "ratio": 0.6}], "prior_excluded": 2 * M})
    assert r["결과"]["중간외국법인_한도"] == 4 * M and r["결과"]["익금불산입"] == 4 * M


def test_basis_by_year_and_individual():
    r = S.cfc_actual_dividend(2018, 1 * M, [{"year": 2017, "amount": 1 * M}])
    assert "구 국제조세조정에 관한 법률 제20조①" in r["근거"] and "이월익금" in r["판단"][0]["결론"]
    assert "제19조의2①" in S.cfc_actual_dividend(2020, 1 * M, [{"year": 2019, "amount": 1 * M}])["근거"]
    r = S.cfc_actual_dividend(2025, 1 * M, [{"year": 2024, "amount": 1 * M}], entity="개인")
    assert r["세무조정"] == [] and "배당소득에 해당하지 않음" in r["판단"][0]["결론"]


def test_input_errors():
    assert "error" in S.cfc_actual_dividend(2025, 1 * M, [])
    assert "error" in S.cfc_actual_dividend(2025, 1 * M, [{"year": 2023, "amount": 1 * M, "used": 2 * M}])


def test_disposal():
    r = S.cfc_share_disposal(2026, 10 * M, 6 * M, 5 * M)
    assert r["결과"]["익금불산입"] == 4 * M and r["세무조정"][0]["소득처분"] == "△유보"
    assert S.cfc_share_disposal(2026, 10 * M, 6 * M, 2 * M)["결과"]["익금불산입"] == 2 * M           # 양도차익 한도
    assert S.cfc_share_disposal(2026, 10 * M, 12 * M, 5 * M)["결과"]["익금불산입"] == 0              # 실제 배당 ≥ 간주
    assert S.cfc_share_disposal(2026, 10 * M, 0, -3 * M)["결과"]["익금불산입"] == 0                  # 차손
    r = S.cfc_share_disposal(2026, 10 * M, 6 * M, 5 * M, sold_ratio=0.5)
    assert r["결과"]["익금불산입"] == 2 * M and "가정" in r["단계별_계산"][0]
    assert "구 국제조세조정에 관한 법률 제20조②" in S.cfc_share_disposal(2018, 1, 0, 1)["근거"]
    r = S.cfc_share_disposal(2026, 10 * M, 6 * M, 5 * M, entity="개인")
    assert r["결과"]["양도소득_제외"] == 4 * M and "제94조①3호다목" in r["판단"][0]["결론"]


def test_deemed_dividend_adjustment_basis_by_year():
    import json
    import pathlib
    # 기존 정답 테스트의 적용 사례 하나를 2019년으로 돌려 세무조정 근거가 구 조문인지
    kw = dict(pretax_incomes=[1_000_000_000], taxes_paid=[50_000_000], ownership_chains=[[1]], related_party=True,
              distributable={"unappropriated_retained_earnings": 800_000_000}, fy_end="2019-12-31")
    r = S.cfc_deemed_dividend(year=2019, **kw)
    assert r["세무조정"] and "구 국제조세조정에 관한 법률 제17조①·제19조①" in r["세무조정"][0]["근거"]
    assert any("구 법 제20조①" in n for n in r["주의"])
    r = S.cfc_deemed_dividend(year=2025, **{**kw, "fy_end": "2025-12-31"})
    assert "제27조①·제31조" in r["세무조정"][0]["근거"] and any("cfc_actual_dividend" in n for n in r["주의"])
