"""연금소득금액 — 소득세법 제20조의3·제14조③9호·제47조의2·제64조의4."""
from korean_tax_calc_mcp import server


def call(**kw):
    t = server.pension_income
    return getattr(t, "fn", t)(**kw)


def test_public_only():
    r = call(year=2022, public_pension=12_000_000)
    assert r["결과"]["총연금액"] == 12_000_000
    assert r["결과"]["연금소득공제"] == 5_900_000          # 490만 + (1,200만−700만)×20%
    assert r["결과"]["연금소득금액"] == 6_100_000


def test_private_under_threshold_separate_2023():
    r = call(year=2023, public_pension=5_000_000, private_pension=10_000_000, private_choice="분리")
    assert r["결과"]["분리과세연금소득"] == 10_000_000      # 사적연금 1,200만 이하 → 분리 선택
    assert r["결과"]["총연금액"] == 5_000_000
    assert r["결과"]["연금소득공제"] == 4_100_000          # 350만 + 150만×40%
    assert r["결과"]["연금소득금액"] == 900_000


def test_threshold_changes_2024():
    r23 = call(year=2023, private_pension=14_000_000, private_choice="분리")
    r24 = call(year=2024, private_pension=14_000_000, private_choice="분리")
    assert r23["결과"]["총연금액"] == 14_000_000            # 1,200만 초과 → 종합과세
    assert r24["결과"]["총연금액"] == 0                     # 1,500만 이하 → 분리 선택
    assert "15" in str(r23)                                 # 제64조의4 15% 분리 세액계산 선택 안내(2023~)


def test_choice_comprehensive():
    r = call(year=2024, private_pension=10_000_000, private_choice="종합")
    assert r["결과"]["총연금액"] == 10_000_000
    assert r["결과"]["연금소득공제"] == 5_500_000           # 490만 + 300만×20%


def test_always_separate_sources():
    r = call(year=2024, public_pension=3_000_000, retirement_source_pension=8_000_000, medical_withdrawal=2_000_000)
    assert r["결과"]["분리과세연금소득"] == 10_000_000
    assert r["결과"]["총연금액"] == 3_000_000
    assert r["결과"]["연금소득금액"] == 0                   # 350만 이하 → 전액 공제


def test_deduction_cap_900():
    r = call(year=2024, public_pension=50_000_000)
    assert r["결과"]["연금소득공제"] == 9_000_000           # 630만 + 3,600만×10% = 990만 → 900만 한도
    assert r["결과"]["연금소득금액"] == 41_000_000
    assert "제47조의2" in str(r["근거"])
