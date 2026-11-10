"""비영리내국법인 고유목적사업준비금 손금산입 한도 nonprofit_reserve_limit — 정답 테스트(수정 금지, Claude 작성 2026-11-10).
근거(2026.7.1 시행본): 법인세법 제29조제1항 1호(이자·배당·복지융자이자)·2호(그 밖의 수익사업 소득 50%, 공익법인 장학 80%)·결손 차감 괄호,
제29조제5항제4호·제7항(5년 미사용 익금산입·이자상당액), 제62조(이자소득 분리과세 선택), 조세특례제한법 제74조제1항(학교법인 등 100%, 2028.12.31 이전 사업연도).
공개 검증 사례: 2026-11-10 트렌드 시나리오 S2(가상 사단법인) 손계산.
"""
from _helpers import call as c

M = 1_000_000
S2 = {"year": 2026, "interest_income": 50 * M, "dividend_income": 20 * M, "other_income": 100 * M, "reserve_booked": 160 * M}


def test_s2_general_nonprofit_limit_and_excess():
    r = c("nonprofit_reserve_limit", S2)
    assert "error" not in r, r
    g = r["결과"]
    assert g["이자배당등_합계"] == 70 * M and g["적용률"] == 0.5 and g["기타분_한도"] == 50 * M
    assert g["한도"] == 120 * M and g["손금산입액"] == 120 * M and g["한도초과액"] == 40 * M
    assert "제29조제1항" in r["근거"]
    assert any("5년" in str(j) for j in r["판단"])


def test_loss_in_other_business_reduces_limit():
    g = c("nonprofit_reserve_limit", {**S2, "other_income": -30 * M, "reserve_booked": 100 * M})["결과"]
    assert g["기타분_한도"] == 0 and g["한도"] == 40 * M and g["한도초과액"] == 60 * M


def test_loss_bigger_than_interest_floors_at_zero():
    g = c("nonprofit_reserve_limit", {**S2, "other_income": -100 * M, "reserve_booked": 10 * M})["결과"]
    assert g["한도"] == 0 and g["손금산입액"] == 0 and g["한도초과액"] == 10 * M


def test_public_interest_scholarship_80pct():
    g = c("nonprofit_reserve_limit", {**S2, "entity": "공익법인_장학"})["결과"]
    assert g["적용률"] == 0.8 and g["한도"] == 150 * M and g["한도초과액"] == 10 * M


def test_special_act_74_100pct_until_2028():
    r = c("nonprofit_reserve_limit", {**S2, "entity": "조특법74"})
    assert r["결과"]["적용률"] == 1.0 and r["결과"]["한도"] == 170 * M and r["결과"]["한도초과액"] == 0
    assert "제74조" in r["근거"]
    r29 = c("nonprofit_reserve_limit", {**S2, "year": 2029, "entity": "조특법74"})
    assert r29["결과"]["적용률"] == 0.5 and any("2028" in str(x) for x in r29.get("주의", []) + r29.get("판단", []))


def test_booked_within_limit():
    g = c("nonprofit_reserve_limit", {**S2, "reserve_booked": 90 * M})["결과"]
    assert g["손금산입액"] == 90 * M and g["한도초과액"] == 0


def test_interest_separate_tax_excludes_interest():
    r = c("nonprofit_reserve_limit", {**S2, "interest_separate_tax": True})
    assert r["결과"]["이자배당등_합계"] == 20 * M and r["결과"]["한도"] == 70 * M
    assert any("제62조" in str(j) for j in r["판단"])


def test_welfare_loan_interest_counts_in_item1():
    g = c("nonprofit_reserve_limit", {**S2, "welfare_loan_interest": 5 * M})["결과"]
    assert g["이자배당등_합계"] == 75 * M and g["한도"] == 125 * M


def test_errors():
    assert "error" in c("nonprofit_reserve_limit", {**S2, "interest_income": -1})
    assert "error" in c("nonprofit_reserve_limit", {**S2, "reserve_booked": -1})
    r = c("nonprofit_reserve_limit", {**S2, "entity": "학교"})
    assert "error" in r and "허용값" in r


def test_find_tool_surfaces_tool():
    r = c("find_tool", {"query": "비영리법인 고유목적사업준비금 손금산입 한도", "n": 3})
    assert "nonprofit_reserve_limit" in [x["도구"] for x in r["결과"]["후보"]], r
