# korean-tax-calc-mcp — Korea Tax Calculator MCP

<!-- mcp-name: io.github.UpstageAI/korean-tax-calc-mcp -->

![Demo: corporate tax and penalty calculation](https://raw.githubusercontent.com/UpstageAI/korean-tax-calc-mcp/main/docs/demo.gif)

[![PyPI](https://img.shields.io/pypi/v/korean-tax-calc-mcp)](https://pypi.org/project/korean-tax-calc-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--calc--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-calc-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) · [한국어](README.md)

**Korean (South Korea) tax calculations for AI agents — code, not guesses.** LLMs often get tax arithmetic wrong. This MCP server computes in code and cites the statute behind every result. It uses year-by-year rate tables (2016–2025); for a year without a verified table it returns an error instead of estimating. 27 tools, no API key, nothing sent outside your machine.

## Try asking

- "Corporate tax on a 500M KRW tax base for fiscal year 2025?"
- "Under-reported 10M KRW of tax, paying on Oct 7 — what are the penalties?"
- "Shareholder loan of 200M on Mar 1, 100M repaid Sep 30 — deemed interest?"
- "SME with 10B KRW revenue spent 50M on entertainment — how much exceeds the limit?"
- "When does the assessment period expire for a corporate tax return due 2018-03-31? What if it was fraudulent?"
- "Retirement income tax on 100M KRW after 15 years of service"

## Install

With [uv](https://docs.astral.sh/uv/) installed, it runs without a separate install step.

```json
{
  "mcpServers": {
    "korean-tax-calc": { "command": "uvx", "args": ["korean-tax-calc-mcp"] }
  }
}
```

Claude Code: `claude mcp add korean-tax-calc -- uvx korean-tax-calc-mcp`

Pair it with [korean-tax-mcp](https://github.com/UpstageAI/korean-tax-mcp) to go from "find the authority" to "compute the number".

## Tools

| Tool | Calculation | Statute |
|---|---|---|
| `corporate_tax` | Corporate income tax (incl. short fiscal years) | CITA Art. 55 |
| `entertainment_limit` | Business entertainment expense limit and excess | CITA Art. 25 |
| `deemed_interest` | Deemed interest on shareholder loans (daily balances, 300M/5% test) | CITA Art. 52; Decree Art. 89 |
| `unfair_transaction` | Unfair related-party transaction threshold (300M/5% gap from market price) | CITA Decree Art. 88(3) |
| `loss_carryforward_limit` | Loss carryforward deduction limit rate | CITA Art. 13 |
| `minimum_tax` | Minimum tax | Restriction of Special Taxation Act Art. 132 |
| `underreporting_penalty` | Under-reporting penalty (10% / 40%) | Framework Act on National Taxes Art. 47-3 |
| `late_payment_penalty` | Late payment penalty (prorated across rate changes) | Framework Act on National Taxes Art. 47-4 |
| `invoice_penalty` | Tax invoice penalties (fictitious, unissued, late, etc.) | VAT Act Art. 60 |
| `assessment_limitation` | Assessment limitation period and expiry date (incl. offshore, inheritance/gift) | Framework Act on National Taxes Art. 26-2 |
| `income_tax` | Global income tax | Income Tax Act Art. 55 |
| `withholding_tax` | Withholding tax by income type and payment year | Income Tax Act Art. 129 |
| `retirement_income_tax` | Retirement income tax | Income Tax Act Art. 48 |
| `vat_deemed_rent` | Deemed rent on lease deposits | VAT Decree Art. 65 |
| `nonbusiness_interest_disallowance` | Interest disallowance for non-business assets | CITA Art. 28 |
| `business_car_expense` | Business passenger car expenses (business-use ratio, depreciation cap) | CITA Art. 27-2 |
| `donation_limit` | Donation limit, excess and carryforward | CITA Art. 24 |
| `bad_debt_allowance` | Bad debt allowance limit | CITA Art. 34 |
| `missing_receipt_disallowance` | Entertainment expenses without qualified receipts | CITA Art. 25(2) |
| `vat_deemed_input_credit` | Deemed input tax credit | VAT Act Art. 42 |
| `vat_common_input_allocation` | Allocation of common input tax | VAT Decree Art. 81 |
| `vat_simplified_taxpayer` | VAT payable by simplified taxpayers | VAT Act Art. 63 |
| `vat_card_sales_credit` | Credit for credit-card sales slips | VAT Act Art. 46 |
| `vat_bad_debt_credit` | Bad debt VAT credit | VAT Act Art. 45 |
| `wage_income_tax` | Earned income deduction, tax and earned income tax credit | Income Tax Act Arts. 47, 55, 59 |
| `daily_worker_withholding` | Withholding for daily workers | Income Tax Act Art. 134 |
| `deemed_bonus_resettlement` | Year-end resettlement of deemed bonus | Income Tax Decree Art. 192 |

CITA = Corporate Income Tax Act.

## Notes

- Results are a review aid, not tax advice. Check the statute text before filing.
- Local income tax is not included.
- Years without a verified rate table return an error rather than an estimate.
- **Data transmission** — All calculations run locally in code; nothing is sent to any external API.

## License

MIT © 2026 Upstage

Created by Mia (Seungmi Yoon)
