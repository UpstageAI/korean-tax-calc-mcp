"""인적공제 입력 오류 문장 정답 테스트. 작성 Claude 2026-10-24 (docs/SPEC_gold_gaps3b.md)."""
import pathlib
from tests._helpers import call as c


def test_missing_birth_year_is_clear_error():
    r = c("personal_deduction", {"year": 2025, "taxpayer": {"birth_year": 1985}, "persons": [{"relation": "직계비속", "age": 10}]})
    assert r.get("error", "").startswith("입력 확인 필요") and any("birth_year" in p and "persons[0]" in p for p in r["문제"])


def test_no_typo_in_server():
    src = (pathlib.Path(__file__).resolve().parents[1] / "korean_tax_calc_mcp").rglob("*.py")
    assert not any("계산하기 않음" in p.read_text(encoding="utf-8") for p in src)
