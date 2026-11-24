"""신고서 사전검토(법인) 규칙 연도표(2026-11-24) — 2025 사업연도 값으로 모든 연도를 판정하던 7개 규칙.
근거 원문: 통합테스트/연도점검_1124/보고_h1.md(조문 MCP 0.30.0 law_article as_of 대조)."""
from tests._helpers import call_raw


def _rules(data):
    r = call_raw("return_precheck", {"tax": "법인", "data": data})
    out = {}
    for bucket in ("오류 의심", "이상 없음", "자료 부족"):
        for x in r.get(bucket, []):
            out[x["규칙"]] = (bucket, x)
    return out


def _fy(y):
    return {"기본.개시일": f"{y}-01-01", "기본.종료일": f"{y}-12-31"}


# A6-6·A10-1: 특정법인 임대·이자·배당 비율 2017~2021 개시 70%, 2022~ 50%
def _special(y, ratio):
    return {**_fy(y), "기업업무추진비.지배주주지분율": 0.6, "기업업무추진비.임대이자배당비율": ratio,
            "기업업무추진비.상시근로자수": 3, "기업업무추진비.부동산임대법인": False}


def test_special_corp_ratio_70_before_2022():
    assert _rules(_special(2019, 0.6))["A6-6"][0] == "이상 없음"
    assert _rules(_special(2019, 0.75))["A6-6"][0] == "오류 의심"


def test_special_corp_ratio_50_from_2022():
    assert _rules(_special(2023, 0.6))["A6-6"][0] == "오류 의심"


def test_special_corp_ratio_before_2017_stops():
    assert _rules(_special(2016, 0.6))["A6-6"][0] == "자료 부족"


def test_sincere_target_uses_year_ratio():
    d = {**_fy(2019), "성실신고.지배주주지분율": 0.6, "성실신고.임대이자배당비율": 0.6, "성실신고.상시근로자수": 3, "성실신고.대상신고": False}
    assert _rules(d)["A10-1"][0] == "이상 없음"


# A9-2: 2020.12.31. 이전 양도 주택·별장 10%, 입주권·분양권 과세대상 아님
def _land(y, kind, rate, when=None):
    a = {"유형": kind, "적용세율": rate, "취득일": "2015-05-01", "양도금액": 5 * 10**8, "장부가액": 3 * 10**8}
    if when: a["양도일"] = when
    return {**_fy(y), "토지등.자산": [a]}


def test_land_house_10pct_before_2021():
    assert _rules(_land(2020, "주택", 0.10))["A9-2"][0] == "이상 없음"
    assert _rules(_land(2021, "주택", 0.10))["A9-2"][0] == "오류 의심"


def test_land_presale_right_not_taxable_before_2021():
    assert _rules(_land(2020, "분양권", 0.20, "2020-06-01"))["A9-2"][0] == "오류 의심"
    assert _rules(_land(2021, "분양권", 0.20, "2021-06-01"))["A9-2"][0] == "이상 없음"


# A15-4: R&D 공제율
def _rd(y, method, group, kind, rate, ratio=None):
    d = {**_fy(y), "RD.방식": method, "RD.구분": group, "RD.유형": kind, "RD.적용공제율": rate}
    if ratio is not None: d["RD.수입금액대비비율"] = ratio
    return d


def test_rd_general_current_2016_cap_3pct():
    assert _rules(_rd(2016, "당기분", "일반", "일반", 0.03, 0.02))["A15-4"][0] == "이상 없음"
    assert _rules(_rd(2016, "당기분", "일반", "일반", 0.035, 0.02))["A15-4"][0] == "오류 의심"


def test_rd_graduate_rates_before_2025():
    assert _rules(_rd(2024, "당기분", "유예1~3", "일반", 0.18))["A15-4"][0] == "오류 의심"
    assert _rules(_rd(2025, "당기분", "유예1~3", "일반", 0.18))["A15-4"][0] == "이상 없음"


def test_rd_special_kinds_before_2025_stop():
    assert _rules(_rd(2023, "당기분", "중소", "신성장", 0.30))["A15-4"][0] == "자료 부족"


# A18-5: 통합투자 2024 개시분까지는 연도표 없음 → 자료 부족(2025 값으로 판정하지 않음)
def _inv(y, rate):
    return {**_fy(y), "투자.규모": "중견", "투자.자산유형": "일반", "투자.적용공제율": rate, "투자.당기투자액": 10**9,
            "투자.직전3년평균": 5 * 10**8, "투자.증가분공제액": 0}


def test_investment_before_2025_stops():
    assert _rules(_inv(2022, 0.05))["A18-5"][0] == "자료 부족"
    assert _rules(_inv(2025, 0.05))["A18-5"][0] == "이상 없음"


# A14-4: 청년 창업 100%는 2018.5.29. 이후 창업분, 2026 창업은 4단계(표 없음)
def _startup(founded, kind, rate):
    return {**_fy(2019), "창업감면.감면연차": 2, "창업감면.유형": kind, "창업감면.기본감면율": rate, "창업감면.창업일": founded}


def test_youth_startup_100_only_from_2018_05_29():
    assert _rules(_startup("2017-03-01", "청년생계형과밀외", 1.0))["A14-4"][0] == "오류 의심"
    assert _rules(_startup("2018-06-01", "청년생계형과밀외", 1.0))["A14-4"][0] == "이상 없음"


def test_startup_from_2026_stops():
    assert _rules(_startup("2026-02-01", "기타", 0.5))["A14-4"][0] == "자료 부족"


# A13-4·A13-6: 중소기업 특별세액감면
def test_sme_midsize_capital_area_before_2021_stops():
    d = {**_fy(2020), "중기감면.규모": "중기업", "중기감면.지역": "수도권", "중기감면.업종군": "일반서적출판", "중기감면.적용감면율": 0.10}
    assert _rules(d)["A13-4"][0] == "자료 부족"


def test_sme_cap_only_from_2018():
    d = {**_fy(2017), "중기감면.산출세액": 10**9, "중기감면.감면소득": 10**9, "중기감면.과세표준": 10**9,
         "중기감면.적용감면율": 0.12, "중기감면.상시근로자감소인원": 0, "중기감면.감면세액": 120_000_000}
    assert _rules(d)["A13-6"][0] == "이상 없음"
    d2 = {**d, **_fy(2019)}
    assert _rules(d2)["A13-6"][0] == "오류 의심"


# A19-6: 이월공제 2021.1.1. 이후 신고분 10년, 그 전 5년
def test_carryforward_5_years_before_2021_filing():
    d = {**_fy(2019), "최저한세.이월공제": [{"발생연도": 2012, "금액": 10_000_000}]}
    assert _rules(d)["A19-6"][0] == "오류 의심"
    d = {**_fy(2022), "최저한세.이월공제": [{"발생연도": 2014, "금액": 10_000_000}]}
    assert _rules(d)["A19-6"][0] == "이상 없음"


# 근거 문구: 파견 인건비 정상가격 조정 근거(2020 이전 구 국조법 제4조), 온누리상품권 근거 법률
def test_expat_citation_old_article_before_2021():
    import json
    r20 = json.dumps(call_raw("expat_cost_recharge", {"year": 2020, "items": [{"급여": 100_000_000, "귀속": "현지법인", "청구액": 50_000_000}]}), ensure_ascii=False)
    r21 = json.dumps(call_raw("expat_cost_recharge", {"year": 2021, "items": [{"급여": 100_000_000, "귀속": "현지법인", "청구액": 50_000_000}]}), ensure_ascii=False)
    assert "구 국제조세조정에 관한 법률 제4조" in r20 and "법률 제7조" not in r20.replace("구 국제조세조정에 관한 법률 제4조", "")
    assert "국제조세조정에 관한 법률 제7조" in r21 and "구 국제조세조정" not in r21


def test_onnuri_vocab_cites_traditional_market_act():
    import os
    import korean_tax_calc_mcp as K
    s = open(os.path.join(os.path.dirname(K.__file__), "data", "facts_vocab.json"), encoding="utf-8").read()
    assert "전기통신금융사기" not in s and "「전통시장 및 상점가 육성을 위한 특별법」 제2조제12호" in s
