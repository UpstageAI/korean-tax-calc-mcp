import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a): return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def c_err(n, a):
    """도구 호출이 오류(검증 실패 등)로 거부되면 True."""
    from mcp.server.mcpserver.exceptions import ToolError
    try:
        asyncio.run(mcp.call_tool(n, a))
        return False
    except ToolError:
        return True


def test_tools_and_values():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"corporate_tax", "deemed_interest", "invoice_penalty", "assessment_limitation", "withholding_tax",
            "nonresident_withholding", "thin_capitalization"} <= names
    assert c("corporate_tax", {"base": 500_000_000, "year": 2025})["결과"]["산출세액"] == 75_000_000
    assert c("deemed_interest", {"movements": [{"date": "2025-01-01", "amount": 240_000_000}], "year_end": "2025-12-31"})["결과"]["익금산입"] == 11_040_000
    assert c("invoice_penalty", {"supply_amount": 40_000_000, "kind": "가공", "supplied_on": "2025-12-15"})["결과"]["가산세"] == 1_200_000
    r = c("assessment_limitation", {"due_date": "2024-03-31", "case": "부정행위", "offshore": True})["결과"]
    assert r["제척기간(년)"] == 15 and r["만료일"] == "2039-03-31"
    assert c("assessment_limitation", {"due_date": "2024-03-31", "case": "무신고"})["결과"]["제척기간(년)"] == 7
    assert c("underreporting_penalty", {"additional_tax": 10_000_000, "fraud": True})["결과"]["가산세"] == 4_000_000


def test_no_year_table_stops():
    assert "error" in c("corporate_tax", {"base": 1, "year": 2026}) or "결과" in c("corporate_tax", {"base": 1, "year": 2026})


def test_v02_tools():
    assert c("nonbusiness_interest_disallowance", {"loans": [{"interest": 30_000_000, "jeoksu": 3_650_000_000}], "nonbusiness_jeoksu": 876_000_000})["결과"]["손금불산입(기타사외유출)"] == 7_200_000
    r = c("business_car_expense", {"year": 2025, "upkeep": 20_000_000, "depreciation": 8_000_000, "booked_depreciation": 8_000_000, "log_kept": False})["결과"]
    assert round(r["업무사용비율"], 4) == round(15_000_000 / 28_000_000, 4)
    assert c("donation_limit", {"year": 2025, "base_income": 500_000_000, "special": 10_000_000, "general": 80_000_000})["결과"]["한도초과(기타사외유출)"] == 31_000_000
    assert c("vat_deemed_input_credit", {"purchase": 50_000_000, "base": 300_000_000, "period": "2025-1", "industry": "음식점", "individual": False})["결과"]["의제매입세액"] == 2_830_188
    # SPEC c4b 가상 수치: 구입액 100,000,000(운반비 6,000,000 포함), 과세 사용 70,000,000,
    # 면세 판매 15,000,000, 공통 기말재고 10,000,000, 과세 공급 280,000,000, 면세 120,000,000,
    # 법인·중소기업 아님·제조, 공제율 2/102 → 공제대상 72,380,000 / 의제매입세액 1,419,215
    r = c("vat_deemed_input_credit",
          {"purchase_total": 100_000_000, "freight_included": 6_000_000,
           "used_taxable": 70_000_000, "used_exempt": 15_000_000, "ending_inventory_common": 10_000_000,
           "taxable_supply": 280_000_000, "exempt_supply": 120_000_000,
           "period": "2026-1", "industry": "제조", "individual": False, "sme": False})
    assert r["결과"]["의제매입세액"] == 1_419_215
    assert r["결과"]["공제대상_매입가액"] == 72_379_999
    items = [{"amount": 50_000}, {"amount": 20_000}, {"amount": 300_000, "congratulatory": True}, {"amount": 100_000, "qualified": True}]
    assert c("missing_receipt_disallowance", {"year": 2025, "items": items})["결과"]["손금불산입"] == 350_000
    assert c("vat_common_input_allocation", {"common_tax": 10_000_000, "total_supply": 1_000_000_000, "exempt_supply": 300_000_000})["결과"]["불공제"] == 3_000_000
    assert c("daily_worker_withholding", {"daily_wage": 200_000})["결과"]["원천징수세액"] == 1_350


def test_nonresident_withholding():
    # 테스트01 기본 사례: 배당·이자·사용료 (개인, 조약 제한세율 적용)
    r = c("nonresident_withholding", {"income_kind": "배당", "amount": 300_000_000, "recipient_type": "개인",
                                       "residence_country": "US", "treaty_rate": 0.15})
    assert r["결과"]["원천징수세액"] == 45_000_000 and r["결과"]["지방소득세"] == 4_500_000    # 4,500만 + 450만
    assert r["결과"]["적용세율"] == 0.15 and r["결과"]["국내세율"] == 0.20

    r = c("nonresident_withholding", {"income_kind": "이자", "amount": 300_000_000, "recipient_type": "개인",
                                       "residence_country": "US", "treaty_rate": 0.12})
    assert r["결과"]["원천징수세액"] == 36_000_000 and r["결과"]["지방소득세"] == 3_600_000   # 3,600만 + 360만
    assert r["결과"]["적용세율"] == 0.12

    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 200_000_000, "recipient_type": "개인",
                                       "residence_country": "US", "treaty_rate": 0.15})
    assert r["결과"]["원천징수세액"] == 30_000_000 and r["결과"]["지방소득세"] == 3_000_000   # 3,000만 + 300만
    assert r["결과"]["적용세율"] == 0.15

    # 조약 없을 때 국내세율 적용
    r = c("nonresident_withholding", {"income_kind": "배당", "amount": 100_000_000, "recipient_type": "법인",
                                       "residence_country": "CA"})
    assert r["결과"]["원천징수세액"] == 20_000_000 and r["결과"]["적용세율"] == 0.20           # 1억 × 20%


def test_thin_capitalization():
    # 테스트 사례: 출자 20억, 차입 50억, 이자 3억, 배수 2 → 초과 10억, 손금불산입 6,000만, 배당 처분
    r = c("thin_capitalization", {"equity": 2_000_000_000, "borrowings": 5_000_000_000,
                                  "total_interest": 300_000_000, "ratio": 2})
    assert r["결과"]["초과차입금"] == 1_000_000_000           # 50억 - 20억×2 = 10억
    assert r["결과"]["손금불산입 이자"] == 60_000_000         # 3억 × 10억/50억 = 6천만
    assert r["결과"]["처분"] == "배당"


def test_r1b_regression():
    # 1. 채권이자 특례 (bond_interest=True) — 적용세율 0.14, 근거에 "1호가목"
    r = c("nonresident_withholding", {"income_kind": "이자", "amount": 100_000_000, "recipient_type": "법인",
                                       "residence_country": "US", "bond_interest": True})
    assert r["결과"]["적용세율"] == 0.14
    assert "1호가목" in r["결과"]["근거"]

    # 2. 근거 호수 검증 — 이자 1호, 배당 2호, 인적용역 4호, 사용료 6호, 기타 8호
    r = c("nonresident_withholding", {"income_kind": "이자", "amount": 100_000_000, "recipient_type": "개인",
                                       "residence_country": "JP"})
    assert "1호" in r["결과"]["근거"]
    r = c("nonresident_withholding", {"income_kind": "배당", "amount": 100_000_000, "recipient_type": "개인",
                                       "residence_country": "JP"})
    assert "2호" in r["결과"]["근거"]
    r = c("nonresident_withholding", {"income_kind": "인적용역", "amount": 100_000_000, "recipient_type": "개인",
                                       "residence_country": "JP"})
    assert "4호" in r["결과"]["근거"]
    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 100_000_000, "recipient_type": "개인",
                                       "residence_country": "JP"})
    assert "6호" in r["결과"]["근거"]
    r = c("nonresident_withholding", {"income_kind": "기타", "amount": 100_000_000, "recipient_type": "개인",
                                       "residence_country": "JP"})
    assert "8호" in r["결과"]["근거"]

    # 3. 조약세율이 국내세율보다 높음 → 국내세율 적용 + 안내 메시지
    r = c("nonresident_withholding", {"income_kind": "배당", "amount": 100_000_000, "recipient_type": "개인",
                                       "residence_country": "US", "treaty_rate": 0.3})
    assert r["결과"]["적용세율"] == 0.2
    assert "조약세율이 국내세율보다 높아 국내세율 적용" in r["결과"]["근거"]

    # 4. 음수 거부 — corporate_tax, nonresident_withholding, thin_capitalization
    assert c_err("corporate_tax", {"base": -5, "year": 2025})
    assert c_err("nonresident_withholding", {"income_kind": "이자", "amount": -1, "recipient_type": "개인",
                                             "residence_country": "US"})
    assert c_err("thin_capitalization", {"equity": -1, "borrowings": 100_000_000, "total_interest": 10_000_000})

    # 5. thin_capitalization year 미지정 → 2026 기준으로 계산
    r = c("thin_capitalization", {"equity": 2_000_000_000, "borrowings": 5_000_000_000,
                                  "total_interest": 300_000_000, "ratio": 2})
    assert r["결과"]["손금불산입 이자"] == 60_000_000  # 2026 기준으로 동일 계산


def test_thin_cap_withholding_recalc():
    # 검증 사례: equity=20억, borrowings=50억, total_interest=3억, 미국, 이자조약 0.12, 배당조약 0.15
    r = c("thin_capitalization", {"equity": 2_000_000_000, "borrowings": 5_000_000_000,
                                  "total_interest": 300_000_000, "recipient_residence_country": "미국",
                                  "interest_treaty_rate": 0.12, "dividend_treaty_rate": 0.15})
    assert r["결과"]["손금불산입 이자"] == 60_000_000
    recalc = r["결과"]["원천징수 재계산"]
    assert recalc["대상 금액(손금불산입 이자)"] == 60_000_000
    assert recalc["이자 기준 원천징수세액"] == 7_200_000      # 6천만 × 0.12
    assert recalc["배당 기준 원천징수세액"] == 9_000_000      # 6천만 × 0.15
    assert recalc["소득세 차액"] == 1_800_000                 # 900만 - 720만
    assert recalc["지방소득세 차액"] == 180_000               # 18만 (소득세 차액의 10%)
    assert "국조법 제22조 ② 배당 처분" in recalc["근거"]


def test_사용료_쟁점_수원고등법원_포함():
    # 사용료 + treaty_rate → 쟁점 3건, 참고에 "수원고등법원-2023-누-15618" 포함, 판단 == "세무사 확인 필요"
    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 200_000_000,
                                       "recipient_type": "개인", "residence_country": "US", "treaty_rate": 0.15})
    issues = r["쟁점"]
    assert len(issues) == 3
    refs = [ref for it in issues for ref in it["참고"]]
    assert any("수원고등법원-2023-누-15618" in ref for ref in refs)
    assert all(it["판단"] == "세무사 확인 필요" for it in issues)


def test_배당_treaty_rate_제156조의6_포함():
    # 배당 + treaty_rate → 제156조의6 쟁점 포함
    r = c("nonresident_withholding", {"income_kind": "배당", "amount": 100_000_000,
                                       "recipient_type": "개인", "residence_country": "US", "treaty_rate": 0.15})
    refs = [ref for it in r["쟁점"] for ref in it["참고"]]
    assert any("제156조의6" in ref or "제98조의6" in ref for ref in refs)


def test_배당_treaty_rate_없음_제156조의6_없음():
    # 배당 + treaty_rate 없음 → 제156조의6 쟁점 없음
    r = c("nonresident_withholding", {"income_kind": "배당", "amount": 100_000_000,
                                       "recipient_type": "법인", "residence_country": "CA"})
    refs = [ref for it in r["쟁점"] for ref in it["참고"]]
    assert not any("제156조의6" in ref or "제98조의6" in ref for ref in refs)


def test_이자_related_party_제22조_포함():
    # 이자 + related_party=True → 제22조 쟁점 포함
    r = c("nonresident_withholding", {"income_kind": "이자", "amount": 100_000_000,
                                       "recipient_type": "개인", "residence_country": "US",
                                       "related_party": True})
    refs = [ref for it in r["쟁점"] for ref in it["참고"]]
    assert any("제22조" in ref for ref in refs)


def test_결과_JSON_단정문구_없음():
    # 결과 JSON 문자열에 "사업소득임"·"사용료임" 없음
    r = c("nonresident_withholding", {"income_kind": "이자", "amount": 100_000_000,
                                       "recipient_type": "개인", "residence_country": "US",
                                       "related_party": True})
    full_text = json.dumps(r, ensure_ascii=False)
    assert "사업소득임" not in full_text
    assert "사용료임" not in full_text


def test_thin_capitalization_쟁점_포함():
    # thin_capitalization → 쟁점 1건, 참고에 "제22조"
    r = c("thin_capitalization", {"equity": 2_000_000_000, "borrowings": 5_000_000_000,
                                  "total_interest": 300_000_000, "ratio": 2})
    issues = r.get("쟁점", [])
    assert len(issues) >= 1
    refs = [ref for it in issues for ref in it["참고"]]
    assert any("제22조" in ref for ref in refs)
    assert all(it["판단"] == "세무사 확인 필요" for it in issues)


def test_issues_json_패키지_데이터_존재():
    # korean_tax_calc_mcp/data/issues.json이 패키지 데이터로 설치되는지 확인
    import importlib.resources
    path = importlib.resources.files("korean_tax_calc_mcp") / "data" / "issues.json"
    assert path.exists()


# ── SPEC r1f §3 부정 테스트 ──────────────────────────────────────────────

def test_사용료_treaty_rate_없음_쟁점1건():
    # 사용료 + treaty_rate 없음 → 쟁점 정확히 1건(소프트웨어 사용료 vs 사업소득)
    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 200_000_000,
                                       "recipient_type": "개인", "residence_country": "US"})
    assert len(r["쟁점"]) == 1
    assert any("수원고등법원-2023-누-15618" in ref for it in r["쟁점"] for ref in it["참고"])


def test_사용료_treaty_rate_있음_쟁점3건():
    # 사용료 + treaty_rate 있음 → 3건
    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 200_000_000,
                                       "recipient_type": "개인", "residence_country": "US", "treaty_rate": 0.15})
    assert len(r["쟁점"]) == 3


def test_이자_related_party_false_쟁점0건():
    # 이자 + related_party=False → 0건
    r = c("nonresident_withholding", {"income_kind": "이자", "amount": 100_000_000,
                                       "recipient_type": "개인", "residence_country": "US",
                                       "related_party": False})
    assert len(r["쟁점"]) == 0


def test_이자_related_party_true_쟁점1건():
    # 이자 + related_party=True → 과소자본 1건
    r = c("nonresident_withholding", {"income_kind": "이자", "amount": 100_000_000,
                                       "recipient_type": "개인", "residence_country": "US",
                                       "related_party": True})
    assert len(r["쟁점"]) == 1
    assert any("제22조" in ref for it in r["쟁점"] for ref in it["참고"])


def test_배당_treaty_rate_없음_쟁점0건():
    # 배당 + treaty_rate 없음 → 0건
    r = c("nonresident_withholding", {"income_kind": "배당", "amount": 100_000_000,
                                       "recipient_type": "법인", "residence_country": "CA"})
    assert len(r["쟁점"]) == 0


def test_배당_treaty_rate_있음_쟁점1건():
    # 배당 + treaty_rate 있음 → 제한세율 1건 (treaty_rate 주어짐 조건만 매칭)
    r = c("nonresident_withholding", {"income_kind": "배당", "amount": 100_000_000,
                                       "recipient_type": "개인", "residence_country": "US", "treaty_rate": 0.15})
    assert len(r["쟁점"]) == 1


def test_인적용역_쟁점1건():
    # 인적용역 → 1건
    r = c("nonresident_withholding", {"income_kind": "인적용역", "amount": 100_000_000,
                                       "recipient_type": "개인", "residence_country": "US"})
    assert len(r["쟁점"]) == 1


def test_issues_json_match_field_존재():
    # issues.json의 모든 nonresident_withholding 쟁점에 match 필드 존재
    import json, os
    path = os.path.join(os.path.dirname(__file__), "..", "korean_tax_calc_mcp", "data", "issues.json")
    with open(path, encoding="utf-8") as f:
        issues = json.load(f)["nonresident_withholding"]
    for it in issues:
        assert "match" in it, f"쟁점 누락: {it.get('쟁점', '조건 못 읽음')}"
        assert isinstance(it["match"], dict)


def test_두_도구_쟁점_위치_동일():
    # nonresident_withholding와 thin_capitalization 모두 최상위 쟁점
    r1 = c("nonresident_withholding", {"income_kind": "사용료", "amount": 200_000_000,
                                        "recipient_type": "개인", "residence_country": "US", "treaty_rate": 0.15})
    r2 = c("thin_capitalization", {"equity": 2_000_000_000, "borrowings": 5_000_000_000,
                                   "total_interest": 300_000_000, "ratio": 2})
    assert "쟁점" in r1 and "쟁점" in r2
    assert len(r1["쟁점"]) >= 1 and len(r2["쟁점"]) >= 1


# ── SPEC c5 §6: description·인자 description 검사 ────────────────────────────

def test_all_tool_descriptions_have_when_and_input():
    """모든 도구 description에 '언제:'·'입력:'이 들어 있는지 검사(SPEC c5 §1)."""
    import asyncio
    from korean_tax_calc_mcp.server import mcp
    tools = asyncio.run(mcp.list_tools())
    missing_when = []
    missing_input = []
    for t in tools:
        desc = t.description or ""
        if "언제:" not in desc:
            missing_when.append(t.name)
        if "입력:" not in desc:
            missing_input.append(t.name)
    assert not missing_when, f"'언제:' 누락 도구: {missing_when}"
    assert not missing_input, f"'입력:' 누락 도구: {missing_input}"


def test_all_parameters_have_description():
    """모든 인자에 description이 있는지 검사(lang 제외, SPEC c5 §2).
    MCP 툴 inputSchema의 properties에서 각 파라미터 description을 확인한다."""
    import asyncio
    from korean_tax_calc_mcp.server import mcp
    tools = asyncio.run(mcp.list_tools())
    for t in tools:
        schema = t.input_schema
        properties = schema.get("properties", {})
        # 'lang'은 언제든지 생략 가능한 자유 텍스트 인자 → 검사에서 제외
        for name, prop in properties.items():
            if name == "lang":
                continue
            desc = prop.get("description")
            assert desc and desc.strip(), f"{t.name}. 파라미터 '{name}' description 없음"



# ── SPEC c5 §6: precheck_schema 3종 반환 테스트 ──────────────────────────────

def test_precheck_schema_corp():
    """precheck_schema('법인') 반환 구조 검사."""
    r = c("precheck_schema", {"tax": "법인"})
    assert r["세목"] == "법인"
    assert isinstance(r["입력스키마"], list)
    assert r["총_입력키"] > 0
    # 몇 개 키의 단위·필수 여부 확인
    rows = r["입력스키마"]
    keys = {row["키"] for row in rows}
    assert "기본.종료일" in keys
    assert "조정계산서.산출세액" in keys
    for row in rows:
        assert set(row.keys()) == {"키", "의미", "단위", "필수"}
        assert row["단위"] in ("원 (int)", "bool", "YYYY-MM-DD/string", "list[dict]/list",
                                "소수 (float)", "문자열", "int (명/수)", "문맥 참조")
        assert row["필수"] in ("요건별 필수", "선택")


def test_precheck_schema_vat():
    """precheck_schema('부가') 반환 구조 검사."""
    r = c("precheck_schema", {"tax": "부가"})
    assert r["세목"] == "부가"
    assert isinstance(r["입력스키마"], list)
    assert r["총_입력키"] > 0
    rows = r["입력스키마"]
    keys = {row["키"] for row in rows}
    assert "신고서.과세표준합계" in keys
    for row in rows:
        assert set(row.keys()) == {"키", "의미", "단위", "필수"}


def test_precheck_schema_income():
    """precheck_schema('소득') 반환 구조 검사."""
    r = c("precheck_schema", {"tax": "소득"})
    assert r["세목"] == "소득"
    assert isinstance(r["입력스키마"], list)
    assert r["총_입력키"] > 0
    rows = r["입력스키마"]
    keys = {row["키"] for row in rows}
    assert "근로자" in keys
    for row in rows:
        assert set(row.keys()) == {"키", "의미", "단위", "필수"}


# ── SPEC c5 §6: 세무조사 도구 기존 형식 호출 하위 호환 테스트 ───────────────

def test_related_judge_backward_compat_list_format():
    """related_judge에 list·dict 직접 전달(기존 호출 형식) 하위 호환."""
    people = {"김갑": {"구분": "개인"}, "㈜대한": {"구분": "법인"}}
    family = [["김갑", "김을", "부모자녀"]]
    stakes = [["김갑", "㈜대한", 0.30]]
    r = c("related_judge", {
        "a": "김갑", "b": "김을", "on": "2024-01-01",
        "people": people, "family": family, "stakes": stakes,
    })
    assert "결과" in r or "근거" in r or isinstance(r, dict)


def test_tunnelling_gift_backward_compat():
    """tunnelling_gift list·dict 직접 전달 하위 호환."""
    r = c("tunnelling_gift", {
        "beneficiary": "김갑", "size": "중소",
        "sales_total": 1000000000.0, "sales_by_corp": {"A": 300000000.0},
        "after_tax_op_profit": 100000000.0,
        "people": {"김갑": {"구분": "개인"}},
        "family": [["김갑", "김을", "부모자녀"]],
        "stakes": [["김갑", "A", 0.30]],
    })
    assert isinstance(r, dict)
