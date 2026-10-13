"""끝에서 끝까지 계산기 정답 테스트 (Claude 작성 2026-10-13) — 수정 금지.
공개 검증 사례(세무사 1차 시험 문제, 출처 Q-Net 공개 문제·정답)는 원문 사실관계를 그대로 입력하고 공식 정답과 손계산 일치를 확인. 실무형 사례는 Claude 손계산. 이 사례들은 도구 설계의 기준이 아니라 검증용이다.
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def find(judg, word):
    return [j for j in judg if word in json.dumps(j, ensure_ascii=False)]


# ── 대손충당금 ───────────────────────────────────────────────────────────────
def test_bad_debt_2024_66():  # 공개 검증 사례: 세무사 1차 2024-66(정답 ① 81,674,945원)
    r = c("bad_debt_adjustment", {
        "year": 2024, "sme": False, "prior_excess": 20_000_000,
        "book": {"opening": 150_000_000, "offset": 130_000_000, "provision": 200_000_000, "closing": 220_000_000},
        "receivables_prev_end_book": 1_400_000_000, "receivables_end_book": 2_500_000_000,
        "writeoffs": [
            {"kind": "소멸시효완성", "amount": 40_000_000, "arose_in": "전기"},
            {"kind": "화해·확정판결", "amount": 70_000_000, "arose_in": "당기"},
            {"kind": "부도6개월", "amount": 15_000_000, "arose_in": "당기", "instrument": "외상매출금", "months_since_default": 9, "mortgage": False},
            {"kind": "부도6개월", "amount": 5_000_000, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 9, "mortgage": False},
        ]})
    k = r["계산"]
    assert k["세법상 당기 대손금"] == 74_999_000
    assert k["세법상 전기말 채권"] == 1_360_000_000
    assert k["세법상 당기말 채권"] == 2_515_001_000
    assert abs(k["대손실적률"] - 0.055) < 1e-9
    assert r["결과"]["한도"] == 138_325_055
    assert r["결과"]["한도초과"] == 81_674_945
    assert len(r["판단"]) >= 4 and all(j.get("근거") for j in r["판단"])
    assert "부인" in json.dumps(find(r["판단"], "외상매출금"), ensure_ascii=False)


def test_bad_debt_sme_receivable_allowed():  # 실무형: 중소기업 부도 외상매출금은 인정(비망 1,000원)
    r = c("bad_debt_adjustment", {
        "year": 2025, "sme": True, "prior_excess": 0,
        "book": {"opening": 30_000_000, "offset": 10_000_000, "provision": 0, "closing": 20_000_000},
        "receivables_prev_end_book": 1_000_000_000, "receivables_end_book": 1_200_000_000,
        "writeoffs": [{"kind": "부도6개월", "amount": 10_000_000, "arose_in": "당기", "instrument": "외상매출금", "months_since_default": 7, "mortgage": False}]})
    assert r["계산"]["세법상 당기 대손금"] == 9_999_000
    assert r["계산"]["세법상 당기말 채권"] == 1_200_001_000
    assert r["결과"]["한도"] == 12_000_010          # 실적률 0.009 < 1% → 1%
    assert r["결과"]["한도초과"] == 7_999_990


# ── 기업업무추진비 ───────────────────────────────────────────────────────────
def test_entertainment_2024_65():  # 공개 검증 사례: 세무사 1차 2024-65(정답 ① 대표자상여 8,000,000 / 기타사외유출 12,350,000
    r = c("entertainment_adjustment", {
        "year": 2024, "sme": False, "months": 12,
        "revenue_general": 7_500_000_000, "revenue_related": 4_500_000_000,
        "expenses": [{"amount": 8_000_000, "evidence": "없음"},
                     {"amount": 6_000_000, "evidence": "영수증 등", "over_30k": True},
                     {"amount": 42_000_000, "evidence": "적격"}]})
    tot = {}
    for a in r["세무조정"]:
        tot[a["소득처분"]] = tot.get(a["소득처분"], 0) + a["금액"]
    assert tot.get("대표자상여") == 8_000_000
    assert tot.get("기타사외유출") == 12_350_000
    assert r["결과"]["한도"] == 35_650_000 and r["결과"]["한도초과"] == 6_350_000


def test_entertainment_sme_within_limit():  # 실무형: 중소기업, 한도 내
    r = c("entertainment_adjustment", {"year": 2024, "sme": True, "months": 12, "revenue_general": 5_000_000_000, "revenue_related": 0,
                                        "expenses": [{"amount": 30_000_000, "evidence": "적격"}, {"amount": 2_000_000, "evidence": "없음"}]})
    assert r["결과"]["한도"] == 51_000_000 and r["결과"]["한도초과"] == 0
    assert sum(a["금액"] for a in r["세무조정"] if a["소득처분"] == "대표자상여") == 2_000_000


def test_entertainment_short_year():  # 실무형: 일반법인 6개월 사업연도
    r = c("entertainment_adjustment", {"year": 2025, "sme": False, "months": 6, "revenue_general": 2_000_000_000, "revenue_related": 0,
                                        "expenses": [{"amount": 20_000_000, "evidence": "적격"}, {"amount": 1_000_000, "evidence": "영수증 등", "over_30k": True}]})
    assert r["결과"]["한도"] == 12_000_000 and r["결과"]["한도초과"] == 8_000_000
    assert sum(a["금액"] for a in r["세무조정"] if a["소득처분"] == "기타사외유출") == 9_000_000


# ── 금융소득 ─────────────────────────────────────────────────────────────────
def test_financial_2024_54():  # 공개 검증 사례: 세무사 1차 2024-54(정답 ③ 39,500,000원
    r = c("financial_income_aggregate", {"year": 2024, "items": [
        {"kind": "예금이자", "amount": 5_000_000},
        {"kind": "투자신탁환매이익", "amount": 12_000_000, "components": [
            {"asset": "채권", "gain": -3_000_000}, {"asset": "상장주식", "gain": 10_000_000}, {"asset": "비상장주식", "gain": 5_000_000}]},
        {"kind": "장내파생상품", "amount": 10_000_000},
        {"kind": "파생결합사채이익", "amount": 6_000_000},
        {"kind": "상장법인현금배당", "amount": 15_000_000},
        {"kind": "저축성보험차익", "amount": 50_000_000, "premium": 40_000_000, "payout": 50_000_000, "contract_year": 2018, "annuity": False}]})
    assert r["결과"]["이자소득금액"] == 15_000_000
    assert r["결과"]["배당소득금액"] == 24_500_000      # 23,000,000 + Gross-up 1,500,000
    assert r["결과"]["합산액"] == 39_500_000
    assert "제외" in json.dumps(find(r["판단"], "장내파생"), ensure_ascii=False)


def test_financial_2025_51():  # 공개 검증 사례: 세무사 1차 2025-51(정답 ③ 40,350,000원
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "외상매출금지급기일연장이자", "amount": 4_000_000},
        {"kind": "소비대차전환이자", "amount": 3_000_000},
        {"kind": "파생결합사채이익", "amount": 4_500_000},
        {"kind": "의제배당_잉여금자본전입", "amount": 8_000_000, "source": "주식발행초과금", "self_stock_shift": 3_500_000},
        {"kind": "의제배당_잉여금자본전입", "amount": 10_000_000, "source": "자기주식처분이익"},
        {"kind": "인정배당", "amount": 17_500_000}]})
    assert r["결과"]["이자소득금액"] == 3_000_000
    assert r["결과"]["합산액"] == 40_350_000


def test_financial_separate_under_20m():  # 실무형: 2천만 원 이하 분리과세
    r = c("financial_income_aggregate", {"year": 2024, "items": [{"kind": "예금이자", "amount": 15_000_000}]})
    assert r["결과"]["합산액"] == 0


def test_financial_grossup_order():  # 실무형: 이자 먼저 채우고 남은 구간만 Gross-up
    r = c("financial_income_aggregate", {"year": 2024, "items": [{"kind": "예금이자", "amount": 10_000_000},
                                                                    {"kind": "상장법인현금배당", "amount": 15_000_000}]})
    assert r["결과"]["합산액"] == 25_500_000


# ── 입력 엄격성 (Claude 추가 10-13 — 모델이 사실관계를 뭉뚱그려 넣은 사례) ──
def test_strict_unknown_kind_rejected():  # 사례: kind='대손금'·'외상매출금' 같은 임의 값 → 조용히 0으로 계산하던 문제
    r = c("bad_debt_adjustment", {"year": 2024, "sme": False, "book": {"opening": 0, "offset": 0, "provision": 0, "closing": 0},
                                  "receivables_prev_end_book": 1, "receivables_end_book": 1,
                                  "writeoffs": [{"kind": "대손금", "amount": 1, "arose_in": "당기"}]})
    assert "error" in r and "허용값" in r and "결과" not in r


def test_strict_missing_facts_rejected():  # 사례: 의제배당 source 없이, 투자신탁 components 없이 호출 → 잘못된 합산
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "의제배당_잉여금자본전입", "amount": 8_000_000}]})
    assert "error" in r and any("source" in p for p in r["문제"])
    r = c("financial_income_aggregate", {"year": 2024, "items": [{"kind": "투자신탁환매이익", "amount": 12_000_000}]})
    assert "error" in r and any("components" in p for p in r["문제"])


def test_strict_evidence_enum():
    r = c("entertainment_adjustment", {"year": 2024, "sme": False, "months": 12, "revenue_general": 0, "revenue_related": 0,
                                        "expenses": [{"amount": 1_000, "evidence": "카드"}]})
    assert "error" in r


# ── CodeSolar 리뷰(PR #6) 지적 회귀 테스트 (Claude 추가 10-13) ──
def test_bad_debt_memo_for_other_instrument_sme():  # 중소기업 '기타' 채권 부도6개월: 비망 1,000원이 세법상 채권에도 반영
    r = c("bad_debt_adjustment", {"year": 2025, "sme": True, "prior_excess": 0,
                                  "book": {"opening": 0, "offset": 5_000_000, "provision": 0, "closing": 0},
                                  "receivables_prev_end_book": 1_000_000_000, "receivables_end_book": 1_000_000_000,
                                  "writeoffs": [{"kind": "부도6개월", "amount": 5_000_000, "arose_in": "당기", "instrument": "기타", "months_since_default": 8, "mortgage": False}]})
    assert r["계산"]["세법상 당기 대손금"] == 4_999_000
    assert r["계산"]["세법상 당기말 채권"] == 1_000_001_000


def test_entertainment_receipt_under_threshold_counts_toward_limit():  # over_30k=True여도 금액이 기준 이하면 시부인 대상
    r = c("entertainment_adjustment", {"year": 2025, "sme": False, "months": 12, "revenue_general": 0, "revenue_related": 0,
                                        "expenses": [{"amount": 20_000, "evidence": "영수증 등", "over_30k": True},
                                                     {"amount": 150_000, "evidence": "영수증 등", "over_30k": True, "congratulatory": True}]})
    assert r["결과"]["시부인_대상"] == 170_000
    assert sum(a["금액"] for a in r["세무조정"] if a["소득처분"] == "기타사외유출" and a["구분"] == "적격증빙 미수취") == 0


# ── CodeSolar 3차 리뷰(PR #6) 회귀 테스트 (Claude 추가 10-13) ──
def test_bad_debt_small_amount_memo():  # 비망가액은 min(금액, 1,000원)
    r = c("bad_debt_adjustment", {"year": 2025, "sme": True, "prior_excess": 0,
                                  "book": {"opening": 0, "offset": 500, "provision": 0, "closing": 0},
                                  "receivables_prev_end_book": 1_000_000_000, "receivables_end_book": 1_000_000_000,
                                  "writeoffs": [{"kind": "부도6개월", "amount": 500, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 8, "mortgage": False}]})
    assert r["계산"]["세법상 당기 대손금"] == 0
    assert r["계산"]["세법상 당기말 채권"] == 1_000_000_500


def test_bad_debt_no_duplicate_judgment_and_uncollectible():  # 소멸시효 건에 '검토 필요' 중복 없음, 회수불능은 인정
    r = c("bad_debt_adjustment", {"year": 2025, "sme": False, "prior_excess": 0,
                                  "book": {"opening": 0, "offset": 3_000_000, "provision": 0, "closing": 0},
                                  "receivables_prev_end_book": 1_000_000_000, "receivables_end_book": 1_000_000_000,
                                  "writeoffs": [{"kind": "소멸시효완성", "amount": 1_000_000, "arose_in": "당기"},
                                                {"kind": "회수불능", "amount": 2_000_000, "arose_in": "당기"}]})
    assert not [j for j in r["판단"] if "검토 필요" in j.get("결론", "")]
    assert r["계산"]["세법상 당기 대손금"] == 3_000_000


def test_bad_debt_default_under_six_months_denied():  # 부도 후 6개월 미만은 부인
    r = c("bad_debt_adjustment", {"year": 2025, "sme": True, "prior_excess": 0,
                                  "book": {"opening": 0, "offset": 5_000_000, "provision": 0, "closing": 0},
                                  "receivables_prev_end_book": 1_000_000_000, "receivables_end_book": 1_000_000_000,
                                  "writeoffs": [{"kind": "부도6개월", "amount": 5_000_000, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 4, "mortgage": False}]})
    assert r["계산"]["세법상 당기 대손금"] == 0
    assert r["계산"]["세법상 당기말 채권"] == 1_005_000_000
    assert sum(a["금액"] for a in r["세무조정"] if a["소득처분"] == "유보" and "부인" in a["구분"]) == 5_000_000


def test_financial_insurance_ten_years_requires_exemption_facts():  # 10년 이상 유지 계약은 비과세 요건 사실 없이는 계산하지 않음
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "저축성보험차익", "amount": 10_000_000, "premium": 40_000_000, "payout": 50_000_000, "contract_year": 2012, "annuity": False}]})
    assert "error" in r and any("비과세" in p for p in r["문제"])
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "저축성보험차익", "amount": 10_000_000, "premium": 40_000_000, "payout": 50_000_000, "contract_year": 2012, "annuity": False, "exempt_conditions_met": True},
        {"kind": "예금이자", "amount": 25_000_000}]})
    assert r["결과"]["이자소득금액"] == 25_000_000           # 보험차익은 비과세로 제외


def test_financial_taxable_source_with_self_stock_shift():  # 과세 재원 무상주에 자기주식 미배정분이 있으면 분리
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "의제배당_잉여금자본전입", "amount": 10_000_000, "source": "이익잉여금", "self_stock_shift": 2_000_000},
        {"kind": "예금이자", "amount": 20_000_000}]})
    k = r["계산"]
    assert k["배당(Gross-up 대상)"] == 8_000_000 and k["배당(Gross-up 비대상)"] == 2_000_000


def test_excluded_source_requires_self_stock_shift():  # Claude 10-13 (24회차 2025-51): 과세 제외 재원이면 자기주식 미배정 상승분을 명시해야 계산
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "의제배당_잉여금자본전입", "amount": 8_000_000, "source": "주식발행초과금"}]})
    assert "error" in r and any("self_stock_shift" in p for p in r["문제"])
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "소비대차전환이자", "amount": 3_000_000}, {"kind": "외상매출금지급기일연장이자", "amount": 4_000_000},
        {"kind": "파생결합사채이익", "amount": 4_500_000},
        {"kind": "의제배당_잉여금자본전입", "amount": 8_000_000, "source": "주식발행초과금", "self_stock_shift": 3_500_000},
        {"kind": "의제배당_잉여금자본전입", "amount": 10_000_000, "source": "자기주식처분이익"},
        {"kind": "인정배당", "amount": 17_500_000}]})
    assert r["결과"]["합산액"] == 40_350_000       # 공개 검증 사례 2025-51 정답 ③


def test_components_wrong_shape_rejected():  # Claude 10-14 (25회차 2024-54): dict 형태 components는 크래시 대신 형식 안내
    r = c("financial_income_aggregate", {"year": 2024, "items": [{"kind": "투자신탁환매이익", "amount": 12_000_000, "components": {"코스닥상장법인주식양도차익": 10_000_000}}]})
    assert "error" in r and "예시" in r


def test_result_key_comes_first():  # 25회차 2025-76: 모델이 판단 목록만 읽고 재계산 → 결과를 맨 앞에
    r = c("simplified_vat_return", {"year": 2025, "business_type": "음식점업", "supplies": {"total": 60_000_000}, "purchases": {}, "prior_year_supplies": 50_000_000, "prepaid_assessed": 0})
    assert list(r.keys())[0] == "결과"
