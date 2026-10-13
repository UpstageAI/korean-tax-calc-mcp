"""어휘 연결 정답 테스트 (Claude 작성 2026-10-13) — 수정 금지.
계산기가 facts_vocab.json의 허용값·기간별 기준·별칭을 직접 읽는지 확인. 기대값은 해당 시점 시행본을 law_article로 조회해 확인한 것.
"""
import asyncio, json, inspect
from korean_tax_calc_mcp.server import mcp
from korean_tax_calc_mcp import vocab


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


# ── vocab 모듈 ────────────────────────────────────────────────────────────────
def test_rule_by_period():
    assert vocab.rule("기업업무추진비_적격증빙미수취", 2020)["기준"]["일반"] == 10_000      # 영 제41조① 2009~2020: 1만 원
    assert vocab.rule("기업업무추진비_적격증빙미수취", 2021)["기준"]["일반"] == 30_000      # 2021.1.1. 이후 지출분 3만 원
    assert vocab.rule("기업업무추진비_적격수취", 2019)["기본한도"]["중소"] == 24_000_000   # 법 제25조① 2019 시행본
    assert vocab.rule("기업업무추진비_적격수취", 2020)["기본한도"]["중소"] == 36_000_000
    assert vocab.rule("상장법인현금배당", 2023)["Gross-up가산율"] == 0.11                  # 법 제17조③ 100분의 11
    assert vocab.rule("상장법인현금배당", 2024)["Gross-up가산율"] == 0.10                  # 2024.1.1. 100분의 10


def test_alias_resolution():
    assert vocab.resolve("접대비_적격수취", tool_name="entertainment_adjustment")["이름"] == "기업업무추진비_적격수취"
    assert vocab.resolve("기업업무추진비_적격수취")["이름"] == "기업업무추진비_적격수취"
    assert "접대비" in json.dumps(vocab.resolve("기업업무추진비_적격수취"), ensure_ascii=False)


def test_items_for_tool_fields():
    kinds = {it["이름"] for it in vocab.items_for("financial_income_aggregate", "kind")}
    assert {"예금이자", "소비대차전환이자", "투자신탁환매이익", "의제배당_잉여금자본전입", "인정배당"} <= kinds
    kinds = {it["이름"] for it in vocab.items_for("bad_debt_adjustment", "kind")}
    assert {"소멸시효완성", "화해·확정판결", "부도6개월", "회수불능"} <= kinds


# ── 계산기가 어휘를 쓰는지 (코드 상수가 아니라) ────────────────────────────────
def test_entertainment_threshold_follows_year():
    base = {"sme": False, "months": 12, "revenue_general": 0, "revenue_related": 0,
            "expenses": [{"amount": 20_000, "evidence": "영수증 등", "over_30k": True}]}
    r20 = c("entertainment_adjustment", {"year": 2020, **base})
    r21 = c("entertainment_adjustment", {"year": 2021, **base})
    # 2020: 기준 1만 원 → 2만 원 영수증은 적격증빙 미수취 → 기타사외유출 / 2021: 기준 3만 원 → 시부인 대상
    assert sum(a["금액"] for a in r20["세무조정"] if a["구분"] == "적격증빙 미수취") == 20_000
    assert sum(a["금액"] for a in r21["세무조정"] if a["구분"] == "적격증빙 미수취") == 0
    assert r21["결과"]["시부인_대상"] == 20_000


def test_entertainment_base_limit_follows_year():
    base = {"sme": True, "months": 12, "revenue_general": 0, "revenue_related": 0, "expenses": [{"amount": 1_000, "evidence": "적격"}]}
    assert c("entertainment_adjustment", {"year": 2019, **base})["결과"]["한도"] == 24_000_000
    assert c("entertainment_adjustment", {"year": 2020, **base})["결과"]["한도"] == 36_000_000


def test_grossup_rate_follows_year():
    items = [{"kind": "예금이자", "amount": 10_000_000}, {"kind": "상장법인현금배당", "amount": 15_000_000}]
    assert c("financial_income_aggregate", {"year": 2023, "items": items})["결과"]["합산액"] == 25_550_000   # 5,000,000 × 11%
    assert c("financial_income_aggregate", {"year": 2024, "items": items})["결과"]["합산액"] == 25_500_000   # 5,000,000 × 10%


def test_validation_lists_come_from_vocab():
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "없는종류", "amount": 1}]})
    assert "error" in r
    names = set(r["허용값"].keys())
    assert names == {it["이름"] for it in vocab.items_for("financial_income_aggregate", "kind")}
    assert all(r["허용값"][n].get("설명") for n in names)   # 설명(뜻)이 어휘에서 왔는지


def test_no_hardcoded_constants_in_server():
    import korean_tax_calc_mcp.server as S
    src = inspect.getsource(S.entertainment_adjustment) + inspect.getsource(S.financial_income_aggregate)
    for lit in ("30_000", "200_000", "36_000_000", "12_000_000", "0.11", "0.10"):
        assert lit not in src, f"코드 상수 {lit}가 남아 있음 — 어휘에서 읽어야 함"


def test_tool_description_lists_vocab():
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    d = tools["financial_income_aggregate"].description
    assert "소비대차전환이자" in d and "투자신탁환매이익" in d and len(d) <= 1500
    assert "접대비" in tools["entertainment_adjustment"].description
