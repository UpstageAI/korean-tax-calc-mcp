"""입력 단일화(원장형만)·같은 입력 재호출 안내 정답 테스트 (Claude 작성 2026-10-14) — 수정 금지.
0.9.0: entertainment_adjustment·simplified_vat_return·common_input_tax 는 ledger만 받고, _guard 가 같은 입력 재호출을 알린다.
실행: .venv/bin/python -m pytest tests/test_e2e7_golden.py -q
"""
import asyncio, json
from korean_tax_calc_mcp import server
from korean_tax_calc_mcp.server import mcp


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def schema(name):
    t = next(x for x in asyncio.run(mcp.list_tools()) if x.name == name)
    return t.input_schema


# ── A. 스키마에서 옛 입력이 사라졌는지 ───────────────────────────────────────
def test_schema_ledger_only():
    s = schema("entertainment_adjustment")
    assert "ledger" in s["properties"] and "ledger" in s.get("required", [])
    assert not ({"expenses", "revenue_general", "revenue_related"} & set(s["properties"]))
    s = schema("simplified_vat_return")
    assert "ledger" in s["properties"] and "ledger" in s.get("required", [])
    assert not ({"supplies", "purchases"} & set(s["properties"]))
    s = schema("common_input_tax")
    assert "ledger" in s["properties"] and "ledger" in s.get("required", [])
    assert "input_tax" not in s["properties"]


def test_descriptions_do_not_mention_legacy_fields():   # 모델이 보는 설명에 옛 필드명이 남아 있으면 그걸 쓴다
    legacy_by_tool = {"entertainment_adjustment": ("expenses", "revenue_general", "revenue_related"),
                      "simplified_vat_return": ("supplies", "purchases", "card_receipt_issued", "tax_invoice_received"),
                      "common_input_tax": ("input_tax\"", "taxable_only", "exempt_only", "attributed")}
    for name, legacy_fields in legacy_by_tool.items():
        t = next(x for x in asyncio.run(mcp.list_tools()) if x.name == name)
        text = (t.description or "") + json.dumps(t.input_schema, ensure_ascii=False)
        for legacy in legacy_fields:
            assert legacy not in text, (name, legacy)


def test_empty_ledger_refused():
    assert "error" in c("entertainment_adjustment", {"year": 2026, "sme": False, "ledger": []})
    assert "error" in c("simplified_vat_return", {"year": 2025, "business_type": "음식점업", "prior_year_supplies": 1, "ledger": {"공급": [], "매입": []}})
    assert "error" in c("common_input_tax", {"year": 2024, "period": "1기", "filing": "예정",
                                             "supplies": {"예정": {"taxable": 1, "exempt": 1}, "확정": None}, "ledger": []})


def test_ledger_evidence_enum_enforced():
    r = c("entertainment_adjustment", {"year": 2025, "sme": False, "ledger": [{"항목": "x", "금액": 1_000, "증빙": "카드"}]})
    assert "error" in r and "적격" in json.dumps(r, ensure_ascii=False)


def test_ledger_calculates_same_as_before():   # 공개 사례 2024-65를 원장형으로: 결과 불변
    r = c("entertainment_adjustment", {
        "year": 2024, "sme": False, "months": 12, "revenue": {"매출액": 12_000_000_000, "특수관계매출": 4_500_000_000},
        "ledger": [{"항목": "증빙 없는 지출", "금액": 8_000_000, "증빙": "없음"},
                   {"항목": "영수증 수취 지출(건당 3만원 초과)", "금액": 6_000_000, "증빙": "영수증 등"},
                   {"항목": "적격증빙 지출", "금액": 42_000_000, "증빙": "적격"}]})
    assert r["결과"]["소득처분별_합계"] == {"대표자상여": 8_000_000, "기타사외유출": 12_350_000}


# ── B. 같은 입력 재호출 안내 ─────────────────────────────────────────────────
ARGS = {"year": 2024, "period": "1기", "filing": "예정",
        "supplies": {"예정": {"taxable": 400_000_000, "exempt": 600_000_000}, "확정": None},
        "ledger": [{"항목": "임차료", "매입세액": 1_000_000, "사용처": "공통"}]}


def test_repeat_call_notice():
    server._reset_call_memo()
    r1 = c("common_input_tax", ARGS)
    assert "안내" not in r1 and r1["결과"]["공제매입세액"] == 400_000
    r2 = c("common_input_tax", ARGS)
    assert list(r2)[0] == "안내" and "2번째" in r2["안내"] and r2["결과"] == r1["결과"]
    r3 = c("common_input_tax", ARGS)
    assert "3번째" in r3["안내"]
    other = c("common_input_tax", {**ARGS, "ledger": [{"항목": "임차료", "매입세액": 2_000_000, "사용처": "공통"}]})
    assert "안내" not in other                                                           # 인자가 다르면 새 계산


def test_repeat_notice_on_errors_and_other_tools():
    server._reset_call_memo()
    bad = {"year": 2026, "sme": False, "ledger": []}
    assert "안내" not in c("entertainment_adjustment", bad)
    r = c("entertainment_adjustment", bad)
    assert "error" in r and list(r)[0] == "안내" and "2번째" in r["안내"]
    ok = {"year": 2024, "base": 100_000_000}
    c("corporate_tax", ok)
    assert "2번째" in c("corporate_tax", ok)["안내"]


def test_reset_clears_memo():
    server._reset_call_memo()
    c("corporate_tax", {"year": 2024, "base": 1_000})
    server._reset_call_memo()
    assert "안내" not in c("corporate_tax", {"year": 2024, "base": 1_000})
