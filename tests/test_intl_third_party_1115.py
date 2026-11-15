"""정상가격 산출방법 신고서 면제 가목 — 국외특수관계 없는 자와의 국제거래 금액(third_party) 입력(2026-11-15, Claude).

원문:
- 사전-2022-법규국조-0527(2022.5.27., 국세법령정보시스템): 「국제조세조정에 관한 법률 시행령」 제36조제2호가목의 '국제거래'에는 국외특수관계 없는 자와의 국제거래도 포함됨
- 시행령 제36조(법제처 시행본): 2021.2.17.(대통령령 제31448호) 제2호 가목 "해당 사업연도의 국제거래 중 전체 재화거래 금액의 합계가 50억원 이하이고 용역거래 금액의 합계가 10억원 이하일 것",
  나목 "국제거래 중 국외특수관계인별 재화거래 … 10억원 이하 … 용역거래 … 2억원 이하". 2023.2.28.(제33272호)부터 제3호 가목 "해당 사업연도의 국제거래 유형별 거래금액의 합계"
  재화 50억·용역 10억·무형자산 10억 이하, 나목 "국외특수관계인과의 국제거래 … 국외특수관계인별로" 10억·2억·2억 이하(부칙 제2조: 2023.1.1. 이후 개시 과세연도)
- 구 시행령 제7조①(2016.2.5.·2020.2.11. 시행본) 제1호 "전체 재화거래 금액의 합계가 50억원 이하이고 용역거래 금액의 합계가 10억원 이하인 경우"
손 계산: 국외특수관계인 재화 30억(한 곳, 나목 10억 초과) + 제3자 재화 20억 = 50억 → '이하'라 면제, 1원 더하면 초과 → 제출.
"""
from tests._helpers import call as c

T = "international_transaction_statement"
억 = 100_000_000


def tp(year, sales, third=None):
    kw = {"year": year, "parties": [{"name": "A", "sales": sales}]}
    if third is not None:
        kw["third_party"] = third
    r = c(T, kw)
    assert "결과" in r, r
    return r


def test_without_input_same_as_before():
    r = tp(2022, {"inventory": 30 * 억})
    assert r["결과"]["정상가격산출방법신고서_제출"] is False            # 국외특수관계인 거래만: 전체 30억 ≤ 50억 → 가목 면제
    assert not any(j["항목"] == "정상가격산출방법신고서 가목 금액" for j in r["판단"])
    assert any("third_party를 넣지 않아" in j["결론"] for j in r["판단"])
    assert tp(2022, {"inventory": 30 * 억}, {})["결과"] == r["결과"]     # 빈 입력도 같음


def test_goods_boundary_50_billion():
    at = tp(2022, {"inventory": 30 * 억}, {"goods": 20 * 억})              # 30억 + 20억 = 50억 '이하' → 면제
    assert at["결과"]["정상가격산출방법신고서_제출"] is False
    over = tp(2022, {"inventory": 30 * 억}, {"goods": 20 * 억 + 1})         # 50억 1원 → 가목 초과, 나목(국외특수관계인별 10억)도 초과 → 제출
    assert over["결과"]["정상가격산출방법신고서_제출"] is True
    j = next(j for j in over["판단"] if j["항목"] == "정상가격산출방법신고서 가목 금액")
    assert "재화 5,000,000,001원" in j["결론"] and "사전-2022-법규국조-0527" in j["근거"]
    # 나목(국외특수관계인별 재화 10억·용역 2억 이하)에 해당하면 제3자 거래가 커도 면제 — 나목은 국외특수관계인 거래만
    small = tp(2022, {"inventory": 10 * 억}, {"goods": 100 * 억})
    assert small["결과"]["정상가격산출방법신고서_제출"] is False


def test_services_boundary_1_billion():
    assert tp(2022, {"other_services": 3 * 억}, {"services": 7 * 억})["결과"]["정상가격산출방법신고서_제출"] is False      # 3억 + 7억 = 10억
    assert tp(2022, {"other_services": 3 * 억}, {"services": 7 * 억 + 1})["결과"]["정상가격산출방법신고서_제출"] is True    # 나목 용역 2억도 초과


def test_intangibles_only_from_2023():
    # 2022년까지는 무형자산 금액 기준이 없음(영 제36조제2호) — third_party.intangibles를 넣어도 그대로
    r22 = tp(2022, {"inventory": 30 * 억}, {"intangibles": 100 * 억})
    assert r22["결과"]["정상가격산출방법신고서_제출"] is False
    # 2023년부터 무형자산 10억(영 제36조제3호가목3)): 국외특수관계인 3억(나목 2억 초과) + 제3자 7억 = 10억 → 면제, 1원 더하면 제출
    assert tp(2023, {"royalty": 3 * 억}, {"intangibles": 7 * 억})["결과"]["정상가격산출방법신고서_제출"] is False
    assert tp(2023, {"royalty": 3 * 억}, {"intangibles": 7 * 억 + 1})["결과"]["정상가격산출방법신고서_제출"] is True


def test_old_years_and_other_reports_unchanged():
    # 구 시행령 제7조①1호(2016~2020)도 '전체 재화거래 금액' — 같은 방식
    assert tp(2018, {"inventory": 30 * 억}, {"goods": 20 * 억})["결과"]["정상가격산출방법신고서_제출"] is False
    assert tp(2018, {"inventory": 30 * 억}, {"goods": 20 * 억 + 1})["결과"]["정상가격산출방법신고서_제출"] is True
    # 국제거래명세서·요약손익계산서 면제는 '국외특수관계인과의' 거래라 더하지 않음
    a, b = tp(2023, {"inventory": 4 * 억})["결과"], tp(2023, {"inventory": 4 * 억}, {"goods": 100 * 억})["결과"]
    assert (a["국제거래명세서_제출"], a["요약손익계산서_제출"]) == (b["국제거래명세서_제출"], b["요약손익계산서_제출"]) == (False, False)


def test_same_as_corporate_filing_obligations_and_errors():
    o = c("corporate_filing_obligations", {"year": 2022, "related_goods": 30 * 억, "party_max_goods": 30 * 억, "third_party_goods": 20 * 억 + 1})["결과"]
    assert o["정상가격산출방법신고서"] is True and o["정상가격신고서_가목_전체금액"] == {"재화": 50 * 억 + 1, "용역": 0}
    assert c("corporate_filing_obligations", {"year": 2022, "related_goods": 30 * 억, "party_max_goods": 30 * 억, "third_party_goods": 20 * 억})["결과"]["정상가격산출방법신고서"] is False
    bad = c(T, {"year": 2022, "parties": [{"name": "A", "sales": {"inventory": 1}}], "third_party": {"goods": -1}})
    assert "error" in bad and any("third_party.goods" in m for m in bad["문제"])
    bad = c(T, {"year": 2022, "parties": [{"name": "A", "sales": {"inventory": 1}}], "third_party": {"capital": 1}})
    assert "error" in bad
