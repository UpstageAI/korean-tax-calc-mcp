"""vocab.resolve(name, year=…) — year를 넘기면 NameError(_year_key 미정의)가 나던 잠복 결함 고정. 작성 Claude

경계 근거: 법인세법 제25조 제목이 2023.12.31 시행본 "접대비의 손금불산입" → 2024.1.1 시행본
"기업업무추진비의 손금불산입"(2022.12.31 개정, 2024.1.1 시행). facts_vocab.json의 별칭
'접대비_증빙없음'은 20160101~20231231로 등록돼 있어 2023년까지는 별칭, 2024년부터는 안내가 나와야 한다.
"""

from korean_tax_calc_mcp import vocab

LAST_YEAR_OLD_NAME = 2023   # 접대비(옛 이름) 마지막 해
FIRST_YEAR_NEW_NAME = 2024  # 기업업무추진비 첫 해


def test_resolve_canonical_with_year_filters_aliases():
    r = vocab.resolve("기업업무추진비_증빙없음", year=LAST_YEAR_OLD_NAME)
    assert r["이름"] == "기업업무추진비_증빙없음"
    assert "접대비_증빙없음" in r["별칭"]
    r = vocab.resolve("기업업무추진비_증빙없음", year=FIRST_YEAR_NEW_NAME)
    assert r["이름"] == "기업업무추진비_증빙없음"
    assert "접대비_증빙없음" not in r.get("별칭", [])


def test_resolve_alias_with_year_out_of_range_gives_guide():
    r = vocab.resolve("접대비_증빙없음", year=LAST_YEAR_OLD_NAME)
    assert r["이름"] == "기업업무추진비_증빙없음"
    assert "안내" not in r
    r = vocab.resolve("접대비_증빙없음", year=FIRST_YEAR_NEW_NAME)
    assert r["이름"] == "기업업무추진비_증빙없음"
    assert "안내" in r


def test_resolve_every_item_with_year_does_not_raise():
    data = vocab.load()
    for item in data["항목"]:
        vocab.resolve(item["이름"], year=2024)
        for alias, _f, _t in item.get("별칭", []):
            vocab.resolve(alias, year=2024)
