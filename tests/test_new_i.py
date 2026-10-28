"""조정대상지역 다주택 중과(소득세법 제104조⑦·제95조②, 시행령 제167조의3①·제167조의10①) 회귀 테스트.

기본세율(제55조①) 과세표준 1억원: 2018~2022년 1,590만 + (1억 − 8,800만) × 35% = 2,010만,
2023년 이후 1,536만 + (1억 − 8,800만) × 35% = 1,956만."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def _tax(**kw):
    a = {"base": 100_000_000, "asset_type": "주택", "acquisition_date": "2015-01-01"}
    a.update(kw)
    return c("capital_gains_tax", a)


def _inc(**kw):
    a = {"asset_type": "주택", "acquisition_date": "2015-01-01", "transfer_price": 500_000_000,
         "acquisition_price": 300_000_000, "one_house": False, "apply_basic_deduction": True}
    a.update(kw)
    return c("capital_gains_income", a)


# ── capital_gains_tax: 기간별 가산세율(제104조⑦) ──
def test_2주택_2018_2021_10pct():
    # 2021.6.1. 전 양도: 제55조① 세율 + 10%p (법률 제15225호 부칙 제1조1호) → 2,010만 + 1,000만
    r = _tax(transfer_date="2021-03-01", houses_count=2, adjusted_area=True)
    assert r["결과"]["산출세액"] == 30_100_000
    assert r["결과"]["다주택_중과"] == {"적용": True, "가산세율": 0.1, "구분": "2주택"}


def test_3주택_2021_6_1_이후_30pct():
    # 2021.6.1. 이후 양도: 3주택 이상 +30%p (법률 제17477호 부칙 제3조) → 2,010만 + 3,000만
    r = _tax(transfer_date="2021-07-01", houses_count=3, adjusted_area=True)
    assert r["결과"]["산출세액"] == 50_100_000


def test_2주택_2021_5_31_경계():
    assert _tax(transfer_date="2021-05-31", houses_count=2, adjusted_area=True)["결과"]["산출세액"] == 30_100_000
    assert _tax(transfer_date="2021-06-01", houses_count=2, adjusted_area=True)["결과"]["산출세액"] == 40_100_000


def test_중과_시행일_2018_4_1():
    # 2018.3.31. 양도는 제104조⑦ 시행 전 — 2주택은 기본세율
    r = _tax(transfer_date="2018-03-31", houses_count=2, adjusted_area=True)
    assert r["결과"]["산출세액"] == 20_100_000 and r["결과"]["다주택_중과"]["적용"] is False
    r = _tax(transfer_date="2018-04-01", houses_count=2, adjusted_area=True)
    assert r["결과"]["산출세액"] == 30_100_000


def test_단기보유_큰세액_2021_이후():
    # 보유 1년 미만, 2021.6.1. 이후: 중과 2,010만+2,000만=4,010만 vs 제104조①3호 70% 7,000만 → 큰 세액
    r = _tax(acquisition_date="2021-01-01", transfer_date="2021-07-01", houses_count=2, adjusted_area=True)
    assert r["결과"]["산출세액"] == 70_000_000


def test_단기보유_큰세액_2021_전():
    # 보유 1년 미만, 2021.6.1. 전: 3주택 중과 2,010만+2,000만=4,010만 vs ①3호 40% 4,000만 → 4,010만
    r = _tax(acquisition_date="2019-01-01", transfer_date="2019-06-01", houses_count=3, adjusted_area=True)
    assert r["결과"]["산출세액"] == 40_100_000


def test_조정대상지역_밖_일반세율():
    r = _tax(transfer_date="2021-07-01", houses_count=3, adjusted_area=False)
    assert r["결과"]["산출세액"] == 20_100_000 and r["결과"]["다주택_중과"]["적용"] is False


# ── 한시 배제 ──
def test_12호_보유10년_2019_12_17부터():
    # 영 제167조의3①12호(2020.2.11. 개정) 부칙 제18조: 2019.12.17. 이후 양도분부터
    a = dict(acquisition_date="2009-01-01", houses_count=3, adjusted_area=True)
    assert _tax(transfer_date="2019-12-16", **a)["결과"]["산출세액"] == 40_100_000
    r = _tax(transfer_date="2019-12-17", **a)
    assert r["결과"]["산출세액"] == 20_100_000 and "12호" in r["판단"][0]["근거"]
    assert _tax(transfer_date="2020-06-30", **a)["결과"]["산출세액"] == 20_100_000
    assert _tax(transfer_date="2020-07-01", **a)["결과"]["산출세액"] == 40_100_000


def test_12호_보유10년_미만은_중과():
    r = _tax(acquisition_date="2012-01-01", transfer_date="2020-03-01", houses_count=2, adjusted_area=True)
    assert r["결과"]["산출세액"] == 30_100_000


def test_12호의2_기간과_연장():
    # 영 제167조의3①12호의2(2022.5.31. 개정) 부칙 제4조: 2022.5.10. 이후 양도분, 기한 연장 2023→2024→2025→2026.5.9.
    a = dict(houses_count=3, adjusted_area=True)
    assert _tax(transfer_date="2022-05-09", **a)["결과"]["산출세액"] == 50_100_000
    assert _tax(transfer_date="2022-05-10", **a)["결과"]["산출세액"] == 20_100_000
    for d in ("2023-05-10", "2024-05-10", "2025-05-10", "2026-05-09"):
        r = _tax(transfer_date=d, **a)
        assert r["결과"]["산출세액"] == 19_560_000 and "한시 배제" in r["판단"][0]["결론"], d
    # 2026.5.10. 이후: 가목 종료 → 중과 1,956만 + 3,000만, 경과 요건 안내
    r = _tax(transfer_date="2026-05-10", **a)
    assert r["결과"]["산출세액"] == 49_560_000
    assert any(h["항목"] == "한시 배제 경과 요건" for h in r["판단"])


def test_12호의2_보유2년_미만은_중과():
    r = _tax(acquisition_date="2023-01-01", transfer_date="2024-03-01", houses_count=2, adjusted_area=True)
    # 보유 1년: 중과 1,956만+2,000만=3,956만 vs ①2호 60% 6,000만 → 6,000만
    assert r["결과"]["산출세액"] == 60_000_000 and r["결과"]["다주택_중과"]["적용"] is True


def test_한시배제_경과_사용자주장():
    r = _tax(transfer_date="2026-07-01", houses_count=2, adjusted_area=True, exclusion_reason="한시배제_경과")
    assert r["결과"]["산출세액"] == 19_560_000 and "나목·다목" in r["판단"][0]["근거"]
    r = _tax(transfer_date="2026-11-10", houses_count=2, adjusted_area=True, exclusion_reason="한시배제_경과")
    assert r["error"].startswith("입력 확인 필요")


# ── 사용자 주장 배제 사유 ──
def test_배제사유_장기임대주택():
    r = _tax(transfer_date="2021-07-01", houses_count=3, adjusted_area=True, exclusion_reason="장기임대주택")
    assert r["결과"]["산출세액"] == 20_100_000 and "제167조의3①2호" in r["판단"][0]["근거"]


def test_배제사유_2주택전용을_3주택에_쓰면_거부():
    r = _tax(transfer_date="2021-07-01", houses_count=3, adjusted_area=True, exclusion_reason="취학근무요양")
    assert "error" in r


def test_배제사유_기타는_근거필수():
    assert "error" in _tax(transfer_date="2021-07-01", houses_count=2, adjusted_area=True, exclusion_reason="기타")
    r = _tax(transfer_date="2021-07-01", houses_count=2, adjusted_area=True, exclusion_reason="기타",
             exclusion_basis="영 제167조의10①5호 동거봉양 합가 10년 이내")
    assert r["결과"]["산출세액"] == 20_100_000 and "동거봉양" in r["판단"][0]["근거"]


def test_배제사유_모르는값_거부():
    assert "error" in _tax(transfer_date="2021-07-01", houses_count=2, adjusted_area=True, exclusion_reason="아무거나")


# ── 이전 입력(heavy_multi_home) 호환 ──
def test_heavy_flag만_중과기간은_사실요구():
    r = _tax(transfer_date="2021-03-01", heavy_multi_home=True)
    assert r["error"].startswith("입력 확인 필요") and "houses_count" in r["필요 입력"]


def test_heavy_false인데_사실은_중과면_거부():
    r = _tax(transfer_date="2021-07-01", heavy_multi_home=False, houses_count=2, adjusted_area=True)
    assert "error" in r


def test_토지에_중과입력_거부():
    r = c("capital_gains_tax", {"base": 100_000_000, "asset_type": "토지", "acquisition_date": "2015-01-01",
                                "transfer_date": "2021-07-01", "houses_count": 2, "adjusted_area": True})
    assert "error" in r


# ── capital_gains_income: 장기보유특별공제 배제(제95조②) + 중과 세율 ──
def test_income_중과_장특공_배제_세액():
    # 양도차익 2억, 장특공 배제 → 소득금액 2억, 과세표준 1억9,750만
    # 2021 기본세율: 3,760만 + (1억9,750만 − 1억5천만) × 38% = 5,565만, +10%p 1,975만 → 7,540만
    r = _inc(transfer_date="2021-03-01", houses_count=2, adjusted_area=True)
    g = r["결과"]
    assert g["장기보유특별공제액"] == 0 and g["양도소득금액"] == 200_000_000
    assert g["양도소득_과세표준"] == 197_500_000 and g["산출세액"] == 75_400_000
    assert any("장기보유특별공제 배제" in h["결론"] for h in r["판단"])


def test_income_한시배제_장특공_적용():
    # 2024.3.1. 양도, 보유 9년 → 12호의2 배제, 표1 18% → 장특공 3,600만, 소득금액 1억6,400만, 과세표준 1억6,150만
    # 2024 기본세율: 3,706만 + (1억6,150만 − 1억5천만) × 38% = 4,143만
    r = _inc(transfer_date="2024-03-01", houses_count=3, adjusted_area=True)
    g = r["결과"]
    assert g["장기보유특별공제액"] == 36_000_000 and g["산출세액"] == 41_430_000
    assert g["다주택_중과"]["적용"] is False


def test_income_2026_6_중과_3주택():
    # 2026.6.1. 양도, 보유 11년: 장특공 배제, 과세표준 1억9,750만
    # 2026 기본세율 3,706만 + 4,750만 × 38% = 5,511만, +30%p 5,925만 → 1억1,436만
    r = _inc(transfer_date="2026-06-01", houses_count=3, adjusted_area=True)
    assert r["결과"]["산출세액"] == 114_360_000


def test_income_heavy_flag만은_여전히_오류():
    r = _inc(transfer_date="2025-01-01", heavy_multi_home=True, apply_basic_deduction=False)
    assert "error" in r and "houses_count" in r["필요 입력"]


def test_income_2018_4_1_전_3주택은_지원안함():
    r = _inc(acquisition_date="2010-01-01", transfer_date="2017-06-01", houses_count=3, adjusted_area=True)
    assert "error" in r
    r = _inc(acquisition_date="2010-01-01", transfer_date="2017-06-01", houses_count=2, adjusted_area=True)
    assert r["결과"]["장기보유특별공제액"] > 0


def test_income_one_house_true에_중과입력_거부():
    r = _inc(transfer_date="2021-07-01", one_house=True, exempt_met=False, residence_years=0,
             houses_count=2, adjusted_area=True)
    assert "error" in r
