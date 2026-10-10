# korean-tax-calc-mcp — Korea Tax Calculator MCP

<!-- mcp-name: io.github.UpstageAI/korean-tax-calc-mcp -->

![Demo: corporate tax and penalty calculation](https://raw.githubusercontent.com/UpstageAI/korean-tax-calc-mcp/main/docs/demo.gif)

[![PyPI](https://img.shields.io/pypi/v/korean-tax-calc-mcp)](https://pypi.org/project/korean-tax-calc-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--calc--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-calc-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Built with Upstage Solar Pro 4](https://img.shields.io/badge/Built%20with-Upstage%20Solar%20Pro%204-7A3FF2)](https://www.upstage.ai/) · [한국어](README.md)

> **Developed with Upstage Solar Pro 4 since 0.3.0** (0.2.1 and earlier predate it). 2026 corporate tax rates, non-resident withholding (`nonresident_withholding`) and thin capitalization (`thin_capitalization`) were written by Solar Pro 4 (Solar Code CLI), reviewed on each PR by CodeSolar (Solar Pro 4-based code review) and cross-checked with tests by Claude. **0.4.0: merged 11 tax audit judgment tools. 0.5.1: added precheck_schema (input schema for tax return precheck), expanded simplified-taxpayer and deemed-input-tax scenarios, refreshed descriptions — now 41 tools.**

**Korean (South Korea) tax calculations for AI agents — code, not guesses.** LLMs often get tax arithmetic wrong. This MCP server computes in code and cites the statute behind every result. It uses year-by-year rate tables (2016–2026); for a year without a verified table it returns an error instead of estimating. 41 tools (29 computation + 12 tax audit judgment). Nothing sent outside your machine for the 29 computation tools.

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
| `vat_deemed_input_credit` | Deemed input tax credit (freight exclusion, common inventory allocation) | VAT Act Art. 42; Decree Art. 81, 84 |
| `vat_common_input_allocation` | Allocation of common input tax | VAT Decree Art. 81 |
| `vat_simplified_taxpayer` | Full VAT calculation for simplified taxpayers (tax base, input credit, card credit, penalty, exemption) | VAT Act Art. 46, 63, 68-2, 69 |
| `vat_card_sales_credit` | Credit for credit-card sales slips | VAT Act Art. 46 |
| `vat_bad_debt_credit` | Bad debt VAT credit | VAT Act Art. 45 |
| `wage_income_tax` | Earned income deduction, tax and earned income tax credit | Income Tax Act Arts. 47, 55, 59 |
| `daily_worker_withholding` | Withholding for daily workers | Income Tax Act Art. 134 |
| `deemed_bonus_resettlement` | Year-end resettlement of deemed bonus | Income Tax Decree Art. 192 |

### Tax audit judgment (11 tools)

| Tool | Judgment/calculation | Authority |
|---|---|---|
| `related_judge` | Whether two parties are related under the Framework Act, CIT, or Inheritance/Gift Tax Act; which subparagraph — 기준일 (YYYY-MM-DD) required | Framework Act Decree Art. 1-2; CIT Decree Art. 2; Inheritance/Gift Tax Decree Art. 2-2 |
| `kinship_check` | Kinship between two individuals (degree, spouse) and whether within the scope at the 기준일 | Framework Act Decree Art. 1-2(1); Inheritance/Gift Tax Decree Art. 2-2(1)1 |
| `ownership_ratio` | Direct + indirect ownership ratio (holder → corporation), path-by-path product, circular shares reflected | Inheritance/Gift Tax Decree Art. 34-3(2) |
| `dominant_shareholder` | Dominant shareholder of the beneficiary corporation (highest direct holder among largest shareholders; if corporation, highest direct+indirect individual) | Inheritance/Gift Tax Decree Art. 34-3(1) |
| `tunnelling_gift` | Deemed gift profit from tunnelling (Inheritance/Gift Tax Act Art. 45-3) — ⑩ excluded sales input, ⑭·⑮ not reflected | Inheritance/Gift Tax Act Art. 45-3; Decree Art. 34-3 |
| `tunnelling_gift_nts` | Deemed gift profit — NTS 2026 filing guide formula (⑫·⑭1·3·⑮ dividend deduction) | Inheritance/Gift Tax Act Art. 45-3; Decree Art. 34-3; NTS 2026 guide |
| `related_provision_at` | Where the related-party scope provision was located on the 기준일 (law=국기|법인|상증) — LAW_OC:법제처 API, else fixed table | Framework Act / CIT / Inheritance-Gift Tax Decree |
| `extract_relations` | Extract relation table (people/family/stakes/officers) from shareholder register·family·officer PDF. Works without UPSTAGE_API_KEY using pypdf local text extraction + 정리 안내 (default). With key: Document Parse + Solar Pro 4 for more precise table extraction | — |
| `tunnelling_from_pdf` | Tunnelling review PDF → table extraction → dominant shareholder·ownership·gift calculation. Works without UPSTAGE_API_KEY using pypdf local extraction + 정리 안내 (default). With key: Document Parse + Solar Pro 4 for more precise table extraction | Inheritance/Gift Tax Act Art. 45-3 |
| `return_precheck` | Pre-review of tax return (error suspicion list): data={input key: value}, tax=법인|부가|소득 — uses audit/agents/precheck rule engine | Per-rule authority (see each rule's 근거) |
| `return_precheck_pdf` | Corporate tax return PDF (Forms 1·3·50) → table extraction → pre-review. Works without UPSTAGE_API_KEY using pypdf local extraction + 정리 안내 (default). With key: Document Parse + Solar Pro 4 for more precise table extraction | Cross-form reconciliation·tax chain recalculation |
| `precheck_schema` | Returns the input schema for tax return precheck: when tax=corp|vat|income is specified, provides the meaning, unit, and required/optional status of each input key for that tax type. Call before return_precheck or PDF tools | Required/optional classification based on each rule's needs |

CITA = Corporate Income Tax Act.

## Issue flags

`nonresident_withholding` and `thin_capitalization` may return an **쟁점 (issues)** list alongside the computed tax. Each entry records a point that can be disputed in practice — e.g. whether software remuneration is royalty or business income, whether a treaty rate applies only after substance-over-form review — and lists **materials to verify** and **reference authorities** (statute articles, ruling numbers, case citations). The tool never concludes ("this is business income"); the `판단` field of every issue is fixed to "세무사 확인 필요" (tax accountant review required). Issue data is read from `korean_tax_calc_mcp/data/issues.json`, not hardcoded.

## Disclaimers and notices

- **Disclaimer:** Results are a review aid, not tax advice. Verify statutes and rulings with a tax accountant, CPA or attorney before filing, during a tax audit, or in appeals. Check the statute text and case law in the original source.
- **AI use notice:** The 29 computation/judgment tools run in code and do not use generative AI. The 3 PDF review tools (`extract_relations`, `tunnelling_from_pdf`, `return_precheck_pdf`) use generative AI (Upstage Solar Pro 4) when UPSTAGE_API_KEY is set, and mark that fact in their results. Without a key, they use pypdf for local text extraction (host_ai mode) and provide 정리 안내 (cleanup guidance) so the next tool input can be prepared manually.
- **Data transmission:** Document content is sent to the Upstage API (api.upstage.ai) only when UPSTAGE_API_KEY is set and the PDF tools are used. Without a key (pypdf local extraction), no data is transmitted externally. Do not submit documents containing personal or sensitive information when using the API-based flow.

## Notes

- Results are a review aid, not tax advice. Check the statute text before filing.
- Local income tax is not included.
- Years without a verified rate table return an error rather than an estimate.
- **Data transmission** — The 29 computation/judgment tools run locally in code; nothing is sent to any external API. Only the 3 PDF tools transmit document content to the Upstage API.

## License

MIT © 2026 Upstage

Created by Mia (Seungmi Yoon)
