"""건물 기준시가 지수표 연도별(2026-11-24) — 구조·용도·위치지수를 적용연도 고시 표로.
근거: 통합테스트/연도점검_1124 보고_h4(법제처 고시 이미지 대조), 용도지수 2018~2023 원문 전사."""
from tests._helpers import call


def c(**a):
    return call("building_standard_price", {"area_m2": 100, "land_price_per_m2": 10_000, "built_year": 2010, **a})


def test_2021_tables_from_notice_2020_42():
    r = c(year=2021, structure="목구조", use="근린생활시설")["결과"]
    assert (r["구조지수"], r["용도지수"], r["위치지수"], r["근사"]) == (130, 100, 75, False)


def test_use_index_changes_by_year():
    assert c(year=2018, structure="철근콘크리트", use="학원")["결과"]["용도지수"] == 105
    assert c(year=2019, structure="철근콘크리트", use="학원")["결과"]["용도지수"] == 107
    assert c(year=2020, structure="철근콘크리트", use="유흥주점")["결과"]["용도지수"] == 135
    assert c(year=2023, structure="철근콘크리트", use="세차장")["결과"]["용도지수"] == 67


def test_hagwon_not_matched_to_dance_academy():
    # '학원'은 32번 학원·교습소(2026 107) — 18번 무도학원(90)으로 읽던 오류
    assert c(year=2026, structure="철근콘크리트", use="학원")["결과"]["용도지수"] == 107
    assert c(year=2026, structure="철근콘크리트", use="무도학원")["결과"]["용도지수"] == 90


def test_src_structure_not_read_as_rc():
    # '철골철근콘크리트'·'철골콘크리트'는 3번(2026 110) — 4번 철근콘크리트(100)로 읽던 오류
    assert c(year=2026, structure="철골철근콘크리트", use="사무소")["결과"]["구조지수"] == 110
    assert c(year=2026, structure="철골콘크리트조", use="사무소")["결과"]["구조지수"] == 110
    assert c(year=2026, structure="철근콘크리트조", use="사무소")["결과"]["구조지수"] == 100


def test_2017_old_numbering_mapped():
    # 2017년 고시(제2016-21호)는 장례식장이 27번(지수 115) — 2018년 이후 44번
    assert c(year=2017, structure="철근콘크리트", use="장례식장")["결과"]["용도지수"] == 115
    assert c(year=2017, structure="철근콘크리트", use="종합병원")["결과"]["용도지수"] == 125


def test_2024_from_nts_commentary():
    # 2024년 해설서: 2023→2024 용도 변경 20·28·48·57번, 근생 41번은 100(2025년에 95로)
    r = c(year=2024, structure="철근콘크리트", use="근린생활시설")
    assert r["결과"]["용도지수"] == 100 and any("해설" in x["결론"] for x in r["판단"])
    assert c(year=2024, structure="철골조", use="공장")["결과"]["용도지수"] == 78
    assert c(year=2024, structure="철골철근콘크리트", use="사무소")["결과"]["구조지수"] == 110


def test_location_index_by_year():
    assert c(year=2018, structure="철근콘크리트", use="사무소", land_price_per_m2=9_500_000)["결과"]["위치지수"] == 135
    assert c(year=2026, structure="철근콘크리트", use="사무소", land_price_per_m2=9_500_000)["결과"]["위치지수"] == 137


def test_before_2016_residual_floor_20pct():
    r = c(year=2015, structure="철근콘크리트", use="사무소", built_year=1960)["결과"]
    assert r["잔가율"] == 0.2 and r["근사"] is True
