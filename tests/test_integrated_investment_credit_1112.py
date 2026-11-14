"""0.39.0 integrated_investment_credit 정답 테스트(2026-11-12, Claude 손계산).
근거: 조세특례제한법 제24조(2021~2025 각 연말·2026.11.12. 시행본)와 개정 부칙, 시행령 제21조①⑦⑧⑨, 제130조."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(**k):
    return getattr(S.integrated_investment_credit, "fn", S.integrated_investment_credit)(**k)


G = lambda amount, kind="일반": [{"kind": kind, "amount": amount * M}]


def test_sme_general_asset_by_year():
    # 투자 8억, 직전 3년 합계 9억 → 연평균 3억, 초과 5억
    r = {y: f(year=y, size="중소기업", investments=G(800), prior3_total=900 * M)["결과"] for y in (2021, 2022, 2023, 2024, 2025, 2026)}
    assert r[2021] == r[2022] == {"기본공제": 80 * M, "추가공제": 15 * M, "공제_대상_세액": 95 * M, "적용": "본칙"}          # 10% + 5억 × 3%
    assert r[2023] == r[2024] == r[2025] == {"기본공제": 96 * M, "추가공제": 50 * M, "공제_대상_세액": 146 * M, "적용": "임시"}   # 12% + 5억 × 10%
    assert r[2026] == {"기본공제": 80 * M, "추가공제": 50 * M, "공제_대상_세액": 130 * M, "적용": "본칙"}                       # 10% + 5억 × 10%
    c = f(year=2025, size="중소기업", investments=G(800), prior3_total=900 * M)["계산"]
    assert c["본칙"]["합계"] == 130 * M and c["임시"]["합계"] == 146 * M and c["직전_3년_연평균"] == 300 * M and c["초과_투자액"] == 500 * M


def test_mid_sized_and_other_companies():
    one = lambda y, size: f(year=y, size=size, investments=G(1_000))["결과"]
    assert one(2022, "중견기업")["기본공제"] == 30 * M and one(2023, "중견기업")["기본공제"] == 70 * M      # 3% → 2023 임시 7%
    assert one(2024, "중견기업") == {"기본공제": 70 * M, "추가공제": 0, "공제_대상_세액": 70 * M, "적용": "임시"}   # 본칙 5% < 임시 7%
    assert one(2026, "중견기업")["기본공제"] == 50 * M
    assert one(2023, "일반")["기본공제"] == 30 * M                                                        # 임시 3%
    assert one(2024, "일반") == {"기본공제": 10 * M, "추가공제": 0, "공제_대상_세액": 10 * M, "적용": "본칙"}       # 본칙·임시 모두 1%, 평균이 없어 추가공제도 0
    # 평균이 있는 2024년 일반기업: 본칙 초과 9억 × 3% = 2,700만, 임시 × 10% = 9,000만 — 둘 다 기본공제 1,000만의 2배 한도에 걸려 같은 3,000만 → 본칙으로 표시
    r = f(year=2024, size="일반", investments=G(1_000), prior3_total=300 * M)
    assert r["결과"] == {"기본공제": 10 * M, "추가공제": 20 * M, "공제_대상_세액": 30 * M, "적용": "본칙"} and any("2배" in p for p in r["판단"])
    assert r["계산"]["임시"]["합계"] == 30 * M
    # 한도에 걸리지 않으면 임시가 큼: 투자 10억, 연평균 8억 → 초과 2억. 본칙 1,000만 + 600만, 임시 1,000만 + 2,000만
    r = f(year=2024, size="일반", investments=G(1_000), prior3_total=2_400 * M)
    assert r["결과"] == {"기본공제": 10 * M, "추가공제": 20 * M, "공제_대상_세액": 30 * M, "적용": "임시"} and r["계산"]["본칙"]["합계"] == 16 * M


def test_new_growth_and_national_strategic():
    one = lambda y, kind, size="중소기업": f(year=y, size=size, investments=G(1_000, kind))["결과"]["기본공제"]
    assert [one(y, "신성장") for y in (2022, 2023, 2024, 2025, 2026)] == [120 * M, 180 * M, 140 * M, 140 * M, 120 * M]
    assert [one(y, "국가전략") for y in (2021, 2022, 2023, 2024, 2025, 2026)] == [160 * M, 160 * M, 250 * M, 250 * M, 250 * M, 250 * M]
    assert one(2022, "국가전략", "일반") == 60 * M and one(2023, "국가전략", "중견기업") == 150 * M
    # 국가전략 추가공제율 4%(2021·2022·2024 본칙): 투자 10억, 연평균 4억 → 6억 × 4% = 2,400만
    assert f(year=2022, size="중소기업", investments=G(1_000, "국가전략"), prior3_total=1_200 * M)["결과"]["추가공제"] == 24 * M
    assert any("2021.7.1." in p for p in f(year=2021, size="중소기업", investments=G(1_000, "국가전략"))["판단"])


def test_semiconductor_and_graduation_band_from_2025():
    assert f(year=2025, size="중소기업", investments=G(1_000, "반도체"))["결과"]["기본공제"] == 300 * M
    assert f(year=2026, size="일반", investments=G(1_000, "반도체"))["결과"]["기본공제"] == 200 * M
    r = f(year=2025, size="졸업 뒤 3년", investments=G(800))
    assert r["결과"]["기본공제"] == 60 * M and r["결과"]["적용"] == "본칙" and any("졸업 뒤 3년" in p for p in r["판단"])      # 7.5%
    assert f(year=2026, size="졸업 뒤 3년", investments=G(1_000, "국가전략"))["결과"]["기본공제"] == 200 * M
    assert "error" in f(year=2024, size="중소기업", investments=G(1_000, "반도체"))
    assert "error" in f(year=2024, size="졸업 뒤 3년", investments=G(1_000))


def test_three_year_average_rules():
    # 이력 24개월에 2억 투자 → 36개월 환산 3억 → 연평균 1억. 투자 5억 → 초과 4억 × 10% = 4,000만
    r = f(year=2026, size="중소기업", investments=G(500), prior3_total=200 * M, history_months=24)
    assert r["계산"]["직전_3년_합계"] == 300 * M and r["계산"]["직전_3년_연평균"] == 100 * M and r["결과"]["추가공제"] == 40 * M
    # 6개월 과세연도: 연평균 3억 × 6/12 = 1.5억 → 초과 3.5억 × 10%
    assert f(year=2026, size="중소기업", investments=G(500), prior3_total=900 * M, months=6)["결과"]["추가공제"] == 35 * M
    # 평균이 없으면 추가공제 없음, 투자금액이 평균 이하여도 없음
    r = f(year=2026, size="중소기업", investments=G(500))
    assert r["결과"]["추가공제"] == 0 and any("제21조제9항" in p for p in r["판단"])
    assert f(year=2026, size="중소기업", investments=G(200), prior3_total=900 * M)["결과"]["추가공제"] == 0


def test_mixed_assets():
    # 2025년: 일반 5억 × 12%(임시) + 신성장 5억 × 14% = 1.3억, 초과(10억 − 4억) × 10% = 6,000만
    r = f(year=2025, size="중소기업", investments=G(500) + G(500, "신성장"), prior3_total=1_200 * M)
    assert r["결과"] == {"기본공제": 130 * M, "추가공제": 60 * M, "공제_대상_세액": 190 * M, "적용": "임시"}
    # 2022년 국가전략(4%)과 일반(3%)이 섞이면 추가공제는 계산하지 않음
    r = f(year=2022, size="중소기업", investments=G(500) + G(500, "국가전략"), prior3_total=600 * M)
    assert r["결과"]["기본공제"] == 130 * M and r["결과"]["추가공제"] is None and r["결과"]["공제_대상_세액"] == 130 * M


def test_overconcentration_zone_exclusion():
    r = f(year=2024, size="중소기업", investments=G(800), prior3_total=900 * M, in_overconcentration_zone=True, expansion=True)
    assert r["결과"] == {"기본공제": 0, "추가공제": 0, "공제_대상_세액": 0, "적용": "배제"} and "제130조제1항" in r["판단"][0]
    # 중소기업의 대체투자는 대상
    assert f(year=2024, size="중소기업", investments=G(800), in_overconcentration_zone=True)["결과"]["기본공제"] == 96 * M
    # 중소기업이 아니면 증설 여부와 관계없이 배제
    r = f(year=2024, size="중견기업", investments=G(800), in_overconcentration_zone=True)
    assert r["결과"]["적용"] == "배제" and "제130조제2항" in r["판단"][0]


def test_temp_notice_for_2024():
    r = f(year=2024, size="중소기업", investments=G(800))
    assert r["결과"]["적용"] == "임시" and any("2025.1.1. 이후 과세표준을 신고" in p for p in r["판단"])


def test_input_errors():
    assert "error" in f(year=2019, size="중소기업", investments=G(100))         # 2020 과세연도는 2021.1.1. 이후 신고분이라 계산(법률 제17759호 부칙 제4조제1항)
    assert "error" in f(year=2024, size="소기업", investments=G(100))
    assert "error" in f(year=2024, size="중소기업", investments=[])
    assert "error" in f(year=2024, size="중소기업", investments=[{"kind": "기계", "amount": 1}])
    assert "error" in f(year=2024, size="중소기업", investments=G(100), history_months=40)
