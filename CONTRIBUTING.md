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

## Review

Every pull request runs the test workflow and an automated CodeSolar review. Address its comments or reply with the reason you disagree; a maintainer merges after both pass.

## Disclaimer (면책)

These tools are not tax advice. Results are reference material that shows the statutory basis and the calculation; confirm real filings, audits, and appeals with a qualified professional and check the original statute text. See the [README disclaimer](https://github.com/UpstageAI/korean-tax-calc-mcp#면책-및-고지).
