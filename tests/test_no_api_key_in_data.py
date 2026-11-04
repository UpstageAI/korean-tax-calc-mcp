"""패키지 데이터·코드에 법제처 OC 같은 키 값이 박혀 있지 않은지 확인."""
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "korean_tax_calc_mcp"


def test_no_oc_value_in_package_files():
    hits = []
    for p in PKG.rglob("*"):
        if p.suffix not in {".json", ".py", ".md", ".txt", ".csv"} or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"[?&]OC=([^&\"'\s{}]+)", text):
            if m.group(1) not in {"<OC>", "...", "test"}:
                hits.append(f"{p.relative_to(PKG)}: OC={m.group(1)[:1]}***")
    assert not hits, hits
