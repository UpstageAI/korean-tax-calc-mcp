"""매출 구성 v2 — 제품/상품은 회계 숫자로, 모델은 재화까지만. Claude 작성(2026-11-16). 네트워크 없음.
- 회계 신호: 매출원가 상품:제품(없으면 재고 상품:제품·재공품·원재료)
- 배분: 모델·규칙이 '재화'로 본 행 합계 × 회계 비율(행 단위 아님)
- 엇갈림(모델 재화 비중 vs 회계 재화 원가 비중 50%p 넘게 차이)·신호 없음 → 매출 구성 불명 → 사람 확인(제외로 가지 않음)"""
import json
import os
import re

import pytest

from korean_tax_calc_mcp.engine.kr_comparables import candidates as C
from korean_tax_calc_mcp.engine.kr_comparables import revenue_mix as RM
from korean_tax_calc_mcp.engine.kr_comparables import statements as ST
from korean_tax_calc_mcp.engine.kr_comparables.compare import compare_profile
from korean_tax_calc_mcp.engine.kr_comparables.schema import empty_profile, value

RESELLER = {"main_category": "merchandise", "main_share": 0.90, "inventory_basis": "ratio", "inv_to_sales": 0.15,
            "raw_material_inv": False, "ppe_ratio": 0.05, "rnd_ratio": 0.0, "advert_ratio": 0.02}


def R(label, v):
    return (label, [v], [])


# ---------- 회계 신호 ----------
def test_signal_from_cost_of_sales():
    sig = ST.goods_signals([R("상품매출원가", 300), R("제품매출원가", 100), R("용역매출원가", 100)], [], cogs_total=500, rcept_no="20250101000001")
    assert sig["merch_ratio"] == pytest.approx(0.75) and sig["source"] == "매출원가 상품:제품"
    assert sig["goods_cost_share"] == pytest.approx(0.8) and sig["rcept_no"] == "20250101000001"


def test_signal_from_inventory_when_no_cost_breakdown():
    inv = [R("유동상품", 20), R("상품평가충당금", -5), R("유동제품", 30), R("유동원재료", 50)]
    sig = ST.goods_signals([R("매출원가", 900)], inv + [R("유동상품", 777)])        # 되풀이된 표는 처음 값만
    assert sig["source"].startswith("재고") and sig["merch_ratio"] == pytest.approx(20 / 100)


def test_no_signal():
    assert ST.goods_signals([R("매출원가", 10)], [R("재고자산", 5)])["merch_ratio"] is None


def test_heyin_shape_merchandise_only():
    """상품 재고·상품매출원가만 있는 형태 → 재화 매출은 전부 상품."""
    sig = ST.goods_signals([R("상품매출원가", 800)], [R("상품", 120)], cogs_total=800)
    rows = [("장비/엔진 / 장비, 엔진, 산업장비", 900, 0, 1, None), ("정비 용역", 100, 0, 2, None)]
    cls = {0: ("goods", "모델"), 1: ("service", "모델")}
    al = RM.allocate(rows, cls, sig)
    assert al["shares"]["merchandise"] == pytest.approx(0.9) and al["shares"]["product"] == 0 and al["conflict"] is None
    assert al["goods_alloc"].startswith("회계 기준 배분")


# ---------- 배분 ----------
def test_allocation_applies_ratio_to_goods_total():
    rows = [("a", 600, 0, 1, None), ("b", 200, 0, 2, None), ("원문 상품", 100, 0, 3, "merchandise"), ("SW", 100, 0, 4, None)]
    cls = {0: ("goods", "모델"), 1: ("goods", "모델"), 2: ("merchandise", "원문 매출유형"), 3: ("sw_license", "모델")}
    al = RM.allocate(rows, cls, {"merch_ratio": 0.25, "source": "매출원가 상품:제품"})
    assert al["shares"]["merchandise"] == pytest.approx((800 * 0.25 + 100) / 1000)
    assert al["shares"]["product"] == pytest.approx(800 * 0.75 / 1000)
    assert al["shares"]["sw_license"] == pytest.approx(0.1) and al["unknown"] == []


def test_allocation_unknown_without_signal():
    rows = [("재화 행", 700, 0, 1, None), ("용역 행", 300, 0, 2, None)]
    al = RM.allocate(rows, {0: ("goods", "모델"), 1: ("service", "모델")}, {"merch_ratio": None})
    assert al["unknown"] == ["product", "merchandise"] and "불명" in al["goods_alloc"]
    assert al["shares"]["service"] == pytest.approx(0.3)


def test_conflict_detected():
    rows = [("서비스 운영", 900, 0, 1, None), ("장비", 100, 0, 2, None)]
    sig = {"merch_ratio": 1.0, "source": "매출원가 상품:제품", "goods_cost_share": 0.95}
    al = RM.allocate(rows, {0: ("service", "모델"), 1: ("goods", "모델")}, sig)
    assert al["conflict"] and "10%" in al["conflict"] and "95%" in al["conflict"]


# ---------- 비교: 엇갈림·불명은 사람 확인 ----------
def _cand(**mix):
    p = empty_profile(company_id="X", company_name="테스트")
    p["mix_coverage"] = value(1.0)
    for k in ("product", "merchandise", "service", "sw_license", "platform_fee", "other"):
        p["mix_" + k] = mix.get(k, value(0.0))
    p["inv_to_sales"] = value(0.15)
    p["ppe_ratio"] = value(0.05)
    p["rnd_ratio"] = value(0.0)
    p["advert_ratio"] = value(0.02)
    p["raw_material_inv"] = value(False)
    return p


def test_conflict_goes_to_review_not_exclusion():
    note = "엇갈림 — 매출 행 분류상 재화 10% vs 회계상 재화 원가 95%(매출원가 상품:제품) — 사람 확인"
    c = _cand(**{k: value(note=note) for k in ("product", "merchandise", "service", "sw_license", "platform_fee", "other")})
    r = compare_profile(RESELLER, c)
    assert r["items"]["revenue_mix"]["verdict"] == "불명" and r["overall"] == "사람 확인"
    assert any("엇갈림" in x for x in r["reasons"])


def test_no_signal_goes_to_review():
    note = "제품/상품 배분 불명 — 원문 매출유형도 회계 신호(매출원가 상품:제품·재고 구성)도 없음 — 사람 확인"
    c = _cand(product=value(note=note), merchandise=value(note=note), service=value(0.05))
    r = compare_profile(RESELLER, c)
    assert r["overall"] == "사람 확인" and any("배분 불명" in x for x in r["reasons"])


def test_unknown_split_but_upper_bound_far_is_diff():
    note = "제품/상품 배분 불명 — 사람 확인"
    c = _cand(product=value(note=note), merchandise=value(note=note), service=value(0.41), sw_license=value(0.53))
    r = compare_profile(RESELLER, c)          # 상품은 많아야 6% → 90%와 20%p 넘게 차이
    assert r["items"]["revenue_mix"]["verdict"] == "다름" and r["overall"] == "제외 후보"
    assert any("상한" in x for x in r["reasons"])


def test_accounting_rows_count_as_verified():
    c = _cand(merchandise=value(0.95), service=value(0.05))
    c["mix_coverage"]["evidence"]["rows"] = [{"label": "장비", "amount": 95, "category": "goods", "reason": "회계 기준 배분(모델·규칙: 재화) 모델"},
                                             {"label": "정비", "amount": 5, "category": "service", "reason": "모델"}]   # 모델만으로 정한 행 5% < 10%
    assert compare_profile(RESELLER, c)["overall"] == "포함 후보"


# ---------- 모델에는 제품/상품을 묻지 않음 ----------
def test_solar_prompt_goods_only(monkeypatch, tmp_path):
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path))
    seen = {}

    def fake(body, key):
        seen["c"] = body["messages"][0]["content"]
        return {"choices": [{"message": {"content": json.dumps({"rows": [{"id": 0, "category": "재화", "reason": "물건"}, {"id": 1, "category": "제품", "reason": "엉뚱"}]}, ensure_ascii=False)}}]}
    got = RM.classify_solar(["CAT 엔진", "부품"], "건설장비 수입·판매를 주된 사업으로 영위", "k" * 10, http=fake)
    assert "제조 여부" in seen["c"] and "건설장비 수입·판매" in seen["c"] and "재화|용역|SW·라이선스|플랫폼·중개수수료|기타" in seen["c"]
    assert got[0][0] == "goods" and got[1][0] == "other"    # 5갈래 밖 답은 기타


# ---------- 회사 맥락: '1. 사업의 개요' 절 전체(4,000자까지), 길면 앞 1,500자 + 회사가 주어인 문장 ----------
FX = os.path.join(os.path.dirname(__file__), "data", "kr_comparables_fixtures")
OV = {"혜인": "20250320001279", "제이씨현시스템": "20250312000813", "정원엔시스": "20250317000308", "카스": "20250321001962",
      "케이사인": "20250317000254", "데이타솔루션": "20250312000588", "웹케시": "20250314001644"}


def _ctx(name):
    return C._context(open(os.path.join(FX, f"overview_{OV[name]}.xml"), encoding="utf-8").read(), True)


@pytest.mark.parametrize("name,phrases", [
    ("혜인", ["공식 딜러쉽 계약", "공급하고 있습니다"]),
    ("제이씨현시스템", ["IT제품 등을 판매, 리스"]),
    ("정원엔시스", ["제조사로부터 IT 관련 H/W 및 S/W 물품을 공급받아", "유통", "총판사"]),      # '총판사'는 뒤쪽 단락
    ("웹케시", ["B2B 핀테크 서비스 제공 기업"]),                                            # 서비스 회사 — 단어 목록이 아니라 절 전체라 들어감
])
def test_context_keeps_function_sentences(name, phrases):
    c = _ctx(name)
    assert 0 < len(c) <= 4000
    for ph in phrases:
        assert ph in c, (name, ph)
    assert "참고하시기" not in c and "참조하시기" not in c


@pytest.mark.parametrize("name,start,company", [
    ("카스", "가. 업계의 현황", "카스는 각국의 인증"),
    ("케이사인", "가. 업계의 현황", "당사는 아래의 사업을 영위"),
    ("데이타솔루션", "가. 시장의 현황", "당사는 통계분석 S/W 사업, 스토리지 사업, SI 사업을 영위"),
])
def test_context_reaches_company_sentences_after_industry_intro(name, start, company):
    c = _ctx(name)
    assert c.startswith(start) and company in c and len(c) <= 4000


def test_long_section_head_plus_company_subject_sentences():
    c = _ctx("데이타솔루션")                       # 절이 4,000자를 넘는 경우
    head, rest = c.split(" … ", 1)
    assert len(head) == C.CTX_HEAD and len(c) <= C.CTX_MAX
    sents = C._sentences(rest)
    assert sents
    for sent in sents:
        assert re.search(r"당사|회사|데이타솔루션", sent[:60]), sent[:60]


def test_context_drops_numeric_rows_and_guidance():
    doc = ("<DOCUMENT><TITLE>1. 사업의 개요</TITLE><P>당사는 계측기를 수입해 판매합니다. 자세한 내용은 '2. 주요 제품'을 참고하시기 바랍니다.</P>"
           "<TABLE><TR><TD>구분</TD><TD>2024년</TD></TR><TR><TD>매출</TD><TD>1,234,567</TD></TR><TR><TD>사업부문</TD><TD>계측기 유통</TD></TR></TABLE>"
           "<TITLE>2. 주요 제품</TITLE></DOCUMENT>")
    c = C._context(doc, True)
    assert "수입해 판매" in c and "계측기 유통" in c and "1,234,567" not in c and "참고하시기" not in c


def test_context_sent_to_model(monkeypatch, tmp_path):
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path))
    seen = {}

    def fake(body, key):
        seen["c"] = body["messages"][0]["content"]
        return {"choices": [{"message": {"content": json.dumps({"rows": [{"id": 0, "category": "재화"}]}, ensure_ascii=False)}}]}
    ctx = _ctx("정원엔시스")
    RM.classify_solar(["IT 인프라"], ctx, "k" * 10, http=fake)
    assert ctx in seen["c"] and "총판사" in seen["c"]


# ---------- 사업의 개요 추출 검사·실패 시 동작 ----------
@pytest.mark.parametrize("ctx,raw,kind", [
    ("1. 사업의 개요 ··········· 5 2. 주요 제품 ··········· 9", "x" * 500, "목차"),
    ("당사는 장비를 판매합니다.", "당사는 장비를 판매합니다. " * 40, "200자"),
    ("당사는 장비를 판매합니다. 2. 주요 제품 및 서비스 가. 주요 제품", "당사는", "다른 절"),
    ("시장은 성장하고 있습니다. " * 20, "시장은 성장. 당사는 장비를 판매합니다.", "회사"),
    ("1,234 5,678 (12.3) 9,876 45.6% 7,890 1,111 2,222", "1,234", "숫자만"),
])
def test_overview_problem_types(ctx, raw, kind):
    assert any(kind in x for x in C.overview_problems(ctx, raw)), C.overview_problems(ctx, raw)


def test_overview_fixtures_pass_checks():
    for name, rc in OV.items():
        ov = C._overview(open(os.path.join(FX, f"overview_{rc}.xml"), encoding="utf-8").read())
        assert ov["problems"] == [], (name, ov["problems"])


def test_extraction_failure_skips_model_and_needs_review(monkeypatch, tmp_path):
    from korean_tax_calc_mcp.engine.kr_comparables.compare import compare_profile
    from tests.test_kr_comparable_candidates import Transport, _client, FAKE_KEY
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DART_API_KEY", FAKE_KEY)
    monkeypatch.setattr(C, "_overview", lambda s, name=None: {"ctx": "", "raw": "x" * 900, "truncated": False, "problems": ["사업의 개요 절 없음"]})
    called = {"n": 0}

    def solar(body, key):
        called["n"] += 1
        raise AssertionError("모델을 부르면 안 됨")
    r = C.run(industry_codes=["46"], years=[2024], listed="상장", client=_client(Transport()), upstage_key="u" * 20, solar_http=solar)["결과"]
    assert called["n"] == 0 and r["후보_수"] == 2
    for p in r["후보_프로필"]:
        assert p["mix_merchandise"]["status"] == "불명-못찾음" and "사업의 개요 추출 실패" in p["mix_merchandise"]["note"]
        cmp_ = compare_profile(RESELLER, p)
        assert cmp_["items"]["revenue_mix"]["verdict"] == "불명"
        assert any("사업의 개요 추출 실패" in x for x in cmp_["reasons"])
