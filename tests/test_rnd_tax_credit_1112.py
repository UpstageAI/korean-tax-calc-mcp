"""0.39.0 rnd_tax_credit 정답 테스트(2026-11-12, Claude 손계산).
근거: 조세특례제한법 제10조제1항제3호(2016~2025 각 연말·2026.11.12. 시행본), 법률 제20617호 부칙 제3조, 시행령 제9조제9항."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(**k):
    return getattr(S.rnd_tax_credit, "fn", S.rnd_tax_credit)(**k)


def test_sme_current_vs_incremental():
    # 당기 2억: 당기분 25% = 5,000만. 직전 1.2억, 4년 발생 [1.2억, 6,000만, 0, 0] → 발생 2개 연도 평균 9,000만 ≤ 직전 → 증가분 (2억 − 1.2억) × 50% = 4,000만 → 당기분
    r = f(year=2024, size="중소기업", current=200 * M, prior4=[120 * M, 60 * M, 0, 0])
    assert r["결과"] == {"공제_대상_세액": 50 * M, "선택": "당기분", "당기분": 50 * M, "증가분": 40 * M} and r["계산"]["4년_연평균"] == 90 * M and r["계산"]["발생한_과세연도_수"] == 2
    # 직전 5,000만이면 증가분 (2억 − 5,000만) × 50% = 7,500만 > 당기분 — 다만 4년 평균 [5,000만, 5,000만, 0, 0] = 5,000만 ≤ 직전이라 가능
    r = f(year=2024, size="중소기업", current=200 * M, prior4=[50 * M, 50 * M, 0, 0])
    assert r["결과"]["선택"] == "증가분" and r["결과"]["공제_대상_세액"] == 75 * M


def test_incremental_blocked_by_four_year_rule():
    # 직전 5,000만 < 4년 평균 (5,000만 + 1억)/2 = 7,500만 → 당기분만
    r = f(year=2024, size="중소기업", current=200 * M, prior4=[50 * M, 100 * M, 0, 0])
    assert r["결과"] == {"공제_대상_세액": 50 * M, "선택": "당기분", "당기분": 50 * M, "증가분": None} and any("단서" in p for p in r["판단"])
    # 4년간 발생이 없으면 당기분만
    r = f(year=2024, size="중소기업", current=200 * M, prior4=[0, 0, 0, 0])
    assert r["결과"]["증가분"] is None and any("발생하지 않아" in p for p in r["판단"])


def test_other_company_current_rate_by_year():
    one = lambda y, cur=3_000, rev=100_000: f(year=y, size="일반", current=cur * M, prior4=[cur * M] * 4, revenue=rev * M)["결과"]["당기분"]
    assert one(2016) == 90 * M        # 2% + 3%/2 = 3.5% → 3% 한도
    assert one(2017) == 75 * M        # 1% + 1.5% = 2.5%
    assert one(2018) == one(2024) == one(2026) == 45 * M      # 1.5%
    assert one(2020, cur=6_000) == 120 * M                    # 6%/2 = 3% → 2% 한도
    assert "error" in f(year=2024, size="일반", current=1, prior4=[0, 0, 0, 0])      # 수입금액 없음


def test_incremental_rate_by_size_and_year():
    inc = lambda y, size, **k: f(year=y, size=size, current=3_000 * M, prior4=[2_000 * M] * 4, **k)["결과"]["증가분"]
    assert inc(2024, "중소기업") == 500 * M and inc(2024, "중견기업") == 400 * M
    assert [inc(y, "일반", revenue=100_000 * M) for y in (2016, 2017, 2018, 2025)] == [400 * M, 300 * M, 250 * M, 250 * M]


def test_graduation_bands_and_2025_change():
    cur = lambda y, size, g=None: f(year=y, size=size, current=1_000 * M, prior4=[1_000 * M] * 4, graduated_year=g)["결과"]["당기분"]
    assert cur(2024, "졸업 뒤 3년") == 150 * M and cur(2024, "졸업 뒤 4~5년") == 100 * M and cur(2024, "중견기업") == 80 * M
    assert cur(2025, "졸업 뒤 3년", 2025) == 200 * M and cur(2026, "졸업 뒤 3년", 2025) == 200 * M      # 2025년 이후 졸업 20%
    assert cur(2025, "졸업 뒤 3년", 2023) == 150 * M and cur(2026, "졸업 뒤 4~5년", 2022) == 100 * M    # 그 전에 졸업한 기업은 종전 율
    assert "error" in f(year=2025, size="졸업 뒤 3년", current=1, prior4=[1, 1, 1, 1])                   # 졸업 연도 필요


def test_short_year_average():
    # 6개월 과세연도: 4년 평균 1억 × 6/12 = 5,000만 ≤ 직전 6,000만 → 증가분 가능
    r = f(year=2024, size="중소기업", current=100 * M, prior4=[60 * M, 140 * M, 0, 0], months=6)
    assert r["계산"]["4년_연평균"] == 50 * M and r["결과"]["증가분"] == 20 * M
    assert f(year=2024, size="중소기업", current=100 * M, prior4=[60 * M, 140 * M, 0, 0])["결과"]["증가분"] is None      # 12개월이면 평균 1억 > 6,000만


def test_notices_and_input_errors():
    r = f(year=2024, size="중소기업", current=200 * M, prior4=[0, 0, 0, 0])
    assert any("16B" in s and "적용제외" in s for s in r["주의"]) and any("제127조제4항" in s for s in r["주의"])
    assert any("13M" in s for s in f(year=2024, size="중견기업", current=200 * M, prior4=[0, 0, 0, 0])["주의"])
    assert "error" in f(year=2015, size="중소기업", current=1, prior4=[0, 0, 0, 0])
    assert "error" in f(year=2024, size="중소기업", current=1, prior4=[0, 0, 0])
    assert "error" in f(year=2024, size="소기업", current=1, prior4=[0, 0, 0, 0])


# ── minimum_tax_adjustment: 최저한세 적용제외 공제가 남은 세액을 넘을 때의 이월(조세특례제한법 제144조①②, 법인세법 제59조①) ──
def mt(**k):
    return getattr(S.minimum_tax_adjustment, "fn", S.minimum_tax_adjustment)(**k)["결과"]


BOOK23 = dict(year=2023, sme=True, net_income=700 * M, income_add=115 * M, income_deduct=15 * M, loss_carryforward=500 * M)      # 과세표준 3억, 산출 3,700만, 최저한세 2,100만
BOOK24 = dict(year=2024, sme=True, net_income=2_427_816_394, income_add=622_183_606, income_deduct=50 * M)                       # 과세표준 30억, 산출 5.5억, 최저한세 2.1억


def test_exempt_rnd_credit_over_remaining_tax_is_carried_forward():
    # 2023: 창업감면 1,850만 중 1,600만 적용 → 차감세액 2,100만. 연구·인력개발비 공제 3,000만 중 2,100만만 공제, 900만 이월
    r = mt(**BOOK23, reductions=[{"code": "111", "amount": 18_500_000}], credits=[{"code": "16B", "current": 30 * M}])
    assert r["차감세액"] == 21 * M and r["적용제외_차감후세액"] == 0
    assert r["별지8"]["16B"] == {"대상세액": 30 * M, "감면세액": 21 * M, "전기이월액": 0, "당기발생액": 30 * M, "공제세액": 21 * M}
    assert {"코드": "16B", "발생연도": 2023, "금액": 9 * M} in r["이월_미공제"] and r["최저한세_적용제외"]["세액공제"] == 21 * M


def test_exempt_rnd_carryforward_used_first_next_year():
    # 2024: 5.5억 − 창업감면 2.75억 = 2.75억 → 연구·인력개발비 이월 900만 + 당기 5,000만 = 5,900만 공제 → 2.16억
    r = mt(**BOOK24, reductions=[{"code": "111", "amount": 275 * M}], credits=[{"code": "16B", "current": 50 * M, "carryforward": [{"year": 2023, "amount": 9 * M}]}])
    assert r["적용제외_차감후세액"] == 216 * M and r["별지8"]["16B"]["공제세액"] == 59 * M and r["별지8"]["16B"]["전기이월액"] == 9 * M
    assert not [x for x in r["이월_미공제"] if x["코드"] == "16B"]


def test_exempt_credit_within_remaining_tax_keeps_old_shape():
    r = mt(**BOOK24, reductions=[{"code": "111", "amount": 275 * M}], credits=[{"code": "16B", "current": 50 * M}])
    assert r["별지8"]["16B"] == {"대상세액": 50 * M, "감면세액": 50 * M} and r["적용제외_차감후세액"] == 225 * M and r["이월_미공제"] == []


def test_foreign_tax_credit_excess_not_carried_here():
    # 외국납부세액공제(101)는 법인세법 제57조의 한도·이월을 따로 계산 — 이 도구는 종전처럼 차감만
    r = mt(**BOOK23, reductions=[{"code": "111", "amount": 18_500_000}], credits=[{"code": "101", "current": 30 * M}])
    assert r["적용제외_차감후세액"] == 0 and r["이월_미공제"] == [] and r["별지8"]["101"] == {"대상세액": 30 * M, "감면세액": 30 * M}
