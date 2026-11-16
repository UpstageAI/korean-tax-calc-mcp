"""nonresident_withholding 0.54.0 — 순액 약정 역산, 근거 조문, 짧은 쟁점 줄(판단은 조문 MCP 안내).

대조한 원문(2026-11-15 조회, as_of 2026-12-31 시행본):
- 법인세법 기본통칙 98-0…2(2024년 고시본): 지급하기로 약정한 금액 ÷ (1 − 원천징수세율) = 과세표준
- 법인세법 제98조제1항제6호(사용료 20%), 제98조의6(2025.12.23. 개정 — 제4항 신설, 경정청구는 제5항), 제98조의7제1항
- 지방세법 제103조의52제1항(외국법인), 제103조의18제1항(비거주자) — 원천징수하는 세액의 10%
- 한미 조세조약 제1조(대상조세 — 소득세·법인세), 제14조(1) 15%·(2) 10%
- 국제조세조정에 관한 법률 시행령 제36조제1호(무형자산거래 1억원 이하)

손으로 계산한 값:
- 순액 1억·15%, 법인세만 부담: 100,000,000 ÷ 0.85 = 117,647,058.82… → 과세표준 117,647,058. 세액 = 17,647,058.82… → 원 단위 17,647,058, 10원 미만 절사 17,647,050
- 지방소득세까지 부담(유추): 100,000,000 ÷ 0.835 = 119,760,479.04… → 119,760,479. 세액 × 0.15 = 17,964,071.85… → 17,964,071 / 17,964,070, 지방 1,796,407 / 1,796,400
- 순액 1억·10%: 111,111,111.11… → 111,111,111, 세액 11,111,111 / 11,111,110
- 순액 1억·국내세율 20%: 125,000,000, 세액 25,000,000, 지방 2,500,000
- 조약이 지방소득세를 포함(일본 10%), 지방소득세까지 부담: 국세분 10%÷1.1, 합계 10% → 111,111,111, 국세 10,101,010(.10…), 지방 1,010,101 → 1,010,100
"""
import json

import pytest

from korean_tax_calc_mcp.engine import calc_income as I
from tests._helpers import call as c

M = 1_000_000
US = {"income_kind": "사용료", "amount": 100 * M, "recipient_type": "법인", "residence_country": "미국"}


# ── 종전 입력의 금액은 그대로 ─────────────────────────────────────────────
@pytest.mark.parametrize("args, tax, local", [
    ({**US, "treaty_rate": 0.15, "year": 2026}, 15 * M, 1_500_000),
    ({**US, "treaty_rate": 0.10}, 10 * M, 1 * M),
    (US, 20 * M, 2 * M),
    ({**US, "treaty_rate": 0.15, "treaty_includes_local_tax": True}, 13_636_360, 1_363_630),
    ({**US, "income_kind": "인적용역", "service_location": "국내"}, 20 * M, 2 * M),
    ({**US, "income_kind": "인적용역", "service_location": "국외"}, 0, 0),
    ({**US, "amount": 119_760_479, "treaty_rate": 0.15}, 17_964_070, 1_796_400),
    ({"income_kind": "사용료", "amount": 55 * M, "recipient_type": "법인", "residence_country": "JP", "treaty_rate": 0.1}, 5 * M, 500_000),
    ({"income_kind": "이자", "amount": 123_456_789, "recipient_type": "개인", "residence_country": "ZZ", "bond_interest": True}, 17_283_950, 1_728_390),
])
def test_existing_amounts_unchanged(args, tax, local):
    g = c("nonresident_withholding", args)["결과"]
    assert (g["원천징수세액"], g["지방소득세"], g["합계"]) == (tax, local, tax + local)
    assert "과세표준" not in g and "역산" not in g


# ── 순액(세금부담) 약정 역산 ───────────────────────────────────────────────
def test_net_of_tax_corporate_tax_only():
    r = c("nonresident_withholding", {**US, "treaty_rate": 0.15, "net_of_tax": True})
    g = r["결과"]
    assert g["약정_순액"] == 100 * M and g["과세표준"] == 117_647_058
    assert g["역산"]["원_단위_세액"] == {"원천징수세액": 17_647_058, "지방소득세": 1_764_705}
    assert (g["원천징수세액"], g["지방소득세"]) == (17_647_050, 1_764_700)
    assert g["역산"]["확신도"].startswith("확인함") and "98-0…2" in g["역산"]["근거"]
    assert "원 미만 버림" in g["역산"]["끝수"]
    assert "98-0…2" in r["근거"]


def test_net_of_tax_with_local_tax_is_marked_inferred():
    r = c("nonresident_withholding", {**US, "treaty_rate": 0.15, "net_of_tax": True, "payer_bears_local_tax": True})
    g = r["결과"]
    assert g["과세표준"] == 119_760_479
    assert g["역산"]["원_단위_세액"] == {"원천징수세액": 17_964_071, "지방소득세": 1_796_407}
    assert (g["원천징수세액"], g["지방소득세"], g["합계"]) == (17_964_070, 1_796_400, 19_760_470)
    assert g["역산"]["확신도"].startswith("유추") and "국이22601-403" in g["역산"]["근거"]
    assert g["역산"]["역산에_쓴_세율"] == pytest.approx(0.165)
    # payer_bears_local_tax만 줘도 순액 약정으로 봄
    g2 = c("nonresident_withholding", {**US, "treaty_rate": 0.15, "payer_bears_local_tax": True})["결과"]
    assert g2["과세표준"] == 119_760_479


@pytest.mark.parametrize("extra, base, tax, local", [
    ({"treaty_rate": 0.10}, 111_111_111, 11_111_110, 1_111_110),       # 10%
    ({}, 125 * M, 25 * M, 2_500_000),                                   # 제한세율 없음 20%
    ({"treaty_rate": 0.25}, 125 * M, 25 * M, 2_500_000),                # 조약세율이 국내세율보다 높으면 국내세율
])
def test_net_of_tax_other_rates(extra, base, tax, local):
    g = c("nonresident_withholding", {**US, **extra, "net_of_tax": True})["결과"]
    assert (g["과세표준"], g["원천징수세액"], g["지방소득세"]) == (base, tax, local)


def test_net_of_tax_treaty_covering_local_tax():
    a = {"income_kind": "사용료", "amount": 100 * M, "recipient_type": "법인", "residence_country": "JP", "treaty_rate": 0.1,
         "net_of_tax": True, "payer_bears_local_tax": True}
    g = c("nonresident_withholding", a)["결과"]
    assert (g["과세표준"], g["원천징수세액"], g["지방소득세"]) == (111_111_111, 10_101_010, 1_010_100)
    # 국세분만 부담: 100,000,000 ÷ (1 − 1/11) = 110,000,000, 국세 10,000,000
    g = c("nonresident_withholding", {**a, "payer_bears_local_tax": False})["결과"]
    assert (g["과세표준"], g["원천징수세액"], g["지방소득세"]) == (110 * M, 10 * M, 1 * M)


def test_net_of_tax_zero_rate_and_zero_amount():
    g = c("nonresident_withholding", {**US, "income_kind": "인적용역", "service_location": "국외", "net_of_tax": True})["결과"]
    assert g["과세표준"] == 100 * M and g["합계"] == 0
    g = c("nonresident_withholding", {**US, "amount": 0, "treaty_rate": 0.15, "net_of_tax": True})["결과"]
    assert g["과세표준"] == 0 and g["합계"] == 0


def test_net_of_tax_one_won_boundary():
    # 순액 85원·15% → 과세표준 정확히 100원, 세액 15원 → 10원(10원 미만 절사). 84원 → 98.82… → 98원
    g = c("nonresident_withholding", {**US, "amount": 85, "treaty_rate": 0.15, "net_of_tax": True})["결과"]
    assert g["과세표준"] == 100 and g["역산"]["원_단위_세액"]["원천징수세액"] == 15 and g["원천징수세액"] == 10
    g = c("nonresident_withholding", {**US, "amount": 84, "treaty_rate": 0.15, "net_of_tax": True})["결과"]
    assert g["과세표준"] == 98 and g["역산"]["원_단위_세액"]["원천징수세액"] == 14


# ── 근거 조문 ──────────────────────────────────────────────────────────────
def test_covered_taxes_article_not_hardcoded():
    r = c("nonresident_withholding", {**US, "treaty_rate": 0.15})
    assert "조약 제2조" not in json.dumps(r, ensure_ascii=False)
    assert "한미 조세조약 제1조(대상조세)" in r["근거"] and "지방세법 제103조의52" in r["근거"]
    assert "제98조의7제1항제1호" in r["결과"]["지방소득세_근거"] and "제103조의52제1항" in r["결과"]["지방소득세_근거"]
    # 표에 없는 나라는 번호 없이, 입력하면 그 번호
    r = c("nonresident_withholding", {**US, "residence_country": "ZZ", "treaty_rate": 0.15, "treaty_includes_local_tax": False})
    assert "조약 제2조" not in json.dumps(r, ensure_ascii=False)
    r = I.nonresident_withholding("사용료", 100 * M, "법인", "미국", 0.15, treaty_covered_taxes_article="제9조")
    assert "조약 제9조(대상조세 — 입력값)" in r["근거"]
    # 조약이 지방소득세를 포함하면 제2호
    r = c("nonresident_withholding", {**US, "residence_country": "JP", "treaty_rate": 0.1})
    assert "제98조의7제1항제2호" in r["결과"]["지방소득세_근거"]


def test_recipient_specific_citations():
    corp = json.dumps(c("nonresident_withholding", {**US, "treaty_rate": 0.15}), ensure_ascii=False)
    assert "제98조의6" in corp and "소득세법 제156조의6" not in corp and "제103조의18" not in corp
    ind = c("nonresident_withholding", {**US, "recipient_type": "개인", "treaty_rate": 0.15})
    s = json.dumps(ind, ensure_ascii=False)
    assert "소득세법 제156조의6" in s and "지방세법 제103조의18제1항" in ind["결과"]["지방소득세_근거"]


# ── 쟁점: 첫 줄은 조문 MCP 안내, 나머지는 한 줄씩 ────────────────────────────
KINDS = ["국내 미등록 특허", "소득 구분·세율", "조약 적용 절차", "납부·신고 기한", "정상가격(이전가격)", "다른 세목", "순액(세금부담) 약정"]


@pytest.mark.parametrize("args", [US, {**US, "treaty_rate": 0.15}, {**US, "income_kind": "배당"}, {**US, "income_kind": "인적용역"},
                                  {**US, "income_kind": "이자", "recipient_type": "개인", "related_party": True}])
def test_first_issue_points_to_law_mcp(args):
    r = c("nonresident_withholding", args)
    first = r["쟁점"][0]
    assert first["구분"] == "안내" and first["쟁점"].startswith("요건·소득구분·조약 적용 판단은 korean-tax-mcp `royalty_withholding_guide`")
    assert "이 도구는 주어진 세율·사실로 금액만 계산" in first["쟁점"] and first["en"].isascii() and "royalty_withholding_guide" in first["en"]
    assert r["한계"][0] == first["쟁점"] and r["한계"][1] == first["en"]


@pytest.mark.parametrize("extra", [{}, {"treaty_rate": 0.15}, {"treaty_rate": 0.15, "net_of_tax": True}, {"recipient_type": "개인"}])
def test_royalty_issue_lines(extra):
    r = c("nonresident_withholding", {**US, **extra})
    own = [it for it in r["쟁점"] if it.get("구분") in KINDS]
    assert [it["구분"] for it in own] == KINDS
    for it in own:
        assert "\n" not in it["쟁점"] and len(it["쟁점"]) <= 260 and it["참고"] and it["확인할 자료"] and "판단" not in it   # 0.59.1: 고정 '전문가 확인 필요' 대신 쟁점별 확인할 자료
    assert "판단_경로" not in r and "판단_경로" not in r["결과"]      # 판단 순서는 조문 MCP에 둠


def test_royalty_issue_contents():
    r = c("nonresident_withholding", {**US, "treaty_rate": 0.15, "year": 2026})
    q = {it.get("구분"): it["쟁점"] for it in r["쟁점"]}
    assert "2021두59908" in q["국내 미등록 특허"] and "royalty_withholding_guide" in q["국내 미등록 특허"]
    assert "income_kind" in q["소득 구분·세율"] and "treaty_withholding_rates" in q["소득 구분·세율"]
    assert "제98조의6제3항" in q["조약 적용 절차"] and "2월 말일" in q["조약 적용 절차"] and "5년" in q["조약 적용 절차"]
    d = q["납부·신고 기한"]
    assert "다음 달 10일" in d and "제120조의2" in d and "withholding_late_payment_penalty" in d and "유추" in d
    e = q["정상가격(이전가격)"]
    assert "arm_length_range" in e and "international_transaction_statement" in e and "제36조" in e
    assert "vat_reverse_charge" in q["다른 세목"] and "관세법 제30조제1항제4호" in q["다른 세목"]
    assert "net_of_tax=True" in q["순액(세금부담) 약정"] and "유추" in q["순액(세금부담) 약정"]


def test_no_treaty_rate_computes_domestic_and_points_to_rate_tool():
    r = c("nonresident_withholding", US)
    assert r["결과"]["적용세율"] == 0.2 and r["결과"]["원천징수세액"] == 20 * M
    p = [it for it in r["쟁점"] if it.get("구분") == "조약 적용 절차"][0]["쟁점"]
    assert p.startswith("treaty_rate가 없어 국내세율로 계산함") and "treaty_withholding_rates" in p
    assert any("treaty_withholding_rates" in x and "국내세율로 계산" in x for x in r["한계"])
    p = [it for it in c("nonresident_withholding", {**US, "treaty_rate": 0.15})["쟁점"] if it.get("구분") == "조약 적용 절차"][0]["쟁점"]
    assert not p.startswith("treaty_rate가 없어")


@pytest.mark.parametrize("amount, word", [(100 * M, "경계값"), (100 * M + 1, "넘음"), (100 * M - 1, "1억원 이하")])
def test_transaction_statement_threshold_boundary(amount, word):
    r = c("nonresident_withholding", {**US, "amount": amount, "treaty_rate": 0.15})
    e = [it for it in r["쟁점"] if it.get("구분") == "정상가격(이전가격)"][0]["쟁점"]
    assert word in e


def test_threshold_uses_grossed_up_base():
    r = c("nonresident_withholding", {**US, "treaty_rate": 0.15, "net_of_tax": True})
    e = [it for it in r["쟁점"] if it.get("구분") == "정상가격(이전가격)"][0]["쟁점"]
    assert "117,647,058원" in e and "넘음" in e and "미확인" in e


def test_other_income_kinds_get_procedure_and_deadline():
    r = c("nonresident_withholding", {**US, "income_kind": "배당", "treaty_rate": 0.1})
    assert [it["구분"] for it in r["쟁점"]] == ["안내", "조약 적용 절차", "납부·신고 기한"]
    assert "98-137…1" in r["쟁점"][2]["쟁점"]
    r = c("nonresident_withholding", {**US, "income_kind": "인적용역"})
    assert any(it.get("구분") == "조약 면제 신청" and "제98조의4" in it["쟁점"] for it in r["쟁점"])
    r = c("nonresident_withholding", {**US, "income_kind": "이자", "net_of_tax": True})
    assert r["쟁점"][-1]["구분"] == "순액(세금부담) 약정" and r["결과"]["과세표준"] == 125 * M


def test_description_has_no_circled_numbers_and_names_new_inputs():
    import asyncio
    from korean_tax_calc_mcp.server import mcp
    t = [x for x in asyncio.run(mcp.list_tools()) if x.name == "nonresident_withholding"][0]
    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
    text = (t.description or "") + json.dumps(schema, ensure_ascii=False)
    assert not any(ch in text for ch in "①②③④⑤⑥⑦⑧⑨")
    for name in ("net_of_tax", "payer_bears_local_tax", "treaty_covered_taxes_article"):
        assert name in t.description and name in schema["properties"]
    first = t.description.splitlines()[0]
    assert first[0].isascii() and "(비거주자 원천징수)" in first and "royalty_withholding_guide" in first
    assert "언제:" in t.description and "입력:" in t.description
