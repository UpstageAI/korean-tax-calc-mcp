"""계산기 사용 정돈 정답 테스트 — 원장형 입력·세무조정 출력·계산기 연결 (Claude 작성 2026-10-14) — 수정 금지.
공개 검증 사례는 원문 사실관계를 원장 항목 그대로 넣고
법인세법 제25조·영 제40조②·제42조①⑥, 부가가치세법 제46조①·제63조·영 제61조②9호·제64조·제81조~제83조로 손계산해 공개 정답과 일치 확인.
실무형 사례는 Claude 손계산. 이 사례들은 도구 설계의 기준이 아니라 검증용이다.
실행: .venv/bin/python -m pytest tests/test_e2e6_golden.py -q
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp
from tests._legacy_to_ledger import to_ledger   # 0.9.0: 옛 입력은 테스트에서 원장형으로 변환해 호출


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, to_ledger(n, a))).content[0].text)


def find(judg, word):
    return [j for j in judg if word in json.dumps(j, ensure_ascii=False)]


# ── A. 세무조정 출력 통일 ──────────────────────────────────────────────────────
def test_2024_65_totals_by_disposition():   # 공개 사례 2024-65: 대표자상여 8,000,000 / 기타사외유출 6,000,000 + 6,350,000 = 12,350,000
    r = c("entertainment_adjustment", {
        "year": 2024, "sme": False, "months": 12, "revenue_general": 7_500_000_000, "revenue_related": 4_500_000_000,
        "expenses": [{"amount": 8_000_000, "evidence": "없음"},
                     {"amount": 6_000_000, "evidence": "영수증 등", "over_30k": True},
                     {"amount": 42_000_000, "evidence": "적격"}]})
    res = r["결과"]
    assert list(res)[:3] == ["세무조정", "소득처분별_합계", "손금불산입_합계"]
    assert res["소득처분별_합계"] == {"대표자상여": 8_000_000, "기타사외유출": 12_350_000}
    assert res["손금불산입_합계"] == 20_350_000
    assert len(res["세무조정"]) == 3 and sum(a["금액"] for a in res["세무조정"]) == 20_350_000
    assert res["한도"] == 35_650_000 and res["한도초과"] == 6_350_000       # 기존 키 유지


def test_bad_debt_totals_by_disposition():   # 공개 사례 2024-66 입력 그대로: 유보 합계와 △유보(전기 한도초과 손금산입)
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
    res = r["결과"]
    assert list(res)[:3] == ["세무조정", "소득처분별_합계", "손금불산입_합계"]
    유보 = sum(a["금액"] for a in res["세무조정"] if a["소득처분"] == "유보")
    assert res["소득처분별_합계"]["유보"] == 유보 and res["소득처분별_합계"]["△유보"] == 20_000_000
    assert res["손금불산입_합계"] == 유보 and 81_674_945 <= 유보
    assert res["한도초과"] == 81_674_945                                           # 기존 키 유지


# ── B1. 기업업무추진비 원장형 입력 ───────────────────────────────────────────
def test_2026_62_ledger_forward():   # 공개 사례 2026-62: 교제목적 광고비·직원단체(법인) 복리시설비·현물 시가 포함, 특수관계 매출할인 차감 → 한도 64,760,000·초과 25,240,000
    r = c("entertainment_adjustment", {
        "year": 2026, "sme": False, "months": 12,
        "revenue": {"매출액": 25_000_000_000, "특수관계매출": 4_000_000_000, "매출할인등": {"특수관계": 200_000_000}},
        "ledger": [
            {"항목": "기업업무추진비(귀속불분명·증빙 없음)", "금액": 7_000_000, "증빙": "없음"},
            {"항목": "기업업무추진비", "금액": 50_000_000, "증빙": "적격"},
            {"항목": "광고비 — 매출거래처 (주)B 교제 목적", "금액": 13_000_000, "증빙": "적격", "성격": "교제목적"},
            {"항목": "복리후생비 — 직원이 조직한 법인 단체 복리시설비", "금액": 12_000_000, "증빙": "적격", "성격": "직원단체_법인"},
            {"항목": "제품 사례 제공(영업외비용)", "성격": "현물", "시가": 15_000_000, "장부가액": 11_000_000},
        ]})
    res, k = r["결과"], r["계산"]
    assert res["한도"] == 64_760_000 and k["시부인 대상"] == 90_000_000 and res["한도초과"] == 25_240_000
    assert res["소득처분별_합계"] == {"대표자상여": 7_000_000, "기타사외유출": 25_240_000}
    assert res["손금불산입_합계"] == 32_240_000
    assert "제40조" in json.dumps(find(r["판단"], "복리후생비"), ensure_ascii=False)
    assert "포함" in json.dumps(find(r["판단"], "광고비"), ensure_ascii=False)


def test_ledger_exclusions_and_in_kind_valuation():   # 실무형: 비법인 직원단체 복리시설비·임직원 부담분은 제외, 현물은 시가·장부가액 중 큰 금액
    r = c("entertainment_adjustment", {
        "year": 2026, "sme": False, "months": 12, "revenue": {"매출액": 1_000_000_000},
        "ledger": [
            {"항목": "복리시설비 — 직원 친목회(비법인)", "금액": 5_000_000, "증빙": "적격", "성격": "직원단체_비법인"},
            {"항목": "임원 개인 접대 대납", "금액": 2_000_000, "증빙": "적격", "성격": "임직원부담"},
            {"항목": "제품 제공", "성격": "현물", "시가": 3_000_000, "장부가액": 4_000_000},
        ]})
    res, k = r["결과"], r["계산"]
    assert k["시부인 대상"] == 4_000_000 and res["한도"] == 15_000_000 and res["한도초과"] == 0
    assert res["손금불산입_합계"] == 0
    excluded = [j for j in r["판단"] if j.get("결론", "").startswith("제외")]
    assert len(excluded) == 2 and all(j.get("근거") for j in excluded)


def test_revenue_dict_with_expenses():   # 공개 사례 2024-65를 revenue(매출액·특수관계매출)로: expenses와 같이 써도 수입금액 한도가 적용돼야
    r = c("entertainment_adjustment", {
        "year": 2024, "sme": False, "months": 12, "revenue": {"매출액": 12_000_000_000, "특수관계매출": 4_500_000_000},
        "expenses": [{"amount": 8_000_000, "evidence": "없음"},
                     {"amount": 6_000_000, "evidence": "영수증 등", "over_30k": True},
                     {"amount": 42_000_000, "evidence": "적격"}]})
    assert r["결과"]["한도"] == 35_650_000 and r["결과"]["한도초과"] == 6_350_000
    assert r["결과"]["소득처분별_합계"] == {"대표자상여": 8_000_000, "기타사외유출": 12_350_000}


def test_ledger_missing_values():
    base = {"year": 2026, "sme": False, "months": 12, "revenue": {"매출액": 1_000_000_000}}
    r = c("entertainment_adjustment", {**base, "ledger": []})
    assert "error" in r                                                                  # 원장 항목 없음(0.9.0: ledger가 유일한 지출 입력)
    r = c("entertainment_adjustment", {**base, "ledger": [{"항목": "현물", "성격": "현물"}]})
    assert "error" in r                                                                  # 현물인데 시가·장부가액 없음
    r = c("entertainment_adjustment", {"year": 2026, "sme": False, "months": 12,
                                       "revenue": {"매출액": 100, "특수관계매출": 50, "매출할인등": {"특수관계": 80}},
                                       "ledger": [{"항목": "x", "금액": 1_000}]})
    assert "error" in r                                                                  # 수입금액 음수


# ── B2. 간이과세 원장형 입력 ─────────────────────────────────────────────────
def test_2025_76_ledger():   # 공개 사례 2025-76: 신용카드 55,000,000 + 현금영수증 25,000,000 = 80,000,000 × 1.3% = 1,040,000 → 차가감 366,000
    r = c("simplified_vat_return", {
        "year": 2025, "business_type": "음식점업", "prior_year_supplies": 75_000_000,
        "ledger": {"공급": [{"항목": "신용카드매출전표 발급분", "금액": 55_000_000},
                           {"항목": "현금영수증 발급분", "금액": 25_000_000},
                           {"항목": "영수증 발급분", "금액": 18_500_000},
                           {"항목": "자기적립마일리지 결제분", "금액": 1_000_000}],
                   "매입": [{"항목": "세금계산서 수취분 식재료(부가가치세 포함)", "금액": 16_500_000},
                           {"항목": "계산서 수취분 식재료", "금액": 29_000_000},
                           {"항목": "세금계산서 미수취분 식재료(발급의무자로부터 매입)", "금액": 2_200_000}]}})
    k = r["계산"]
    assert k["과세표준"] == 98_500_000 and k["납부세액"] == 1_477_500
    assert k["세금계산서등수취세액공제"] == 82_500 and k["신용카드매출전표등발급세액공제"] == 1_040_000
    assert k["세금계산서미수취가산세"] == 11_000
    assert r["결과"]["차가감납부세액"] == 366_000


def test_simplified_ledger_unknown_item_refused():
    r = c("simplified_vat_return", {
        "year": 2025, "business_type": "음식점업", "prior_year_supplies": 75_000_000,
        "ledger": {"공급": [{"항목": "알 수 없는 항목", "금액": 1_000_000}], "매입": []}})
    assert "error" in r and "허용값" in r and "자기적립마일리지" in json.dumps(r["허용값"], ensure_ascii=False)
    r = c("simplified_vat_return", {
        "year": 2025, "business_type": "음식점업", "prior_year_supplies": 75_000_000,
        "ledger": {"공급": [], "매입": []}})
    assert "error" in r                                                                  # 공급 항목 없음


# ── B3. 공통매입세액 원장형 입력 ─────────────────────────────────────────────
def test_2024_76_ledger():   # 공개 사례 2024-76: 배송료는 횟수(70:30)로 실지귀속, 나머지 공통 안분·정산 → 공제매입세액 1,030,000
    r = c("common_input_tax", {
        "year": 2024, "period": "1기", "filing": "확정",
        "supplies": {"예정": {"taxable": 400_000_000, "exempt": 600_000_000}, "확정": {"taxable": 200_000_000, "exempt": 800_000_000}},
        "ledger": [{"항목": "상품 포장지", "매입가액": 7_000_000, "사용처": "과세"},
                   {"항목": "냉장고", "매입가액": 8_000_000, "사용처": "면세"},
                   {"항목": "임차료", "매입가액": 10_000_000, "사용처": "공통"},
                   {"항목": "전기료", "매입가액": 2_000_000, "사용처": "공통"},
                   {"항목": "배송료(회당 10,000원 × 100회)", "매입가액": 1_000_000, "사용처": "실지귀속", "횟수": {"과세": 70, "면세": 30}}],
        "prior_common_input_tax": 1_000_000, "prior_nondeductible": 600_000})
    k = r["계산"]
    assert k["실지귀속_공제"] == 70_000 and k["공통매입세액_과세기간합계"] == 2_200_000
    assert k["불공제_확정"] == 940_000 and k["공통매입세액_공제"] == 260_000
    assert r["결과"]["공제매입세액"] == 1_030_000


def test_common_ledger_validation():
    base = {"year": 2024, "period": "1기", "filing": "예정",
            "supplies": {"예정": {"taxable": 400_000_000, "exempt": 600_000_000}, "확정": None}}
    r = c("common_input_tax", {**base, "ledger": [{"항목": "배송료", "매입세액": 100_000, "사용처": "실지귀속"}]})
    assert "error" in r                                                                  # 실지귀속인데 비율·횟수·면적 없음
    r = c("common_input_tax", {**base, "ledger": [{"항목": "임차료", "사용처": "공통"}]})
    assert "error" in r                                                                  # 금액 없음
    r = c("common_input_tax", {**base, "ledger": []})
    assert "error" in r                                                                  # 원장 항목 없음
    r = c("common_input_tax", {**base, "ledger": [{"항목": "임차료", "매입세액": 1_000_000, "사용처": "공통"},
                                                  {"항목": "접대비", "매입세액": 50_000, "사용처": "불공제"}]})
    assert r["계산"]["공통매입세액_공제"] == 400_000 and r["결과"]["공제매입세액"] == 400_000


# ── B4. 재계산 ← 일괄공급 안분 연결 ─────────────────────────────────────────
def test_2025_71_bundle_to_recalculation():   # 공개 사례 2025-71: 762,600,000(부가세 포함) 감정가 432:244.8 → 건물 457,560,000·매입세액 45,756,000 → 45,756,000 × (1 − 5%×5) × 6%p = 2,059,020
    r = c("input_tax_recalculation", {
        "asset_type": "건물·구축물",
        "bundle": {"total_price": 762_600_000, "vat_included": True, "appraisal": {"building": 432_000_000, "land": 244_800_000}},
        "acquired": {"year": 2022, "period": "2기"},
        "ratios": [{"year": 2022, "period": "2기", "exempt_ratio": 0.50}, {"year": 2023, "period": "1기", "exempt_ratio": 0.54},
                   {"year": 2023, "period": "2기", "exempt_ratio": 0.45}, {"year": 2024, "period": "1기", "exempt_ratio": 0.49},
                   {"year": 2024, "period": "2기", "exempt_ratio": 0.44}, {"year": 2025, "period": "1기", "exempt_ratio": 0.51}]})
    assert r["결과"]["건물_매입세액"] == 45_756_000
    assert r["결과"]["당기_납부세액_가산"] == 2_059_020
    assert "감정평가" in json.dumps(r.get("판단", []), ensure_ascii=False)
    last = r["이력"][-1]
    assert last["기준비율"] == 0.45 and last["경과과세기간수"] == 5 and last["재계산"] is True


def test_bundle_conflicts():
    base = {"asset_type": "건물·구축물", "acquired": {"year": 2022, "period": "2기"},
            "ratios": [{"year": 2022, "period": "2기", "exempt_ratio": 0.5}, {"year": 2023, "period": "1기", "exempt_ratio": 0.6}]}
    r = c("input_tax_recalculation", {**base, "input_tax": 1_000_000,
                                      "bundle": {"total_price": 1_000_000, "vat_included": True, "appraisal": {"building": 1, "land": 1}}})
    assert "error" in r
    r = c("input_tax_recalculation", {**base, "bundle": {"total_price": 1_000_000, "vat_included": True}})
    assert "error" in r                                                                  # 안분 기준 없음
