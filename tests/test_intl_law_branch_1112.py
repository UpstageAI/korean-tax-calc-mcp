"""0.31.12 특수관계인 거래의 법인세법 제52조 vs 국조법 정상가격 조정 분기(2026-11-12, Claude).
조문: 국조법 제4조②·제7조, 시행령 제4조(2018년까지 구법 제3조②·제4조, 구 영 제3조의2) — 2016·2018·2021·2023·2026 시행본 대조."""
import pytest
from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_foreign as F


def _fn(t):
    return getattr(t, "fn", t)


def test_branch_helper():
    assert F.related_party_law(False)["적용"] == "법인세법"
    r = F.related_party_law(True)
    assert r["적용"] == "국조법" and "제4조②" in r["근거"] and "제7조" in r["근거"]
    for t in ("무상이전·채무면제", "무수익자산", "출연금대납", "자본거래"):
        e = F.related_party_law(True, t)
        assert e["적용"] == "법인세법" and "시행령 제4조" in e["근거"] and "단서" in e["근거"]
        assert F.related_party_law(False, t)["적용"] == "법인세법"
    old = F.related_party_law(True, "일반", 2018)
    assert "구 국제조세조정에 관한 법률 제3조②" in old["근거"] and "제4조" in old["근거"] and "주의" not in old
    assert "제3조의2" in F.related_party_law(True, "자본거래", 2018)["근거"]
    assert "주의" in F.related_party_law(True, "자본거래", 2020)
    assert "주의" not in F.related_party_law(True, "자본거래", 2021)
    with pytest.raises(ValueError):
        F.related_party_law(True, "기타")


def test_unfair_transaction_domestic_unchanged():
    f = _fn(S.unfair_transaction)
    r = f(10_000, 9_700, 100_000)          # 차액 3,000만 = 3% → 부인 안 함
    assert r["결과"]["부당행위계산"] is False and "적용_규정" not in r["결과"] and r["근거"] == "법인세법 제52조, 시행령 제88조③"
    assert f(10_000, 9_000, 100_000)["결과"]["부당행위계산"] is True


def test_unfair_transaction_foreign_related_goes_to_transfer_pricing():
    f = _fn(S.unfair_transaction)
    r = f(10_000, 9_700, 100_000, foreign_related=True)     # 3% 차액도 조정 대상
    res = r["결과"]
    assert res["적용_규정"] == "국조법 정상가격 조정" and res["부당행위계산"] is False
    assert res["정상가격_조정_대상"] is True and res["조정대상_차액"] == 30_000_000
    assert "제7조" in r["근거"] and "법인세법 제52조" not in r["근거"]
    assert any("제8조" in p for p in r["판단"])
    same = f(10_000, 10_000, 100_000, foreign_related=True)
    assert same["결과"]["정상가격_조정_대상"] is False and same["결과"]["조정대상_차액"] == 0
    old = f(10_000, 9_700, 100_000, foreign_related=True, year=2018)
    assert "구 국제조세조정에 관한 법률" in old["근거"] and any("제5조" in p for p in old["판단"])


def test_unfair_transaction_foreign_exception_types_stay_under_corporate_tax_act():
    f = _fn(S.unfair_transaction)
    r = f(10_000, 9_700, 100_000, foreign_related=True, transaction_type="자본거래")
    assert r["결과"]["적용_규정"] == "법인세법 제52조" and r["결과"]["부당행위계산"] is False      # 3% < 5%
    assert "시행령 제4조" in r["근거"] and "법인세법 제52조" in r["근거"]
    r = f(10_000, 0, 100_000, foreign_related=True, transaction_type="무상이전·채무면제")
    assert r["결과"]["부당행위계산"] is True and "정상가격_조정_대상" not in r["결과"]
    w = f(5_000, 10_000, 100_000, wholly_owned_capital_increase=True, foreign_related=True, transaction_type="자본거래")
    assert w["결과"]["부당행위계산"] is False and len(w["판단"]) == 2


def test_unfair_transaction_year_range():
    assert "error" in _fn(S.unfair_transaction)(10_000, 9_000, 10, foreign_related=True, year=2015)


def test_deemed_interest_note_points_to_exceptions():
    r = _fn(S.deemed_interest)(movements=[S.Movement(date="2025-03-01", amount=1_000_000_000)], year_end="2025-12-31",
                               rate_mode="당좌선택", foreign_related=True)
    assert "국외특수관계인과의 국제거래" in r["결과"]["판단"] and "transaction_type" in r["결과"]["판단"]
    assert r["결과"]["익금산입"] == 38_564_383


def test_notes_say_arms_length_is_not_judged_and_deemed_rate_is_fallback():
    u = _fn(S.unfair_transaction)(10_000, 9_700, 100_000, foreign_related=True)
    assert any("정상가격인지 판정하지 않음" in p for p in u["판단"]) and any("제13조" in p for p in u["판단"])
    d = _fn(S.deemed_interest)(movements=[S.Movement(date="2025-03-01", amount=1_000_000_000)], year_end="2025-12-31",
                               rate_mode="당좌선택", foreign_related=True)
    assert "제8조① 단서" in d["결과"]["판단"] and "산출할 수 없는 경우에만" in d["결과"]["판단"]
    assert any("제13조" in x for x in d["주의"])
    e = _fn(S.deemed_interest)(movements=[S.Movement(date="2025-03-01", amount=1_000_000_000)], year_end="2025-12-31",
                               rate_mode="입력", market_rate=0.06, foreign_related=True)
    assert "정상이자율인지 판정하지 않음" in e["결과"]["판단"] and e["결과"]["익금산입"] == int(1_000_000_000 * 0.06 * 306 / 365)
