"""자녀세액공제(소득세법 제59조의2) 귀속연도별 회귀 테스트 — 값은 각 연도 조문·부칙에서 손으로 계산."""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp


def c(a):
    r = asyncio.run(mcp.call_tool("child_tax_credit", a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def ok(a):
    r = c(a)
    assert "error" not in r, r
    return r["결과"]


def rejected(a):
    try:
        r = c(a)
    except Exception:
        return True
    return isinstance(r, dict) and "error" in r


K = lambda age, **kw: {"age": age, "basic_deduction": True, **kw}


def test_2016_three_children_two_under6_and_birth():
    # 2016: ① 3명 30만+30만=60만, ② 6세 이하 2명 → 15만, ③ 출생 1명당 30만(2015.5.13 개정)
    r = ok({"year": 2016, "children": [K(10), K(3), K(0, born_or_adopted_this_year=True)]})
    assert (r["기본분_①"], r["6세이하_추가_②"], r["출산입양_③"]) == (600_000, 150_000, 300_000)
    assert r["자녀세액공제"] == 1_050_000


def test_2017_birth_by_order():
    # 2017: ③ 둘째 50만(2016.12.20 개정), ① 2명 30만, ② 6세 이하 2명 → 15만
    r = ok({"year": 2017, "children": [K(4), K(0, born_or_adopted_this_year=True, order="둘째")]})
    assert r["자녀세액공제"] == 300_000 + 150_000 + 500_000


def test_2018_under6_extra_deleted():
    # 2018: ② 삭제(2017.12.19, 2018.1.1 시행), 연령 요건 아직 없음
    r = ok({"year": 2018, "children": [K(4), K(2)]})
    assert (r["기본분_①"], r["6세이하_추가_②"]) == (300_000, 0)


def test_2019_age7_and_school_child():
    # 2019: 7세 이상 + 7세 미만 취학아동 포함(2018.12.31 개정)
    r = ok({"year": 2019, "children": [K(9), K(6, school_enrolled=True), K(3)]})
    assert r["①대상_인원"] == 2 and r["기본분_①"] == 300_000


def test_2019_age6_requires_school_flag():
    r = c({"year": 2019, "children": [K(6)]})
    assert "입력 확인 필요" in r["error"]


def test_2020_school_clause_removed():
    r = ok({"year": 2020, "children": [K(7), K(6, school_enrolled=True)]})
    assert r["①대상_인원"] == 1 and r["기본분_①"] == 150_000


def test_2022_vs_2023_age_threshold():
    # 2023: 8세 이상(2022.12.31 개정, 부칙 제16조)
    kids = [K(7), K(9), K(12)]
    assert ok({"year": 2022, "children": kids})["기본분_①"] == 600_000   # 3명: 30만+30만
    assert ok({"year": 2023, "children": kids})["기본분_①"] == 300_000   # 2명


def test_2024_amounts_and_grandchild():
    # 2024: 2명 35만, 3명 35만+30만=65만, 손자녀 포함(2023.12.31 개정)
    r = ok({"year": 2024, "children": [K(8), K(10), K(9, relation="손자녀")]})
    assert r["기본분_①"] == 650_000


def test_2025_amounts():
    # 2025: 1명 25만·2명 55만·3명 55만+40만(2024.12.31 개정, 부칙 제7조)
    assert ok({"year": 2025, "children": [K(8)]})["기본분_①"] == 250_000
    assert ok({"year": 2025, "children": [K(8), K(9)]})["기본분_①"] == 550_000
    assert ok({"year": 2025, "children": [K(8), K(9), K(15), K(17)]})["기본분_①"] == 1_350_000


def test_2026_age_transition_and_2017_born():
    # 2026: 부칙(2026.4.21) 제2조②1호 9세 이상, 단 제2조③ 2017년생(2026년 9세)은 본문 13세 이상 → 제외
    r = ok({"year": 2026, "children": [K(9), K(10), {"birth_date": "2014-05-01", "basic_deduction": True}]})
    assert r["①대상_인원"] == 2 and r["기본분_①"] == 550_000


def test_birth_credit_third_and_grandchild_excluded():
    r = ok({"year": 2025, "children": [K(0, born_or_adopted_this_year=True, order=3),
                                       K(0, relation="손자녀", born_or_adopted_this_year=True)]})
    assert r["출산입양_③"] == 700_000 and r["기본분_①"] == 0


def test_birth_requires_order_from_2017():
    assert "입력 확인 필요" in c({"year": 2021, "children": [K(0, born_or_adopted_this_year=True)]})["error"]
    assert ok({"year": 2016, "children": [K(0, born_or_adopted_this_year=True)]})["출산입양_③"] == 300_000


def test_2023_grandchild_needs_settlement_date():
    # 2023.12.31 부칙 제3조①: 손자녀는 2024.1.1 이후 신고·결정·연말정산분부터
    kids = [K(10), K(9, relation="손자녀")]
    assert "입력 확인 필요" in c({"year": 2023, "children": kids})["error"]
    assert ok({"year": 2023, "children": kids, "settlement_date": "2024-02-15"})["기본분_①"] == 300_000
    assert ok({"year": 2023, "children": kids, "settlement_date": "2023-11-30"})["기본분_①"] == 150_000
    assert "입력 확인 필요" in c({"year": 2021, "children": kids, "settlement_date": "2024-05-31"})["error"]


def test_not_basic_dependent_excluded_and_bad_inputs():
    r = ok({"year": 2025, "children": [K(10), {"age": 12, "basic_deduction": False}]})
    assert r["기본분_①"] == 250_000
    assert rejected({"year": 2025, "children": [{"age": 10}]})
    assert rejected({"year": 2025, "children": [{"age": 10, "basic_deduction": True, "relation": "형제자매"}]})
    assert rejected({"year": 2025, "children": [{"age": 10, "birth_year": 2010, "basic_deduction": True}]})
    assert rejected({"year": 2025, "children": [K(10, foo=1)]})
    assert rejected({"year": 2015, "children": [K(10)]})


def test_find_tool_alias():
    r = asyncio.run(mcp.call_tool("find_tool", {"query": "자녀세액공제 얼마"}))
    t = json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)
    assert t["결과"]["후보"][0]["도구"] == "child_tax_credit"
