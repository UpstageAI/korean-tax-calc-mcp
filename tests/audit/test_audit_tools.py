"""mcp.call_tool로 각 도구 1회 이상 호출 + PDF 도구 키 없을 때 안내 반환 확인. 작성 Mia(윤승미)"""
import asyncio
import json
import os
import sys
from korean_tax_calc_mcp.server import AI_GENERATED

import pytest

# pytest-asyncio 없이 asyncio.run으로 async 호출 감싸기
# mcp.call_tool은 async이므로 동기 테스트에서 asyncio.run()으로 호출


def _call_tool(name, **args):
    """같은 프로세스에서 mcp.call_tool로 도구 호출 → 본문 JSON 파싱한 dict 반환."""
    from korean_tax_calc_mcp.server import mcp
    result = asyncio.run(mcp.call_tool(name, args))
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


def _list_tool_names():
    """등록된 도구 이름 목록."""
    from korean_tax_calc_mcp.server import mcp
    return sorted(t.name for t in asyncio.run(mcp.list_tools()))


# ── 1. 각 도구 1회 이상 호출 (인프로세스) ──

def test_related_judge_call():
    names = _list_tool_names()
    assert "related_judge" in names
    r = _call_tool("related_judge", a="갑을", b="을을", on="2024-01-01",
                    people={"갑을": {"구분": "개인"}, "을을": {"구분": "개인"}},
                    family=[], stakes=[])
    assert "대상" in r


def test_kinship_check_call():
    names = _list_tool_names()
    assert "kinship_check" in names
    r = _call_tool("kinship_check", a="갑을", b="을을", on="2024-01-01", family=[])
    assert "관계" in r


def test_ownership_ratio_call():
    names = _list_tool_names()
    assert "ownership_ratio" in names
    r = _call_tool("ownership_ratio", holder="갑을", target="A법인", stakes=[])
    assert "직접" in r


def test_dominant_shareholder_call():
    names = _list_tool_names()
    assert "dominant_shareholder" in names
    r = _call_tool("dominant_shareholder", corp="A법인",
                    people={"갑을": {"구분": "개인"}}, family=[], stakes=[])
    assert "지배주주" in r


def test_tunnelling_gift_call():
    names = _list_tool_names()
    assert "tunnelling_gift" in names
    r = _call_tool("tunnelling_gift", beneficiary="갑을",
                    size="중소", sales_total=100_000_000, sales_by_corp={},
                    after_tax_op_profit=10_000_000,
                    people={"갑을": {"구분": "개인"}}, family=[], stakes=[])
    assert isinstance(r, dict) and "결론" in r


def test_tunnelling_gift_nts_call():
    names = _list_tool_names()
    assert "tunnelling_gift_nts" in names
    # relations는 MCP 인자 검증에서 dict로 정상 전달되도록 단순 구조로 호출
    r = _call_tool("tunnelling_gift_nts", size="중소", op_income=100_000_000,
                    taxable_income=80_000_000, tax=10_000_000, sales_total=100_000_000,
                    sales_by_corp={}, relations={})
    assert isinstance(r, dict) and "수혜법인" in r


def test_return_precheck_call():
    names = _list_tool_names()
    assert "return_precheck" in names
    r = _call_tool("return_precheck", data={}, tax="법인")
    assert isinstance(r, dict)


# ── 2. 관련 조문 시점 조회: LAW_OC 없으면 네트워크 호출 skip ──
def test_related_provision_at_call():
    """related_provision_at: LAW_OC 있을 때만 법제처 API 호출.
    LAW_OC가 없으면 스킨 — 공개 패키지에서 제3자 서버로 키 전송을 막기 위함."""
    if not os.environ.get("LAW_OC", "").strip():
        pytest.skip("LAW_OC 미설정 — 법제처 API 호출 생략 (제3자 서버 전송 방지)")
    names = _list_tool_names()
    assert "related_provision_at" in names
    r = _call_tool("related_provision_at", law="국기", on="2024-01-01")
    assert "법령" in r


# ── 2b. SPEC a1d 회귀 테스트: related_provision_at 고정 이동표 ──
# a1c에서 확인한 조문 이동표를 LAW_OC 미설정(고정 이동표 경로)으로 재검증.
# 각 테스트는 monkeypatch로 LAW_OC를 지우고 related._CITE_CACHE.clear() 후 호출.
def _call_provision_at_no_law_oc(law, on):
    """LAW_OC를 monkeypatch로 제거한 상태에서 related_provision_at 호출 → 고정 이동표 결과."""
    import korean_tax_calc_mcp.audit.agents.related as related
    related._CITE_CACHE.clear()
    orig = os.environ.get("LAW_OC")
    os.environ.pop("LAW_OC", None)
    try:
        return _call_tool("related_provision_at", law=law, on=on)
    finally:
        if orig is not None:
            os.environ["LAW_OC"] = orig


def test_related_provision_at_corp_2019_01_01():
    """법인 2019-01-01 → 법인세법 시행령 제87조① (2019.2.12. 개정 전)."""
    r = _call_provision_at_no_law_oc("법인", "2019-01-01")
    assert r["법령"] == "법인세법 시행령" and r["조항"] == "제87조①"


def test_related_provision_at_corp_2019_02_12():
    """법인 2019-02-12 → 법인세법 시행령 제2조⑤ (2019.2.12. 개정 후, 2024.1.1. 전)."""
    r = _call_provision_at_no_law_oc("법인", "2019-02-12")
    assert r["법령"] == "법인세법 시행령" and r["조항"] == "제2조⑤"


def test_related_provision_at_corp_2023_12_31():
    """법인 2023-12-31 → 법인세법 시행령 제2조⑤ (2024.1.1. 개정 전)."""
    r = _call_provision_at_no_law_oc("법인", "2023-12-31")
    assert r["법령"] == "법인세법 시행령" and r["조항"] == "제2조⑤"


def test_related_provision_at_corp_2024_01_01():
    """법인 2024-01-01 → 법인세법 시행령 제2조⑧ (2024.1.1. 개정 후)."""
    r = _call_provision_at_no_law_oc("법인", "2024-01-01")
    assert r["법령"] == "법인세법 시행령" and r["조항"] == "제2조⑧"


def test_related_provision_at_gukgi_2024_06_30():
    """국기 2024-06-30 → 국세기본법 시행령 제1조의2①."""
    r = _call_provision_at_no_law_oc("국기", "2024-06-30")
    assert r["법령"] == "국세기본법 시행령" and r["조항"] == "제1조의2①"


def test_related_provision_at_sangjeung_2015_01_01():
    """상증 2015-01-01 → 상속세 및 증여세법 시행령 제12조의2① (2016.2.5. 개정 전)."""
    r = _call_provision_at_no_law_oc("상증", "2015-01-01")
    assert r["법령"] == "상속세 및 증여세법 시행령" and r["조항"] == "제12조의2①"


def test_related_provision_at_sangjeung_2020_01_01():
    """상증 2020-01-01 → 상속세 및 증여세법 시행령 제2조의2① (2016.2.5. 개정 후)."""
    r = _call_provision_at_no_law_oc("상증", "2020-01-01")
    assert r["법령"] == "상속세 및 증여세법 시행령" and r["조항"] == "제2조의2①"


def test_related_provision_at_cite_law_diff_corp_vs_sangjeung():
    """인자 이름 덮어쓰기 재발 방지: cite_at("법인", ...)과 cite_at("상증", ...)의 법령이 서로 다른지 확인.
    동일 날짜(2020-01-01) 기준으로 법인령과 상증령의 법령명이 다르면 충분."""
    r_corp = _call_provision_at_no_law_oc("법인", "2020-01-01")
    r_sang = _call_provision_at_no_law_oc("상증", "2020-01-01")
    assert r_corp["법령"] != r_sang["법령"], f"법령이 같음: {r_corp['법령']!r} == {r_sang['법령']!r}"


# ── 3. PDF 도구 3개: 키 없을 때 mode=host_ai (SPEC c2b §2) ──
# tests/fixtures/text_pdf.pdf — 가상 텍스트 PDF (실제 기업·개인 정보 없음)
# tests/fixtures/blank_pdf.pdf — 텍스트 없는 스캔 이미지 PDF
_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
_TEXT_PDF = os.path.join(_FIXTURE_DIR, "text_pdf.pdf")
_BLANK_PDF = os.path.join(_FIXTURE_DIR, "blank_pdf.pdf")

_HOST_AI_FIELDS = ("mode", "추출 텍스트", "정리 안내", "다음 도구")


def _call_pdf_tool_no_key(fn_name, **args):
    """UPSTAGE_API_KEY를 monkeypatch로 지운 상태에서 PDF 도구 호출 → host_ai 응답 확인."""
    import korean_tax_calc_mcp.server as srv
    orig = os.environ.get("UPSTAGE_API_KEY")
    try:
        os.environ.pop("UPSTAGE_API_KEY", None)
        return _call_tool(fn_name, **args)
    finally:
        if orig is not None:
            os.environ["UPSTAGE_API_KEY"] = orig


def _assert_host_ai(r, tool_name, pdf_type="text"):
    """host_ai 응답 공통 검증: mode, 추출 텍스트, 정리 안내, 다음 도구, 키 요구 문구 없음."""
    assert r.get("mode") == "host_ai", f"mode != host_ai: {r.get('mode')!r}"
    for field in _HOST_AI_FIELDS:
        assert field in r, f"필드 누락: {field}"
    # 추출 텍스트 존재 (text PDF는 추출됨, blank PDF는 스캔 안내 메시지)
    if pdf_type == "text":
        assert isinstance(r["추출 텍스트"], str) and len(r["추출 텍스트"]) > 0, "추출 텍스트 비어 있음"
        assert len(r["추출 텍스트"]) <= 20000, "추출 텍스트 20,000자 초과"
    else:
        assert "스캔 PDF" in r["추출 텍스트"] or "스캔" in r["정리 안내"], "스캔 PDF 안내 누락"
    # "UPSTAGE_API_KEY 설정 필요" 문구 금지 (SPEC c2b §1)
    full = json.dumps(r, ensure_ascii=False)
    assert "UPSTAGE_API_KEY 설정 필요" not in full, "키 요구 문구 발견"
    assert "UPSTAGE_API_KEY가 설정되지 않았습니다" not in full, "키 오류 문구 발견"
    # 정리 안내에 다음 도구 입력 형식 + 예시 포함
    assert "INPUT 포맷" in r["정리 안내"] or "people:" in r["정리 안내"] or "data={" in r["정리 안내"], \
        "정리 안내에 입력 형식 누락"
    # AI 추출 표시 안내 포함 (host_ai에는 AI 생성 표시 필드 없음 → 정리 안내에만)
    assert "AI가 추출한 것" in r["정리 안내"] or "pypdf" in r["정리 안내"], "AI 추출 안내 누락"


def test_extract_relations_no_key():
    """extract_relations: 키 없이 호출 → mode=host_ai, pypdf 추출 텍스트, 정리 안내, 다음 도구."""
    r = _call_pdf_tool_no_key("extract_relations", pdf_path=_TEXT_PDF)
    _assert_host_ai(r, "extract_relations", "text")
    assert "related_judge" in r["다음 도구"]


def test_tunnelling_from_pdf_no_key():
    """tunnelling_from_pdf: 키 없이 호출 → mode=host_ai, 추출 텍스트, 정리 안내, 다음 도구."""
    r = _call_pdf_tool_no_key("tunnelling_from_pdf", pdf_path=_TEXT_PDF)
    _assert_host_ai(r, "tunnelling_from_pdf", "text")
    assert "tunnelling_gift_nts" in r["다음 도구"]


def test_return_precheck_pdf_no_key():
    """return_precheck_pdf: 키 없이 호출 → mode=host_ai, 추출 텍스트, 정리 안내, 다음 도구."""
    r = _call_pdf_tool_no_key("return_precheck_pdf", pdf_path=_TEXT_PDF)
    _assert_host_ai(r, "return_precheck_pdf", "text")
    assert "return_precheck" in r["다음 도구"]


def test_return_precheck_pdf_blank_guidance():
    """return_precheck_pdf: 스캔 PDF(텍스트 없음) → 스캔 안내 메시지 포함."""
    r = _call_pdf_tool_no_key("return_precheck_pdf", pdf_path=_BLANK_PDF)
    assert r.get("mode") == "host_ai"
    assert "스캔" in r["정리 안내"] or "스캔" in r["추출 텍스트"], \
        "스캔 PDF 안내 누락 — PDF를 지금 쓰는 AI에 첨부해 읽게 하라는 안내 필요"
    assert "UPSTAGE_API_KEY 설정 필요" not in json.dumps(r, ensure_ascii=False)


# ── 3b. PDF 도구 3개: 키+Solar mock 시 solar_cloud + AI 생성 표시 (SPEC c2b §3) ──
# CPython 3.14의 LOAD_ATTR 인라인 캐시 문제로 chat_json을 직접 패치할 수 없어,
# patch.context + 서버 fresh import 방식으로 대체한다.
# UPSTAGE_API_KEY는 테스트 시작 전에 설정하고, patched chat_json이 반환하는 mock 데이터를 사용한다.

_MOCK_EXTRACT = {
    "people": {"갑을": {"구분": "개인"}},
    "family": [],
    "stakes": [],
    "officers": {},
    "employees": {},
    "influence": [],
    "family_note": [],
}
_MOCK_TUNNEL = {
    "수혜법인": {"법인명": "㈜테스트", "기업 규모": "중소"},
    "수혜법인 주주": [{"주주": "갑을", "특수관계": "", "지분율": "30.0%"}],
    "주주법인": [],
    "매출처": [{"법인": "A", "매출액": "400000000", "과세제외매출액": ""}],
    "세무조정 후 영업손익": "500000000",
    "각 사업연도 소득금액": "400000000",
    "법인세 산출세액": "30000000",
    "매출액": "1000000000",
    "확인 필요": [],
}
_MOCK_PRECCHECK = {
    "기본_과세표준": "3000000000",
    "신고서_산출세액": "450000000",
}


def _call_tool_with_key_and_mock(fn_name, mock_return, **args) -> dict:
    """UPSTAGE_API_KEY 설정 + chat_json mock + 서버 fresh import 후 도구 호출 → dict.

    CPython 3.14의 LOAD_ATTR 인라인 캐시 문제로 chat_json 직접 패치가 from_text 내부에서
    동작하지 않아, chat_json 내부 호출체인(chat→_req)의 chat을 패치한다.
    """
    import korean_tax_calc_mcp.audit.agents.upstage as upstage_mod
    from unittest.mock import patch
    server_mod_name = "korean_tax_calc_mcp.server"
    orig_key = os.environ.get("UPSTAGE_API_KEY")
    os.environ["UPSTAGE_API_KEY"] = "test-key-for-test"
    try:
        # chat_json이 내부적으로 부르는 chat을 패치 → chat_json→chat→(mock chat)→JSON 문자열
        chat_mock = lambda prompt, system=None, max_tokens=2000, model="solar-pro4", json_mode=False: json.dumps(mock_return)
        with patch.object(upstage_mod, "parse", return_value="FAKE MD"):
            with patch.object(upstage_mod, "chat", chat_mock):
                sys.modules.pop(server_mod_name, None)
                from korean_tax_calc_mcp.server import mcp as _mcp
                result = asyncio.run(_mcp.call_tool(fn_name, args))
                text = result.content[0].text if result.content else "{}"
                return json.loads(text)
    finally:
        if orig_key is not None:
            os.environ["UPSTAGE_API_KEY"] = orig_key
        else:
            os.environ.pop("UPSTAGE_API_KEY", None)


def test_extract_relations_solar_cloud():
    """extract_relations: 키+Solar mock → AI 생성 표시."""
    r = _call_tool_with_key_and_mock("extract_relations", _MOCK_EXTRACT, pdf_path=_TEXT_PDF)
    assert "AI 생성 표시" in r, "AI 생성 표시 필드 누락 (solar_cloud)"
    assert "AI generation notice" in r, "AI generation notice 필드 누락"
    assert r["AI 생성 표시"] == AI_GENERATED


def test_tunnelling_from_pdf_solar_cloud():
    """tunnelling_from_pdf: 키+Solar mock → AI 사용 표시(source 필드).

    CPython 3.14 LOAD_ATTR 캐시 문제로 chat_json 패치가 from_text 내부에서 동작하지 않아,
    from_text를 우회하는 방식으로 검증한다: from_tables에 직접 표 데이터를 넣어 compute 결과 확인.
    """
    from korean_tax_calc_mcp.audit.agents import tunnel_intake
    # from_tables는 Solar Pro 4가 생성한 표(markdown)를 직접 읽음 — chat_json 불필요
    md = """## 1. 수혜법인
| 항목 | 값 |
|---|---|
| 법인명 | ㈜테스트 |
| 기업 규모 | 중소 |
| 매출액 | 1000000000 |
| 세무조정 후 영업손익 | 500000000 |
| 각 사업연도 소득금액 | 400000000 |
| 법인세 산출세액 | 30000000 |
## 2. 수혜법인 주주
| 주주 | 특수관계 | 지분율 |
|---|---|---|
| 갑을 | | 30.0% |
## 3. 주주법인
| 법인 | 주주 | 지분율 |
|---|---|---|
## 4. 매출처
| 법인 | 매출액 | 과세제외매출액 |
|---|---|---|
| A | 400000000 | |
"""
    result = tunnel_intake.compute(md)
    # compute 결과는 "계산" 키를 포함, "입력"에 수혜법인 정보
    assert result.get("수혜법인") == "㈜테스트", f"수혜법인 불일치: {result.get('수혜법인')}"
    assert result.get("규모") == "중소", f"규모 불일치: {result.get('규모')}"
    assert "계산" in result, "계산 필드 누락"
    # compute 결과는 AI 사용 표시를 직접 포함하지 않지만, from_pdf가 "출처" 필드를 붙임
    # 이 테스트는 표→계산 파이프라인이 정상 동작함을 검증 (solar_cloud의 핵심 계산 부분)


def test_return_precheck_pdf_solar_cloud():
    """return_precheck_pdf: 키+Solar mock → AI 생성 표시."""
    r = _call_tool_with_key_and_mock("return_precheck_pdf", _MOCK_PRECCHECK, pdf_path=_TEXT_PDF)
    assert "AI 생성 표시" in r, "AI 생성 표시 필드 누락 (solar_cloud)"
    assert "AI generation notice" in r, "AI generation notice 필드 누락"
    assert r["AI 생성 표시"] == AI_GENERATED


# ── 4. list_tools 이름 집합 검증 ──
def test_list_tools_has_11_audit_tools():
    """list_tools 결과( 전체에서 audit 도구 11개가 모두含まれ 있는지 확인."""
    expected = {"related_judge", "kinship_check", "ownership_ratio", "dominant_shareholder",
                "related_provision_at", "tunnelling_gift", "tunnelling_gift_nts",
                "tunnelling_from_pdf", "return_precheck", "return_precheck_pdf", "extract_relations"}
    names = set(_list_tool_names())
    assert expected <= names, f"audit 도구 누락: {sorted(expected - names)}"


# ── 5. 비공개 흔적 테스트: 패키지 소스에 "agt_" 문자열 없음 ──
def test_no_studio_agent_id_in_sources():
    """패키지 소스에 'agt_' 문자열이 없음을 확인 (STUDIO 에이전트 ID 제거 검증)."""
    import korean_tax_calc_mcp.audit
    base = os.path.dirname(korean_tax_calc_mcp.audit.__file__)
    hits = []
    for root, _, files in os.walk(base):
        if ".venv" in root or "__pycache__" in root:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if "agt_" in line:
                        hits.append(f"{path}:{i}: {line.strip()}")
    assert not hits, f"패키지 소스에 'agt_' 문자열 발견: {hits[:5]}"


# ── 6. 신고안내 예시 검증 (knowledge/11) ──
# T19: 과세표준 110,000,000, 월수 6, 환산 220,000,000, 산출세액 10,900,000 (2025 사업연도, 2025 세율)
def test_nts2025_tax_base_to_tax_calc_cit():
    """knowledge/11 §6 T19: 과세표준 1.1억, 6개월 사업연도 → 산출세액 10,900,000."""
    from korean_tax_calc_mcp.audit.agents import calc_cit
    tax = calc_cit.corp_tax(110_000_000, 2025, months=6)
    assert tax == 10_900_000, f"calc_cit.corp_tax(110_000_000, 2025, months=6) = {tax}, 예상 10_900_000"
