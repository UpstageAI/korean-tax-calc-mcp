"""판례·실무 기준 반영(0.61.0) — 손실은 사람 확인, 재고·유형자산 하나만 다르면 사람 확인, 광고·판관비·품목 신호, 특수관계 매출·매입 20%,
연도별 범위, 사분위 방식 선택, 표본·손실 경고, 기준값 출처. Claude 작성(2026-11-17).
근거: OECD TPG 3.64~3.65·3.57, 26 CFR §1.482-1(e)(2)(iii)(C), 국조법 시행령 제2조제2항·제15조, 국조법 기본통칙 8-15…1.
판례 근거·판단은 조문 MCP 몫 — 여기서는 숫자 비교와 표시만 검사. 네트워크 없음."""
import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_tp_screen as T
from korean_tax_calc_mcp.engine.kr_comparables import statements as ST
from korean_tax_calc_mcp.engine.kr_comparables.compare import compare_profile as _cp, labeled_rules, merged_rules, run_tool as _rt
from kr_example_rules import EX_RULES, EX_SCREENS


def compare_profile(t, c, rules=None):       # 예시 기준값을 rules로 넘김(도구에는 관행 기본값 없음)
    return _cp(t, c, {**EX_RULES, **(rules or {})})


def run_tool(t, cs, rules=None):
    return _rt(t, cs, {**EX_RULES, **(rules or {})})
from korean_tax_calc_mcp.engine.kr_comparables.schema import empty_profile, value

YEARS = [2022, 2023, 2024]


# ---------- 4. 사분위 방식 ----------
def test_us_quartile_no_interpolation():
    xs = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
    inc = S.arm_length_range(comparables=xs, tested_value=0.04, tested_is_resident=True, quartile_method="inclusive", year=2024)["결과"]
    us = S.arm_length_range(comparables=xs, tested_value=0.04, tested_is_resident=True, quartile_method="us", year=2024)["결과"]
    assert (inc["제1사분위"], inc["제3사분위"]) == pytest.approx((0.025, 0.055))
    assert (us["제1사분위"], us["중위값"], us["제3사분위"]) == pytest.approx((0.02, 0.04, 0.06))
    even = S.arm_length_range(comparables=[0.01 * i for i in range(1, 9)], tested_value=0.04, tested_is_resident=True, quartile_method="us", year=2024)["결과"]
    assert (even["제1사분위"], even["중위값"], even["제3사분위"]) == pytest.approx((0.025, 0.045, 0.065))   # 정확히 25%·50%·75%면 다음 값과 평균


# ---------- 1·3. tp_comparable_screen: 손실은 사람 확인, 연도 자료 필수 해제, 연도별 범위 ----------
def _row(cid, y, rev, op, inv=10, rec=10, pay=5):
    return {"company_id": cid, "company_name": cid, "country": "KR", "industry_code": "46510", "year": y, "currency": "KRW",
            "revenue": rev, "operating_profit": op, "total_assets": 60, "inventory": inv, "receivables": rec, "payables": pay}


def _rows():
    rs = []
    for cid, ops in (("A", (3, 4, 5)), ("B", (2, 2, 3)), ("C", (5, 6, 4)), ("D", (-1, -2, 1)), ("E", (-1, 2, 3)), ("F", (4, None, 5))):
        for y, op in zip(YEARS, ops):
            if op is not None:
                rs.append(_row(cid, y, 100, op))
    return rs


TP = {"name": "분석대상", "is_resident": True, "years": {y: {"revenue": 100, "operating_profit": 3, "inventory": 15, "receivables": 12, "payables": 10} for y in YEARS}}


def _screen(**kw):
    a = dict(rows=_rows(), tested_party=TP, analysis_years=YEARS, tested_year=2024, multi_year_reason={"code": 1, "text": "경기 변동"}, search_log={"db": "테스트"})
    a.update(kw)
    a["screens"] = {**EX_SCREENS, **(kw.get("screens") or {})}
    return T.comparable_screen(**a)


def _mx(r, cid):
    return next(m for m in r["탈락_매트릭스"] if m["company_id"] == cid)


def test_loss_is_review_by_default():
    r = _screen()
    d, e = _mx(r, "D"), _mx(r, "E")
    assert d["S5"].startswith("검토 필요: [L2]") and d["최종"] == "선정"         # 3년 중 2년 손실 → 사람 확인, 자동 제외 안 함
    assert e["S5"].startswith("표시: [L1]") and e["최종"] == "선정"              # 1년 손실 → 표시만
    assert any(x["company_id"] == "D" for x in r["결과"]["사람_확인"])
    r2 = _screen(screens={"loss_action": "exclude"})
    assert _mx(r2, "D")["최종"].startswith("탈락") and "S5" in _mx(r2, "D")["최종"]
    assert any(s["시나리오"].startswith("C 지속 손실기업 제외") for s in r["민감도"])


def test_missing_year_kept_by_default():
    r = _screen()
    f = _mx(r, "F")
    assert f["S2"].startswith("표시") and f["최종"] == "선정"
    assert _mx(_screen(screens={"require_all_years": True}), "F")["최종"].startswith("탈락")


def test_yearly_ranges_and_method_shown():
    r = _screen(quartile_method="us")["결과"]
    yr = r["연도별_범위"]
    assert set(yr) == set(YEARS) and yr[2023]["n"] == 5 and yr[2022]["n"] == 6     # F는 2023 자료 없음 — 그해만 빠짐
    assert r["범위"]["계산법"] == "us" and r["범위"]["n"] == 6 and r["범위"]["조정점"] == "중위값"
    assert "26 CFR" in r["범위"]["계산법_설명"]


def test_wca_reports_before_and_after():
    base = _screen()["결과"]
    r = _screen(wca={"rate": 0.05, "rate_basis": "테스트 금리"})["결과"]
    assert "조정_전_범위" in r and r["조정_전_범위"]["중위값%"] == base["범위"]["중위값%"]
    assert r["범위"]["중위값%"] != base["범위"]["중위값%"]


def test_option_validation():
    assert "error" in _screen(screens={"loss_action": "drop"})
    assert "error" in _screen(quartile_method="median")


# ---------- 2·5. 프로필 비교: 손실·실질 지배·기준값 출처 ----------
RESELLER = {"main_category": "merchandise", "main_share": 0.90, "inventory_basis": "ratio", "inv_to_sales": 0.15,
            "raw_material_inv": False, "ppe_ratio": 0.05, "rnd_ratio": 0.0, "advert_ratio": 0.015}


def _cand(**kw):
    p = empty_profile(company_id="X", company_name="테스트")
    p["mix_coverage"] = value(1.0)
    for k in ("product", "merchandise", "service", "sw_license", "platform_fee", "other"):
        p["mix_" + k] = value(0.0)
    p["mix_merchandise"] = value(0.92)
    p["inv_to_sales"] = value(0.15); p["ppe_ratio"] = value(0.05); p["rnd_ratio"] = value(0.0); p["advert_ratio"] = value(0.015)
    p["raw_material_inv"] = value(False)
    p.update(kw)
    return p


def test_loss_review_and_flag():
    r = compare_profile(RESELLER, _cand(loss_years=value(2, note="분석 연도 3년 중 2년 영업손실")))
    assert r["overall"] == "사람 확인" and any(x.startswith("[L2]") and "3년 중 2년" in x for x in r["reasons"])
    r = compare_profile(RESELLER, _cand(loss_years=value(1, note="분석 연도 3년 중 1년 영업손실")))
    assert r["overall"] == "포함 후보" and any(w.startswith("[L1]") for w in r["warnings"])


def test_control_signals_are_reference_only():
    sig = [{"kind": "임원 겸직", "sentence": "당사의 대표이사는 지배기업의 임원을 겸직하고 있습니다."}]
    r = compare_profile(RESELLER, _cand(control_signals=value(sig)))
    assert r["overall"] == "포함 후보" and any(x.startswith("[C1]") and "임원 겸직" in x and "판정 아님" in x for x in r["warnings"])   # 문장은 참고 표시만
    out = run_tool(RESELLER, [_cand(control_signals=value(sig), related_sales_ratio=value(0.55))])   # 의존 50% 이상([C2]) — 사람 확인
    row = out["결과"]["사람_확인_목록"][0]
    assert row["실질_지배_근거(참고)"] == sig and len(row["실질_지배_질문"]) == 4


def test_asset_differences_review_or_exclude():
    assert compare_profile(RESELLER, _cand(inv_to_sales=value(0.6)))["reasons"][0].startswith("[K1]")
    r = compare_profile(RESELLER, _cand(inv_to_sales=value(0.6), ppe_ratio=value(0.5)))
    assert r["overall"] == "제외 후보" and r["reasons"][0].startswith("[K3]")
    r = compare_profile(RESELLER, _cand(raw_material_inv=value(True)))
    assert r["overall"] == "사람 확인" and r["reasons"][0].startswith("[K5]")
    r = compare_profile(RESELLER, _cand(raw_material_inv=value(True), ppe_ratio=value(0.5)))
    assert r["overall"] == "제외 후보" and r["reasons"][0].startswith("[K4]")


def test_marketing_and_sga_need_review():
    r = compare_profile(RESELLER, _cand(advert_ratio=value(0.08)))           # 1.5% vs 8%: 3배 넘고 차이 3%p 넘음
    assert r["overall"] == "사람 확인" and r["reasons"][0].startswith("[A1]")
    assert compare_profile(RESELLER, _cand(advert_ratio=value(0.04)))["overall"] == "포함 후보"
    t = RESELLER | {"sga_ratio": 0.10}
    assert compare_profile(t, _cand(sga_ratio=value(0.45)))["reasons"][0].startswith("[A2]")
    assert compare_profile(t, _cand(sga_ratio=value(0.15)))["overall"] == "포함 후보"
    assert "sga" not in compare_profile(RESELLER, _cand(sga_ratio=value(0.45)))["items"]   # 분석대상 값 없으면 비교 안 함


def test_product_keywords():
    t = RESELLER | {"product_keywords": ["의료기기", "진단 시약"]}
    c = _cand(business_desc=value("당사는 산업용 윤활유를 수입하여 판매합니다. 주요 고객은 정유사입니다."))
    r = compare_profile(t, c)
    assert r["overall"] == "사람 확인" and r["reasons"][0].startswith("[P1]")
    assert r["product_match"]["원문"][0].startswith("당사는 산업용 윤활유")
    c = _cand(business_desc=value("당사는 체외 진단시약과 의료기기를 수입 판매합니다."))
    assert compare_profile(t, c)["overall"] == "포함 후보" and compare_profile(t, c)["product_match"]["겹침"] == ["의료기기", "진단 시약"]
    assert any(w.startswith("[P0]") for w in compare_profile(t, _cand())["warnings"])


def test_rule_sources_labeled():
    lab = labeled_rules(merged_rules(EX_RULES), EX_RULES)
    legal = sorted(k for k, v in lab.items() if v["구분"] == "법정")
    assert legal == ["범위·중위값 조정(tp_comparable_screen·arm_length_range)"]   # 법정은 범위·중위값 조정뿐
    assert lab["independence_legal_pct"]["구분"] == "법정 준용"
    assert lab["related_review"]["구분"] == "입력" and lab["loss_review_years"]["구분"] == "관행" and lab["related_review"]["값"] == "꺼짐"   # 0.72.0 — 기본값 없음
    assert "숫자 기준 없음" in lab["related_review"]["근거"] and lab["control_dependence"]["구분"] == "법정 준용"
    assert lab["mix_max_diff"]["구분"] == "우리 규칙" and all(v["근거"] for v in lab.values())
    assert "조문 MCP" in lab["판단_근거_확인"]["근거"] and "판정 아님" in lab["related_review"]["근거"]
    import re
    assert not any(re.search(r"\d{4}(두|누|구합)\d{3,5}", v["근거"]) for v in lab.values())   # 판례 인용은 조문 MCP 몫


# ---------- 5. 특수관계자 주석에서 실질 지배 신호 추출 ----------
NOTE = ("<P>24. 특수관계자 거래</P><P>(1) 당사의 지배기업은 Global Parent Inc.이며, 당사의 대표이사는 지배기업의 임원을 겸직하고 있습니다.</P>"
        "<P>(2) 당기 중 지배기업으로부터 운영자금 대여를 받았으며, 지배기업이 당사 차입금에 지급보증을 제공하고 있습니다.</P>"
        "<TABLE><TR><TH>회사명</TH><TH>매출</TH><TH>매입</TH></TR><TR><TD>Global Parent Inc.</TD><TD>1,000</TD><TD>60,000</TD></TR>"
        "<TR><TD>합계</TD><TD>1,000</TD><TD>60,000</TD></TR></TABLE><P>(단위: 원)</P><P>25. 우발부채</P>")


def test_control_signal_extraction():
    doc = "<DOCUMENT>" + NOTE + "</DOCUMENT>"
    sig, title = ST.control_signals(doc, False)
    assert {"임원 겸직", "지배기업", "자금 대여·보증"} <= {x["kind"] for x in sig}
    assert all(len(x["sentence"]) <= 200 for x in sig)
    r, why = ST.related_purchases(doc, False, cogs=80_000, revenue=100_000)
    assert r == pytest.approx(0.75) and "매출원가" in why                 # 60,000 ÷ 매출원가 80,000
    assert ST.control_signals("<DOCUMENT><P>1. 일반사항</P></DOCUMENT>", False)[0] is None


# ---------- 판례 경고: 손실 일괄 제외·표본·운전자본 한계 ----------
def test_tested_loss_with_exclusion_warns():
    tp = {**TP, "years": {**TP["years"], 2024: {**TP["years"][2024], "operating_profit": -2}}}
    r = _screen(tested_party=tp, screens={"loss_action": "exclude"})
    assert any("일괄 제외" in w for w in r["경고"])
    assert not any("일괄 제외" in w for w in _screen(tested_party=tp)["경고"])      # 기본(사람 확인)은 경고 없음


def test_small_sample_warns_and_wca_limit():
    r = _screen(rows=[x for x in _rows() if x["company_id"] in ("A", "B", "C")], screens={"sample_min": 5, "spread_ratio": 1.0})
    assert any(w.startswith("[우리 규칙] 표본 3개") for w in r["경고"])
    w = _screen(wca={"rate": 0.05, "rate_basis": "테스트"})
    assert "품목·거래단계" in w["보고서_부록"]["차이_조정"]["한계"] and any(x.startswith("운전자본 조정은 재고") for x in w["주의"])


# ---------- 국세청 통칙 8-15…1 사분위, 세 방식 민감도(기본값·기존 숫자 그대로) ----------
@pytest.mark.parametrize("n,q1,q3", [(2, 1, 2), (3, 1.5, 2.5), (4, 1.5, 3.5), (5, 1.5, 4.5), (6, 2, 5), (7, 2.5, 5.5), (8, 2.5, 6.5), (9, 2.5, 7.5), (10, 3, 8), (12, 3.5, 9.5)])
def test_nts_quartile_table(n, q1, q3):
    # 국세청 「외국법인 및 외국인투자기업 납세안내」(2026) 인쇄 272~273쪽 통칙 위치 — 표는 out/tp_screening_local_sources.md 2절
    r = S.arm_length_range(comparables=list(range(1, n + 1)), tested_value=1, tested_is_resident=True, quartile_method="nts", year=2024)["결과"]
    assert (r["제1사분위"], r["제3사분위"]) == pytest.approx((q1, q3))


def test_quartile_default_nts_and_sensitivity():
    xs = [0.0573, 0.0776]
    r = S.arm_length_range(comparables=xs, tested_value=0.025, tested_is_resident=True, year=2024)
    assert (r["결과"]["제1사분위"], r["결과"]["제3사분위"]) == pytest.approx(tuple(xs))         # n=2: 위치 1·2 → 최솟값~최댓값
    assert r["결과"]["사분위_방식"] == {"방식": "nts", "설명": r["결과"]["사분위_방식"]["설명"], "n": 2, "근거": r["결과"]["사분위_방식"]["근거"], "조정점": "중위값"}
    assert "8-15…1" in r["결과"]["사분위_방식"]["근거"]
    sens = r["사분위_민감도"]
    assert set(sens) == {"excel_inc", "nts", "us"} and (sens["excel_inc"]["제1사분위"], sens["excel_inc"]["제3사분위"]) == pytest.approx((0.062375, 0.072525))   # 0.0573 + 0.25·0.0203, 0.0573 + 0.75·0.0203
    scr = _screen()["결과"]
    assert set(scr["사분위_민감도"]) == {"excel_inc", "nts", "us"} and scr["범위"]["계산법"] == "nts"
    assert scr["사분위_민감도"]["nts"]["제1사분위%"] == scr["범위"]["제1사분위%"]


def test_nts_ruling_example_n91():
    # 통칙 8-15…1 예: n=91 → 아래 위치 (91+2)/4 = 23.25, 위 위치 (273+2)/4 = 68.75 — 소수 위치면 인접 두 값 평균
    xs = list(range(1, 92))
    r = S.arm_length_range(comparables=xs, tested_value=50, tested_is_resident=True, year=2024)["결과"]
    assert (r["제1사분위"], r["중위값"], r["제3사분위"]) == (23.5, 46, 68.5)
    r = S.arm_length_range(comparables=[3, 1, 2], tested_value=2, tested_is_resident=True, year=2024)["결과"]
    assert (r["제1사분위"], r["제3사분위"]) == (1.5, 2.5)                        # n=3: 위치 1.25·2.75


# ---------- 단년 주 결과·서식 칸(Ⅱ-8·9·11·12·13) ----------
def test_single_year_primary_and_form_fields():
    r = _screen(multi_year_reason=None)
    assert r["결과"]["주_결과"].startswith("단년_범위") and r["결과"]["단년_범위"]["n"] == 6
    assert _screen()["결과"]["주_결과"].startswith("범위(다년")
    rows = [dict(x, rcept_no="2025031400000" + x["company_id"][-1:].replace("A", "1").replace("B", "2").replace("C", "3").replace("D", "4").replace("E", "5").replace("F", "6"),
                 fs_div="OFS", accounting_standard="K-IFRS") for x in _rows()]
    tp = {**TP, "selection_reason": "기능이 단순한 쪽", "pli_reason": "판매 기능 — 영업이익률"}
    r = _screen(rows=rows, tested_party=tp, search_log={"db": "테스트", "collected_at": "2026-11-17"},
                manual_decisions=[{"company_id": "E", "decision": "accept", "reason": "검토 후 포함", "evidence": "주석", "reviewer": "검토자"}],
                wca={"rate": 0.05, "rate_basis": "테스트"})
    b = r["보고서_부록"]
    y = b["최종_비교대상_재무_요약"][0]["연도별"][2024]
    assert y["재무제표_구분"] == "별도" and y["회계기준"] == "K-IFRS" and y["수집_기준_시점"] == "2026-11-17" and y["출처_접수번호"].startswith("20250314")
    assert b["사람_판단"][0]["사유"] == "검토 후 포함" and b["Ⅱ-9_분석대상_선정_이유"] == "기능이 단순한 쪽" and b["Ⅱ-8_지표_선정_이유"].startswith("판매")
    adj = b["차이_조정"]
    assert adj["적용_쪽"].startswith("비교대상") and all(x["조정_전%"] is not None and x["조정_후%"] is not None for x in adj["조정_전후"])


def test_s1a_marked_as_applied_by_analogy():
    crit = _screen()["보고서_부록"]["탐색_조건"]["적용_기준"][0]
    assert crit["성격"].startswith("[법정 준용]") and crit["입력"].startswith("법정")


# ---------- 실질 지배 숫자·기능 질문 ----------
def test_dependence_50_and_questions():
    r = compare_profile(RESELLER, _cand(related_purchase_ratio=value(0.55)))
    assert any(x.startswith("[C2]") for x in r["reasons"]) and r["overall"] == "사람 확인"
    out = run_tool(RESELLER | {"own_marketing": False, "bears_inventory_risk": True}, [_cand(related_purchase_ratio=value(0.55))])
    row = out["결과"]["사람_확인_목록"][0]
    assert len(row["실질_지배_질문"]) == 4 and {q["질문"] for q in row["기능_질문"]} == {"자체 마케팅(시장개척·브랜드 홍보)을 하는가", "재고위험을 부담하는가"}
    assert "조문 MCP" in row["기능_질문"][0]["근거"]
    with pytest.raises(ValueError):
        run_tool(RESELLER | {"own_marketing": "아니오"}, [_cand()])


# ---------- 비상장 지분율(감사보고서 주석) — 지분만으로 제외하지 않음 ----------
OWN_TABLE = ("<P>1. 일반사항</P><P>당기말 현재 자본금은 50,000천원이며, 당사의 주주 현황은 다음과 같습니다.</P>"
             "<TABLE><TR><TH>주주</TH><TH>소유주식수(주)</TH><TH>지분율(%)</TH></TR><TR><TD>갑</TD><TD>4,000</TD><TD>80.00</TD></TR>"
             "<TR><TD>을</TD><TD>1,000</TD><TD>20.00</TD></TR><TR><TD>합 계</TD><TD>5,000</TD><TD>100.00</TD></TR></TABLE><P>2. 회계정책</P>")
OWN_SENT = "<P>1. 일반사항</P><P>당기말 현재의 자본금은 50백만원이며, 스웨덴국 소재법인인 Parent AB 가 지분 100%를 소유하고 있습니다.</P>"
SUB_TABLE = ("<P>9. 종속기업투자</P><P>당사의 종속기업 현황은 다음과 같습니다.</P><TABLE><TR><TH>회사명</TH><TH>주식수</TH><TH>지분율</TH></TR>"
             "<TR><TD>자회사</TD><TD>100</TD><TD>100%</TD></TR></TABLE>")


def test_owner_share_extraction():
    pct, ev = ST.owner_share("<DOCUMENT>주석" + OWN_TABLE + "</DOCUMENT>")
    assert pct == 80.0 and "갑" in ev
    pct, ev = ST.owner_share("<DOCUMENT>주석" + OWN_SENT + "</DOCUMENT>")
    assert pct == 100.0 and "Parent AB" in ev
    assert ST.owner_share("<DOCUMENT>주석" + SUB_TABLE + "</DOCUMENT>")[0] is None      # 회사가 가진 자회사 지분표는 제외


def test_unlisted_owner_review_not_exclude():
    r = compare_profile(RESELLER, _cand(owner_pct=value(100.0), related_sales_ratio=value(0.02), related_purchase_ratio=value(0.9)))
    assert r["overall"] == "사람 확인" and any(x.startswith("[I3]") and "매입 90%" in x for x in r["reasons"])
    assert compare_profile(RESELLER, _cand(owner_pct=value(30.0)))["overall"] == "포함 후보"


# ---------- 관행 기준값은 도구에 없음 — rules·screens가 없으면 법정 기준만 ----------
def test_no_rules_applies_statutory_only():
    out = _rt(RESELLER, [_cand(inv_to_sales=value(0.6), ppe_ratio=value(0.5)), _cand(max_shareholder_pct=value(55.0)), _cand(related_purchase_ratio=value(0.6))])
    res = out["결과"]
    assert res["안내"].startswith("관행 기준 미적용") and out["주의"][0].startswith("관행 기준 미적용")
    rows = res["비교표"]
    assert rows[0]["종합"] == "포함 후보" and rows[0]["재고"]["판정"] == "기준 없음" and rows[0]["재고"]["배수"] == 4.0   # 숫자는 냄
    assert rows[1]["종합"] == "제외 후보" and rows[1]["사유"][0].startswith("[I1]")                                   # 법정 준용 50%
    assert rows[2]["종합"] == "사람 확인" and rows[2]["사유"][0].startswith("[C2]")                                   # 거래 의존 50%
    used = res["사용_기준"]
    assert used["mix_max_diff"]["값"] == "꺼짐" and used["independence_legal_pct"]["입력"].startswith("법정")
    out = _rt(RESELLER, [_cand()], rules={"mix_max_diff": 0.15})
    assert "안내" not in out["결과"] and out["결과"]["사용_기준"]["mix_max_diff"]["입력"] == "사용자 입력"
    with pytest.raises(ValueError):
        _rt(RESELLER, [_cand()], rules={"independence_legal_pct": 60})          # 법정 기준보다 느슨하게는 못 둠
    r = T.comparable_screen(rows=_rows(), tested_party=TP, analysis_years=YEARS, tested_year=2024, multi_year_reason={"code": 1, "text": "x"}, search_log={"db": "t"})
    assert r["결과"]["안내"].startswith("관행 기준 미적용") and r["결과"]["최종_수"] == 6        # 손실 회사도 남음(S5 꺼짐)
    tbl = {c["기준"]: c for c in r["보고서_부록"]["탐색_조건"]["적용_기준"]}
    assert tbl["S5 지속 손실(연도 수)"]["값"] == "꺼짐" and tbl["S1a 독립성"]["입력"].startswith("법정")
    crit = _screen(screens={"sample_min": 3})["보고서_부록"]["탐색_조건"]["적용_기준"]
    tbl = {c["기준"]: c for c in crit}
    assert tbl["표본·편차 경고"]["입력"] == "사용자 입력" and tbl["S5 지속 손실(연도 수)"]["입력"] == "사용자 입력"
    assert not any(w.startswith("[우리 규칙] 표본") for w in _screen(rows=[x for x in _rows() if x["company_id"] in "ABC"], screens={"sample_min": 3, "spread_ratio": 5})["경고"])


# ---------- 조문 MCP '넘길 값' 연결(고정본) — 키 이름 그대로 받아 오류 없이 ----------
def test_tax_mcp_handoff_values_accepted():
    """조문 MCP 0.30.0 '넘길 값'(특수관계 상한·검토선 없음, control_dependence 0.5)을 오류 없이 받음."""
    import json, os
    h = json.load(open(os.path.join(os.path.dirname(__file__), "data", "tax_mcp_handoff_1123.json"), encoding="utf-8"))
    rules = h["kr_comparable_profile_compare"]["rules"]
    assert not set(rules) & {"related_review", "related_sales_review", "related_purchase_review"} and rules["control_dependence"] == 0.5
    assert not set(h["tp_comparable_screen"]["screens"]) & {"related_max", "related_purchase_max"}
    r = S.kr_comparable_profile_compare(tested=RESELLER, candidates=[_cand(), _cand(inv_to_sales=value(0.6))], **h["kr_comparable_profile_compare"])
    assert "error" not in r and "안내" not in r["결과"]
    assert r["결과"]["사용_기준"]["related_review"]["값"] == "꺼짐" and r["결과"]["사용_기준"]["control_dependence"]["입력"] == "사용자 입력"
    assert r["결과"]["비교표"][1]["종합"] == "사람 확인" and r["결과"]["비교표"][1]["광고판촉"]["판정"] == "가까움"   # advert_mult 없으면 ratio_low~high
    sc = h["tp_comparable_screen"]
    out = S.tp_comparable_screen(tested_party=TP, analysis_years=YEARS, tested_year=2024, rows=_rows(), multi_year_reason={"code": 1, "text": "x"},
                                 search_log={"db": "t"}, screens=sc["screens"], quartile_method=sc["quartile_method"])
    assert "error" not in out and "안내" not in out["결과"] and out["결과"]["범위"]["계산법"] == "nts"
    out = S.tp_comparable_screen(tested_party=TP, analysis_years=YEARS, tested_year=2024, rows=_rows(), multi_year_reason={"code": 1, "text": "x"},
                                 search_log={"db": "t"}, screens=sc["screens"], quartile_method="inclusive")
    assert out["결과"]["범위"]["계산법"] == "excel_inc"
    out = S.tp_comparable_screen(tested_party=TP, analysis_years=YEARS, tested_year=2024, rows=_rows(), multi_year_reason={"code": 1, "text": "x"},
                                 search_log={"db": "t"}, screens=sc["screens"], quartile_method="nts_rule_8_15")
    assert out["결과"]["범위"]["계산법"] == "nts"
    bad = S.kr_comparable_profile_compare(tested=RESELLER, candidates=[_cand()], rules={"independence_legal_pct": 60})
    assert "error" in bad
