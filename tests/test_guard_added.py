"""_guard를 새로 붙인 도구 — 잘못된 입력이 예외가 아니라 {"error": ...} dict로 돌아오는지.
bad_debt_allowance(입력이 모두 스키마 제약)·precheck_schema(Literal만)·related_provision_at(자유 문자열, LAW_OC 없으면 고정표)·
return_precheck(규칙이 잘못된 값을 자료 부족으로 흡수)는 검증 경로가 없어 제외."""
import pytest

CASES = [
    ("underreporting_penalty", {"additional_tax": 1_000_000, "reduction": "수정신고", "due": "bad-date", "amended_on": "2024-01-01"}),
    ("assessment_limitation", {"due_date": "2024-13-45"}),
    ("vat_bad_debt_credit", {"bad_debt_incl_vat": 1_100_000, "reason": "부도", "reason_date": "bad-date"}),
    ("related_judge", {"a": "김갑", "b": "김을", "on": "2024-01-01", "people": {"김갑": {"구분": "개인"}, "김을": {"구분": "개인"}},
                      "family": [], "stakes": [["김갑", "㈜대한", "x"]], "with_citation": False}),
    ("kinship_check", {"a": "김갑", "b": "김을", "on": "2024-01-01", "family": [["김갑"]]}),
    ("ownership_ratio", {"holder": "김갑", "target": "㈜대한", "stakes": [["김갑", "㈜대한", "x"]]}),
    ("dominant_shareholder", {"corp": "㈜대한", "people": {"김갑": {"구분": "개인"}}, "family": [], "stakes": [["김갑", "㈜대한", "x"]]}),
    ("tunnelling_gift", {"beneficiary": "김갑", "size": "중소", "sales_total": 1, "sales_by_corp": {}, "after_tax_op_profit": 1,
                         "people": {"김갑": {"구분": "개인"}}, "family": [], "stakes": [["김갑", "㈜대한", "x"]]}),
    ("tunnelling_gift_nts", {"size": "중소", "op_income": 1, "taxable_income": 1, "tax": 1, "sales_total": 1, "sales_by_corp": {},
                             "relations": {}, "dividends": {"직접": 5}}),
    ("export_workbook", {"title": "t", "calls": "not json"}),
    ("find_tool", {"query": ""}),
]


@pytest.mark.parametrize("tool, args", CASES, ids=[t for t, _ in CASES])
def test_invalid_input_returns_error_dict(call, tool, args):
    r = call(tool, args)
    assert isinstance(r, dict) and "error" in r, r
