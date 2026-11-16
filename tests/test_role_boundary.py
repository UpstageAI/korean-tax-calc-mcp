"""서버 역할 경계 검사 — 계산 MCP는 계산만 하고, 요건·판단·판례는 조문 MCP(korean-tax-mcp)가 맡는다.

판례·결정례 번호(예: 2024두64901, 조심2023서9158)가 계산 MCP 코드에 새로 늘어나면 실패한다.
판단 근거가 필요하면 조문 MCP의 요건 안내·판례 도구에 넣고, 계산 도구 출력에는 그 도구 이름을 안내한다.
기준선은 이 검사를 만든 시점(0.60.0)의 파일별 개수이며, 줄이는 것은 자유롭고 늘리려면 이유를 적어 기준선을 고친다.
"""
import os
import re

PKG = os.path.join(os.path.dirname(__file__), "..", "korean_tax_calc_mcp")
CASE_NO = re.compile(r"[0-9]{2,4}(?:두|구합|누)[0-9]{2,6}|조심[0-9]{4}[가-힣][0-9]+|국심[0-9]{4}[가-힣][0-9]+")

# 0.60.0 기준선(파일별 판례 번호 개수). 늘리지 말 것 — 판단은 조문 MCP로.
BASELINE = {
    "server.py": 4,                  # 0.60.0 7 → 판단 근거를 조문 MCP로 옮겨 4
    "engine/calc_incentive.py": 4,   # 0.60.0 8 → 위탁제조 결정례를 조문 MCP sme_tax_incentives_guide로 안내해 4
    "engine/calc_vat.py": 9,
    "engine/calc_nominee.py": 2,
    "engine/calc_tax_priority.py": 3,
}   # data/facts_vocab.json·engine/nonresident_issues.py는 0(조문 MCP other_income_guide·royalty_withholding_guide)


def _counts():
    out = {}
    root = os.path.normpath(PKG)
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            try:
                s = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            n = len(CASE_NO.findall(s))
            if n:
                out[os.path.relpath(p, root).replace(os.sep, "/")] = n
    return out


def test_no_new_case_citations_in_calculator():
    over = {k: (v, BASELINE.get(k, 0)) for k, v in _counts().items() if v > BASELINE.get(k, 0)}
    assert not over, (
        "계산 MCP에 판례·결정례 번호가 늘었습니다(파일: (현재, 기준선)) — "
        f"{over}. 요건·판단·판례는 조문 MCP(korean-tax-mcp) 도구에 넣고, "
        "계산 도구 출력에는 그 도구 이름을 안내하세요(CONTRIBUTING.md '서버 역할')."
    )
