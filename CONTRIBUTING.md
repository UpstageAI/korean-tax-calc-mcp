# Contributing to korean-tax-calc-mcp

Thank you for helping improve these tax calculation tools. 기여해 주셔서 감사합니다. 이슈와 PR은 한국어·영어 모두 환영합니다.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report security problems privately as described in [SECURITY.md](SECURITY.md).

## Reporting a wrong number or statute (계산·조문 오류 제보)

Open an issue with the "Wrong result or statute" form and include:

- **Tool name** (e.g. the MCP tool you called)
- **Inputs** you passed (remove any personal or company data)
- **Actual result** and **expected value**, with the basis: law name, article, and the effective date you applied (시행일, and the 부칙 application rule if the amendment matters)
- **Version** (`pip show korean-tax-calc-mcp`) and the client you used

A report with the statute and the effective date can usually be fixed and covered by a test right away.

## 서버 역할 (Server roles)

이 서버(계산 MCP)는 **계산만** 합니다. 요건 해당 여부, 연도별 적용 판단, 판례·결정례·해석, 소득 구분 같은 **판단은 짝 서버 [korean-tax-mcp](https://github.com/UpstageAI/korean-tax-mcp)(조문 MCP)** 가 맡습니다.

- 새 도구나 기능을 더하기 전에 "이 판단은 어느 서버 몫인가"를 먼저 정합니다. 판단이면 조문 MCP에 요건 안내·판례 도구를 만들고, 계산 도구 출력 첫 줄에서 그 도구 이름을 안내합니다.
- 계산 도구의 쟁점 설명은 "무엇이 숫자를 바꾸는지" 한 줄씩만 둡니다. 판례 번호와 판단 경로를 이 서버에 새로 넣지 않습니다(`tests/test_role_boundary.py`가 판례 번호가 늘면 실패시킵니다).
- 같은 판단을 두 서버에 중복해 두지 않습니다.

This server only computes. Requirement checks, year-by-year applicability, rulings and case law live in the companion server korean-tax-mcp; calculator outputs point to the matching tool there.

## Running tests (테스트 실행)

The same commands CI runs (`.github/workflows/test.yml`, Python 3.10–3.12):

```bash
python -m pip install --upgrade pip
python -m pip install -e . pytest
python -m pip install ruff && ruff check . --select E9,F821
python -m pytest -q tests
```

Run the full suite locally before opening a pull request.

## Pull request rules

- **Cite the statute for every rule and number.** Give the law name, article, 공포번호 and 시행일, checked against the statute text. Do not rely on summaries or memory.
- **Apply the amendment's effective-date rule (부칙).** Rates and limits are split by year or effective date according to the 부칙 적용례; do not replace an old value wholesale.
- **Answer tests are hand-computed from the statute**, not copied from the tool's output, and include boundary cases (thresholds, bracket edges, the day before/after an effective date).
- **New or renamed tools must update the README tool tables and tool counts** (`README.md`, `README-EN.md`, and other files that list tools such as `llms.txt`) so the consistency tests pass in CI.
- **Tool descriptions start with an English line**, followed by Korean detail.
- **No secrets.** Never commit API keys (`LAW_OC` or `UPSTAGE_API_KEY`), tokens, or personal data, including in tests and fixtures.
- Docs-only changes do not need a version bump; maintainers handle releases and `CHANGELOG.md`.
- **Releases go through GitHub Actions only.** Maintainers publish with `gh workflow run publish-pypi.yml` (PyPI Trusted Publishing, no API token); the MCP Registry workflow runs after it. Do not upload from a local machine with an API token.

## Keeping the law.go.kr key out of the repo (법제처 OC 키 유출 방지)

The 법제처 Open API puts the key in the request URL (`…?OC=<key>&…`) and echoes that URL back inside response links, so a saved response or a copied source link carries the key with it. Four guards:

- **Masked on receipt.** `korean_tax_calc_mcp.audit.agents.law._get` (the only code here that calls law.go.kr) returns responses with every `OC=<value>` replaced by `OC=***`; the key exists only in the outgoing request URL.
- **Repository scan.** `tests/test_oc_key_guard.py` runs `scripts/check_no_oc_key.sh --all` over every tracked file in CI. Placeholders such as `OC=***`, `OC={oc}`, `OC=test`, `YOUR_KEY` pass.
- **Pre-commit hook.** Install once per clone (covers every worktree): `bash scripts/check_no_oc_key.sh --install`. A commit whose staged files contain a key-shaped value is refused; the hook prints file and line only, never the value.
- **Saving raw responses (원자료 저장).** Pass anything fetched from law.go.kr through the masking helper before it touches disk: `curl -s "$URL" | python scripts/redact_oc.py > raw/law_xxx.json`, or in Python `from korean_tax_calc_mcp.audit.agents.law import scrub_oc` and `json.dump(scrub_oc(data), f)`. Already-saved files: `python scripts/redact_oc.py raw/*.json`. Do not `echo` a URL that contains the key and do not run such commands under `set -x`; keep the URL in a variable.

If a key was pushed, masking the file is not enough (it stays in history): reissue the key at open.law.go.kr.

## Review

Every pull request runs the test workflow and an automated CodeSolar review. Address its comments or reply with the reason you disagree; a maintainer merges after both pass.

## Disclaimer (면책)

These tools are not tax advice. Results are reference material that shows the statutory basis and the calculation; confirm real filings, audits, and appeals with a qualified professional and check the original statute text. See the [README disclaimer](https://github.com/UpstageAI/korean-tax-calc-mcp#면책-및-고지).
