"""입력 의미 검증 정답 테스트 — persons.relation 허용값·income_ok 설명, 의제매입 purchase 설명. 작성 Claude 2026-10-21.
계산 로직은 바꾸지 않는다. 모르는 relation을 조용히 0 처리하던 것을 '문제'로 알리거나 동의어로 받아들인다."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp

TOOL = "special_tax_credit"


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def _schema(tool):
    tools = asyncio.run(mcp.list_tools())
    t = next(x for x in tools if x.name == tool)
    return t.inputSchema["properties"]


def _args(rel):
    return {"year": 2021, "earner_type": "근로", "total_salary": 60000000,
            "persons": [{"name": "본인", "relation": "본인", "age": 50, "income_ok": True},
                        {"name": "아들", "relation": rel, "age": 22, "income_ok": True},
                        {"name": "딸", "relation": rel, "age": 16, "income_ok": True},
                        {"name": "모친", "relation": "직계존속", "age": 75, "income_ok": True}],
            "expenses": [{"kind": "교육비_대학원", "amount": 4000000, "person": "본인"},
                         {"kind": "교육비_대학", "amount": 10000000, "person": "아들"},
                         {"kind": "교육비_초중고", "amount": 100000, "person": "딸"},
                         {"kind": "교복", "amount": 300000, "person": "딸"},
                         {"kind": "교육비_대학", "amount": 500000, "person": "모친"}]}


def test_known_relation_result_unchanged():
    r = c(TOOL, _args("직계비속"))
    assert r["결과"]["교육비_세액공제"] == 2010000            # 본인 4M + 아들 9M(한도) + 딸 0.4M, 모친 제외 → ×15%


def test_child_relation_is_not_silently_zero():
    r = c(TOOL, _args("자녀"))
    if "error" in r:                                           # 거부하는 경우: 허용값을 알려줘야 함
        txt = json.dumps(r, ensure_ascii=False)
        assert "relation" in txt and "직계비속" in txt
    else:                                                      # 동의어로 받는 경우: 직계비속과 같은 결과
        assert r["결과"]["교육비_세액공제"] == 2010000


def test_unknown_relation_rejected_with_allowed_list():
    r = c(TOOL, _args("친구"))
    assert "error" in r
    txt = json.dumps(r, ensure_ascii=False)
    assert "친구" in txt and "직계비속" in txt and "직계존속" in txt     # 허용 목록이 메시지에 있음


def test_persons_description_explains_relation_and_income_ok():
    d = _schema(TOOL)["persons"]["description"]
    assert "직계비속" in d and "직계존속" in d and "income_ok" in d
    assert "소득" in d                                         # income_ok 뜻(소득 요건 충족) 설명


def test_deemed_input_purchase_description_has_rules():
    d = _schema("vat_deemed_input_credit")["purchase"]["description"]
    assert "판매" in d and "재고" in d                          # 그대로 판매분 제외·재고분 포함
    assert "합산" in d or "1회" in d                            # 품목별 분리 호출 금지 안내
