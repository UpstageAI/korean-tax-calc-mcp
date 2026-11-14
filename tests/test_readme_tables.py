"""README·README-EN 도구 표가 등록 도구와 맞는지 — 묶음 제목 숫자 = 행 수, 행 합 = 등록 도구 수, 빠진 도구·없는 도구 0."""
import asyncio
import pathlib
import re

import pytest

from korean_tax_calc_mcp import server as S

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAMES = {t.name for t in asyncio.run(S.mcp.list_tools())}
GROUP = re.compile(r"<summary><b>([^<]*?)</b> \((\d+)\)</summary>(.*?)</details>", re.S)
ROW = re.compile(r"^\| `([a-z_0-9]+)` \|", re.M)


@pytest.mark.parametrize("fname", ["README.md", "README-EN.md"])
def test_readme_tool_groups_match_registered_tools(fname):
    txt = (ROOT / fname).read_text(encoding="utf-8")
    rows = []
    for m in GROUP.finditer(txt):
        got = ROW.findall(m.group(3))
        assert int(m.group(2)) == len(got), (m.group(1), m.group(2), len(got))
        rows += got
    assert len(rows) == len(set(rows)), "같은 도구가 두 묶음에"
    assert set(rows) == NAMES, (NAMES - set(rows), set(rows) - NAMES)


@pytest.mark.parametrize("fname", ["README.md", "README-EN.md"])
def test_readme_details_render(fname):
    txt = (ROOT / fname).read_text(encoding="utf-8")
    assert txt.count("<details>") == txt.count("</details>")
    # 표·mermaid가 렌더링되려면 </summary> 다음 줄이 비어 있어야 함
    assert not re.search(r"</summary>\n(?!\n)", txt)


def test_pyproject_description_has_no_stale_count():
    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    desc = re.search(r'^description = "(.*)"$', txt, re.M).group(1)
    for n in re.findall(r"(\d+) tools", desc):
        assert int(n) == len(NAMES)
