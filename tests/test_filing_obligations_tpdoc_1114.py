"""통합·개별기업보고서 제출자와 국제거래명세서 등(Claude 작성 2026-11-14).
조문 확인(국세법령정보시스템 연혁본): 구 국조법 제11조①(2016.1.1.·2019.1.1. 시행본 — 갈음 단서 없음, 2020.1.1. 시행본 — 갈음 단서),
국조법 제16조②(법률 제17651호 2021.1.1. 시행본 — 제출자 제외 괄호·6개월, 부칙: 종전 기한이 지나지 않은 사업연도분에도 적용),
제16조②(법률 제19928호 2024.1.1. 시행본 — 괄호 삭제, 부칙: 시행 전 개시 사업연도분은 종전)."""
import pytest
from _helpers import call as c

E = 100_000_000
BIG = dict(revenue=2000 * E, related_goods=600 * E, party_max_goods=600 * E)


def fo(year, **kw):
    r = c("corporate_filing_obligations", dict(year=year, **kw))
    assert "error" not in r, r
    return r


def J(r):
    return {p["항목"]: p["결론"] for p in r["판단"]}


@pytest.mark.parametrize("year", [2020, 2021, 2022, 2023])
def test_excluded_2020_2023(year):
    r = fo(year, **BIG)
    assert r["결과"]["국제거래정보통합보고서"] is True
    assert r["결과"]["국제거래명세서"] is False and r["결과"]["정상가격산출방법신고서"] is False
    assert r["결과"]["통합보고서_제출자_제외"] is True
    assert "제외" in J(r)["통합·개별기업보고서 제출자"]


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_both_from_2024(year):
    r = fo(year, **BIG)
    assert r["결과"]["국제거래정보통합보고서"] is True and r["결과"]["국제거래명세서"] is True
    assert "별도로" in J(r)["통합·개별기업보고서 제출자"]
    assert "갈음" not in str(r["판단"])
    assert r["결과"]["제출기한"].startswith(f"{year + 1}-06-30")


def test_2019_unverified_and_2018_additional():
    assert "부칙을 확인" in J(fo(2019, **BIG))["통합·개별기업보고서 제출자"]
    r = fo(2018, **BIG)
    assert "추가로 제출" in J(r)["통합·개별기업보고서 제출자"] and r["결과"]["국제거래명세서"] is True
    assert r["결과"]["제출기한"].startswith("2019-03-31")


def test_deadline_small_filer():
    assert fo(2020, related_goods=20 * E)["결과"]["제출기한"].startswith("2021-06-30")
    assert fo(2019, related_goods=20 * E)["결과"]["제출기한"].startswith("2020-03-31")
    assert "제출기한" not in fo(2025, related_goods=1 * E)["결과"]          # 5억 이하 면제
