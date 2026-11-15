"""근거 조문 인용의 영문 표기(citation_en) — 표 기반 단위 테스트.

법령명 표(data/law_names_ko_en.json)는 법제처 영문법령 목록 검색(2026-11-15)의 영문 제명이다.
조문 번호 표기는 법제처 영문법령의 인용 꼴('Article 98 (1) 6', 'Article 94 (1) 3 (c)', 'proviso', 'latter part',
'with the exception of the subparagraphs', 'Addenda', 'Act No.')을 줄인 것이다.
"""
import json
from pathlib import Path

import pytest

from korean_tax_calc_mcp.citation_en import Citer, cite_en, convert_articles, law_name_en, law_table, unconfirmed_laws

# ── 조문 번호(법령명 없음) ─────────────────────────────────────────────────
ARTICLES = [
    ("제98조", "Art. 98"),
    ("제98조①6호", "Art. 98(1)6"),
    ("제98조제1항제6호", "Art. 98(1)6"),
    ("제98조의7제1항제1호", "Art. 98-7(1)1"),
    ("제98조의7①1호", "Art. 98-7(1)1"),
    ("제47조의5①", "Art. 47-5(1)"),
    ("제27조의4", "Art. 27-4"),
    ("제103조의52제1항", "Art. 103-52(1)"),
    ("제94조제1항제3호다목", "Art. 94(1)3(c)"),
    ("제2조제1항제3호의2", "Art. 2(1)3-2"),
    ("제44조제7의2호", "Art. 44 subpara. 7-2"),
    ("제93조6호", "Art. 93 subpara. 6"),
    ("제19조 제3호", "Art. 19 subpara. 3"),
    ("제104조의5 제3항", "Art. 104-5(3)"),
    ("제136조④⑤", "Art. 136(4)(5)"),
    ("제19조의2⑥9호", "Art. 19-2(6)9"),
    ("§60의2①1호", "Art. 60-2(1)1"),
    ("§42의2⑥", "Art. 42-2(6)"),
    ("제98조의6제3항·제4항·제5항", "Art. 98-6(3)·(4)·(5)"),
    ("제16조의2제4항~제7항", "Art. 16-2(4)~(7)"),
    ("제75조·제76조", "Art. 75·Art. 76"),
    ("제46조~제50조", "Art. 46~Art. 50"),
    ("제45조·제45조의3", "Art. 45·Art. 45-3"),
    ("제1조 단서", "Art. 1, proviso"),
    ("제60조② 후문", "Art. 60(2), latter part"),
    ("제4조제1항 전단", "Art. 4(1), former part"),
    ("제10조④ 후단", "Art. 10(4), latter part"),
    ("제3조제1항 본문", "Art. 3(1), main clause"),
    ("제47조의5제1항 각 호 외의 부분", "Art. 47-5(1), with the exception of the subparagraphs"),
    ("제5항", "para. (5)"),
    ("제3항제1호", "para. (3)1"),
    ("제2항제1호가목", "para. (2)1(a)"),
    ("제1호", "subpara. 1"),
    ("1호·2호", "subpara. 1·2"),
    ("나목", "item (b)"),
    ("별표 3", "Table 3"),
    ("[별표]", "Table"),
    ("별표 1의2", "Table 1-2"),
    ("부칙 제1조", "Addenda Art. 1"),
    ("부칙§9", "Addenda Art. 9"),
    ("법률 제21212호", "Act No. 21212"),
    ("대통령령 제31448호 부칙 제17조", "Presidential Decree No. 31448 Addenda Art. 17"),
    ("법률 제21212호 부칙 제1조 단서·제4조", "Act No. 21212 Addenda Art. 1, proviso·Art. 4"),
    ("시행령 제27조의4", "Enforcement Decree Art. 27-4"),
    ("시행규칙 제43조", "Enforcement Rule Art. 43"),
    ("구 시행령 제6조제7항", "former Enforcement Decree Art. 6(7)"),
    ("같은 법 시행령 제98조제1항", "Enforcement Decree of the same Act Art. 98(1)"),
    ("법 제42조①", "Act Art. 42(1)"),
    ("영 제53조제3항", "Decree Art. 53(3)"),
    ("기본통칙 4-0…2", "Basic Rulings 4-0…2"),
]


@pytest.mark.parametrize("ko,en", ARTICLES)
def test_article_numbers(ko, en):
    assert convert_articles(ko) == en


# ── 그대로 두는 것(조문의 호가 아닌 '호', 서식 번호, 숫자) ─────────────────────
UNCHANGED = ["별지 제15호서식", "별지 제15호 서식", "기획재정부령 제123호", "국세청고시 2025-8", "98-0…2", "2026.7.1. 시행", "1,000,000원", "과목", "항목",
             "3호선", "국이22601-403"]


@pytest.mark.parametrize("ko", UNCHANGED)
def test_not_a_citation_is_left_alone(ko):
    assert convert_articles(ko) == ko


# ── 법령명 + 조문 ──────────────────────────────────────────────────────────
LAWS = [
    ("법인세법 제98조①6호", "Corporate Tax Act (법인세법) Art. 98(1)6"),
    ("소득세법 제94조제1항제3호다목", "Income Tax Act (소득세법) Art. 94(1)3(c)"),
    ("부가가치세법 제52조제1항", "Value-Added Tax Act (부가가치세법) Art. 52(1)"),
    ("국세기본법 제47조의5①", "Framework Act on National Taxes (국세기본법) Art. 47-5(1)"),
    ("국세기본법 시행령 제27조의4", "Enforcement Decree of the Framework Act on National Taxes (국세기본법 시행령) Art. 27-4"),
    ("지방세법 제103조의52①", "Local Tax Act (지방세법) Art. 103-52(1)"),
    ("지방세기본법 제71조", "Framework Act on Local Taxes (지방세기본법) Art. 71"),
    ("조세특례제한법 제136조⑥", "Act on Restriction on Special Cases Concerning Taxation (조세특례제한법) Art. 136(6)"),
    ("국제조세조정에 관한 법률 제7조", "Adjustment of International Taxes Act (국제조세조정에 관한 법률) Art. 7"),
    ("국제조세조정에 관한 법률 시행령 제36조제1호", "Enforcement Decree of the Adjustment of International Taxes Act (국제조세조정에 관한 법률 시행령) Art. 36 subpara. 1"),
    ("상속세 및 증여세법 제67조", "Inheritance Tax and Gift Tax Act (상속세 및 증여세법) Art. 67"),
    ("국고금 관리법 제47조제1항", "Management of the National Funds Act (국고금 관리법) Art. 47(1)"),
    ("조세범 처벌법 제3조", "Punishment of Tax Offenses Act (조세범 처벌법) Art. 3"),
    ("조세범 처벌절차법 제15조①1호", "Procedure for the Punishment of Tax Offenses Act (조세범 처벌절차법) Art. 15(1)1"),
    ("중소기업기본법 시행령 별표 1", "Enforcement Decree of the Framework Act on Small and Medium Enterprises (중소기업기본법 시행령) Table 1"),
    ("법인세법 기본통칙 98-0…2", "Corporate Tax Act Basic Rulings (법인세법 기본통칙) 98-0…2"),
    ("구 법인세법 제121조의2①", "former Corporate Tax Act (구 법인세법) Art. 121-2(1)"),
    ("법법§60의2①1호", "Corporate Tax Act (법법) Art. 60-2(1)1"),
    ("조특법 제136조④⑤", "Act on Restriction on Special Cases Concerning Taxation (조특법) Art. 136(4)(5)"),
    ("부가령 제42조제1호", "Enforcement Decree of the Value-Added Tax Act (부가령) Art. 42 subpara. 1"),
    ("민법 제161조", "Civil Act (민법) Art. 161"),
    ("관세법 제30조제1항제4호", "Customs Act (관세법) Art. 30(1)4"),
]


@pytest.mark.parametrize("ko,en", LAWS)
def test_law_name_and_article(ko, en):
    c = Citer()
    assert c.convert(ko) == en
    assert c.missing == []


def test_korean_gloss_only_on_first_mention_in_a_cell():
    out = cite_en("법인세법 제98조①6호 · 법인세법 제98조의7①1호 · 지방세법 제103조의52①")
    assert out == "Corporate Tax Act (법인세법) Art. 98(1)6 · Corporate Tax Act Art. 98-7(1)1 · Local Tax Act (지방세법) Art. 103-52(1)"
    assert cite_en("법인세법 제98조").startswith("Corporate Tax Act (법인세법)")      # 다른 칸에서는 다시 병기


def test_generic_decree_after_a_named_law():
    out = cite_en("국제조세조정에 관한 법률 제7조 · 시행령 제36조제1호")
    assert out == "Adjustment of International Taxes Act (국제조세조정에 관한 법률) Art. 7 · Enforcement Decree Art. 36 subpara. 1"


@pytest.mark.parametrize("ko,kept", [("법인세법 시행규칙 제75조", "법인세법 시행규칙"), ("소득세법 시행규칙 제23조제1항", "소득세법 시행규칙"),
                                      ("지방세기본법 시행령 제1조", "지방세기본법 시행령"), ("주택법 시행규칙 제3조", "주택법 시행규칙")])
def test_law_with_no_official_english_title_stays_korean(ko, kept):
    """영문본이 없는 법령은 이름을 지어내지 않는다 — 국문 그대로 두고 missing에 올린다(조문 번호만 영문)."""
    c = Citer()
    out = c.convert(ko)
    assert out.startswith(kept + " Art. ")
    assert "Enforcement" not in out
    assert c.missing == [kept]


def test_law_name_inside_a_word_or_without_a_citation_is_left_alone():
    assert cite_en("법인세법상 내국법인") == "법인세법상 내국법인"
    c = Citer(phrases=False)
    assert c.convert("종합소득세법 제1조") == "종합소득세법 Art. 1"       # 낱말 중간의 '소득세법'은 법령명으로 보지 않는다


def test_non_korean_text_is_returned_as_is():
    for s in ("", "Royalty statements", "15% × 1.1", None, 12):
        assert cite_en(s) == s


# ── 구절: 용어집에 통째로 있는 것만 ──────────────────────────────────────────
def test_phrases_only_from_glossary_and_missing_reported():
    c = Citer()
    out = c.convert("법인세법 제98조①6호 · 조세조약 제한세율 15% · 이 구절은 용어집에 없음")
    assert out.startswith("Corporate Tax Act (법인세법) Art. 98(1)6 · ")
    assert "15%" in out and "조세조약 제한세율" not in out
    assert out.endswith(" · 이 구절은 용어집에 없음")
    assert c.missing == ["이 구절은 용어집에 없음"]


def test_number_slot_keeps_the_number():
    a, b = cite_en("조세조약 제한세율 15%"), cite_en("조세조약 제한세율 12.5%")
    assert a.replace("15%", "{n}%") == b.replace("12.5%", "{n}%")
    assert "가" not in a and "15%" in a and "12.5%" in b


def test_custom_labels_take_precedence_and_are_marked_used():
    from korean_tax_calc_mcp.workbook_i18n import Labels
    own = Labels({"이 구절은 용어집에 없음": "Not in the glossary"}, en=True)
    c = Citer(own)
    assert c.convert("법인세법 제98조 · 이 구절은 용어집에 없음") == "Corporate Tax Act (법인세법) Art. 98 · Not in the glossary"
    assert c.missing == [] and own.used == {"이 구절은 용어집에 없음"}


def test_ruling_numbers_are_not_reported_as_missing():
    c = Citer()
    assert c.convert("국이22601-403") == "국이22601-403"
    assert c.missing == []


def test_shared_missing_list():
    seen: list[str] = []
    Citer(missing=seen).convert("법인세법 제1조(용어집에 없는 말)")
    assert seen == ["용어집에 없는 말"]


# ── 법령명 표 ─────────────────────────────────────────────────────────────
def test_law_table_rows_and_source():
    data = json.loads((Path(__file__).parent.parent / "korean_tax_calc_mcp" / "data" / "law_names_ko_en.json").read_text(encoding="utf-8"))
    assert "법제처 영문법령" in data["source"]
    assert len(data["laws"]) >= 50
    for row in data["laws"]:
        assert row["ko"] and row["en"] and row["elaw_effective"].isdigit() and len(row["elaw_effective"]) == 8, row
        assert row["en"] == row["en"].strip() and not any("가" <= ch <= "힣" for ch in row["en"]), row
        if row["ko"].endswith(" 시행령"):
            assert row["en"].startswith("Enforcement Decree of the "), row
    assert law_name_en("법인세법") == "Corporate Tax Act" and law_name_en("법법") == "Corporate Tax Act"
    assert law_name_en("법인세법 시행규칙") is None
    assert "법인세법 시행규칙" in unconfirmed_laws() and not set(unconfirmed_laws()) & set(law_table())
