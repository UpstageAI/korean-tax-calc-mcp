"""한국표준산업분류(11차) 데이터·ksic_lookup·후보 도구 입력 검사. 정답은 통계청 고시 제2024-203호 해설서 원문. Claude 작성(2026-11-17)."""
import json

import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine.kr_comparables import candidates as C
from korean_tax_calc_mcp.engine.kr_comparables import ksic as K


def _call(**kw):
    return json.loads(json.dumps(S.ksic_lookup(**kw), ensure_ascii=False, default=str))


def test_counts_match_notice_table():
    """총설 '구·신분류 단계별 분류 항목 수 비교' 합계 행(11차): 대 21·중 77·소 234·세 501·세세 1,205."""
    lv = [sum(1 for it in K.data()["items"] if it["level"] == L) for L in K.LEVELS]
    assert lv == [21, 77, 234, 501, 1205]
    assert K.source()["sha256"] and "2024-203" in K.source()["고시"]


@pytest.mark.parametrize("code,name", [
    ("2042", "세제, 화장품 및 광택제 제조업"), ("20421", "계면활성제 제조업"), ("20422", "치약, 비누 및 기타 세제 제조업"),
    ("20423", "화장품 제조업"), ("46443", "화장품 및 화장용품 도매업"), ("46444", "비누 및 세정제 도매업"),
    ("47813", "화장품, 비누 및 방향제 소매업"), ("204", "기타 화학제품 제조업"), ("C", "제조업"),
    ("46599", "그 외 기타 기계 및 장비 도매업"), ("4644", "의약품, 의료용품 및 화장품 도매업"),
])
def test_names_from_notice(code, name):
    assert K.item(code)["name"] == name


def test_no_english_left_in_names():
    import re
    assert not [it["code"] for it in K.data()["items"] if re.search(r"[A-Za-z]", it["name"])]


def test_v10_links():
    # 구·신 연계표: 10차 10401 → 11차 10411(동물성 유지 제조업), 10차 01152 → 11차 01151
    assert K.from_v10("10401") == ["10411"] and K.from_v10("01152") == ["01151"]
    assert K.from_v10("20423") is None      # 같은 코드는 연계 목록에 없음


def test_lookup_by_name_and_code():
    r = _call(query="화장품")["결과"]
    codes = [x["code"] for x in r["항목"]]
    assert codes[:3] == ["20423", "46443", "47813"] and "46444" not in codes
    r = _call(query="204")["결과"]
    assert r["name"] == "기타 화학제품 제조업" and r["세세분류_수"] == len(r["하위_세세분류"]) == 13
    assert [p["code"] for p in r["상위"]] == ["C", "20"]
    r = _call(query="10401")["결과"]
    assert r["level"] == "10차 코드" and r["11차"][0]["code"] == "10411"
    assert _call(query="99999")["결과"]["찾음"] is False
    assert _call(query="화장품", level="세분류")["결과"]["항목"][0]["code"] == "2042"


def test_tool_registered_and_findable():
    t = {x.name: x for x in S.mcp._tool_manager.list_tools()}["ksic_lookup"]
    assert t.annotations.read_only_hint is True and t.annotations.open_world_hint is False
    assert t.description.splitlines()[0].startswith("Korean Standard Industrial Classification")
    assert any(x["도구"] == "ksic_lookup" for x in S.find_tool(query="업종 코드")["결과"]["후보"])


def test_candidates_reject_unknown_code(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "f" * 40)
    with pytest.raises(ValueError, match="ksic_lookup"):
        C.run(industry_codes=["99999"], years=[2024], client=object())
