"""서버 역할 경계(관행 기준값) — 계산 MCP에 관행·우리 규칙 기준값 상수를 두지 않는다(0.61.0~). Claude 작성(2026-11-17).

비교대상 선정·프로필 비교의 기준값(독립성 %, 비율 배수, 손실 연도 수 등)은 조문 MCP(korean-tax-mcp) transfer_pricing_guide가 주고,
계산 MCP는 rules·screens 입력으로만 받는다. 이 검사는 선정 관련 모듈에 숫자 값을 가진 dict 상수가 다시 생기면 실패한다.
법정 기준(시행령 제2조② 50%)과 데이터 검산 허용 오차만 예외. tests/test_role_boundary.py(판례 번호 검사)와 같은 원칙.
"""
import ast
import os

PKG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "korean_tax_calc_mcp"))
FILES = ["engine/calc_tp_screen.py"] + [os.path.join("engine/kr_comparables", f) for f in os.listdir(os.path.join(PKG, "engine", "kr_comparables")) if f.endswith(".py")]
# 숫자 값을 허용하는 키 — 법정 기준과 검산 허용 오차(선정 기준 아님)
ALLOWED = {"independence_legal_pct", "control_dependence", "op_tolerance"}
RULE_DICT_NAMES = ("DEFAULT", "PRACTICE", "RULE", "SCREEN", "THRESH", "CRITERIA")


def _num(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)


def _violations():
    out = []
    for rel in FILES:
        tree = ast.parse(open(os.path.join(PKG, rel), encoding="utf-8").read())
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any(any(w in n.upper() for w in RULE_DICT_NAMES) for n in names):
                continue
            for k, v in zip(node.value.keys, node.value.values):
                key = k.value if isinstance(k, ast.Constant) else None
                if key in ALLOWED:
                    continue
                if _num(v) or (isinstance(v, ast.List) and v.elts):          # 숫자 또는 값 목록(예: 탈락 등급) — 설명용 튜플(구분, 근거)은 허용
                    out.append(f"{rel}:{node.lineno} {names[0]}[{key!r}]")
    return out


def test_no_practice_threshold_constants():
    bad = _violations()
    assert not bad, ("계산 MCP에 관행·우리 규칙 기준값 상수가 생겼습니다 — " + ", ".join(bad) +
                     ". 기준값은 rules·screens 입력으로 받고(값·출처는 조문 MCP transfer_pricing_guide), 입력이 없으면 법정 기준만 적용하세요.")


def test_check_catches_a_planted_constant(tmp_path, monkeypatch):
    p = tmp_path / "x.py"
    p.write_text('DEFAULT_RULES = {"mix_max_diff": 0.2, "independence_legal_pct": 50}\n', encoding="utf-8")
    monkeypatch.setattr(__import__(__name__), "PKG", str(tmp_path))
    monkeypatch.setattr(__import__(__name__), "FILES", ["x.py"])
    assert _violations() == ["x.py:1 DEFAULT_RULES['mix_max_diff']"]
