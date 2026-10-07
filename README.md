# korean-tax-calc-mcp — Korea Tax Calculator MCP (한국 세금 계산)

<!-- mcp-name: io.github.UpstageAI/korean-tax-calc-mcp -->

![데모: 법인세·가산세 계산](https://raw.githubusercontent.com/UpstageAI/korean-tax-calc-mcp/main/docs/demo.gif)

[![PyPI](https://img.shields.io/pypi/v/korean-tax-calc-mcp)](https://pypi.org/project/korean-tax-calc-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--calc--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-calc-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) · [English](README-EN.md)

**Korean tax calculations for AI agents — code, not guesses.** Corporate tax, entertainment limits, deemed interest, penalties, limitation periods, withholding, income tax and VAT, using year-by-year rate tables (2016–2025). Each result cites its statute. Years without a verified table stop with an error instead of estimating. 27 tools, no API key, nothing sent outside. → [English README](README-EN.md)

---

> 세금 계산은 AI가 자주 틀립니다. 이 서버는 계산을 코드로 하고, 결과마다 근거 조문을 붙입니다. 연도표가 없는 해는 추정하지 않고 멈춥니다.

**이렇게 물어보세요**

- "2025 사업연도 과세표준 5억 법인세 산출세액은?"
- "과소신고 1천만 원을 10월 7일에 납부하면 가산세는?"
- "가지급금 3월 1일 2억 대여, 9월 30일 1억 회수 — 인정이자 계산해줘"
- "중소기업 매출 100억, 기업업무추진비 5천만 원이면 한도초과액은?"
- "2018년 3월 31일 신고기한인 법인세 부과제척기간 만료일은? 부정행위면?"
- "퇴직금 1억, 근속 15년 퇴직소득세"
- "세금계산서 미발급 공급가액 5천만 원 가산세"
- "보증금 3억 상가 간주임대료 (184일)"

**설치 한 줄** — `claude mcp add korean-tax-calc -- uvx korean-tax-calc-mcp`

- **연도별 세율표** — 2016~2025 사업연도·귀속연도별 세율·한도율, 없는 해는 추정하지 않고 오류
- **근거 조문** — 모든 결과에 법·시행령 조문 표시
- **날짜 계산** — 가산세 이율 변경일 안분, 제척기간 만료일, 인정이자 적수
- **API 키 없음·외부 전송 없음** — 설치한 컴퓨터 안에서 코드로만 계산

## 설치

[uv](https://docs.astral.sh/uv/)가 있으면 설치 없이 바로 실행됩니다.

```json
{
  "mcpServers": {
    "korean-tax-calc": { "command": "uvx", "args": ["korean-tax-calc-mcp"] }
  }
}
```

Claude Code: `claude mcp add korean-tax-calc -- uvx korean-tax-calc-mcp`

근거 조문·해석은 [korean-tax-mcp](https://github.com/UpstageAI/korean-tax-mcp)와 함께 쓰면 "근거 찾기 → 계산"이 이어집니다.

## 도구

| 도구 | 계산 | 근거 |
|---|---|---|
| `corporate_tax` | 법인세 산출세액 (1년 미만 사업연도 포함) | 법인세법 제55조 |
| `entertainment_limit` | 기업업무추진비 한도·한도초과 | 법인세법 제25조 |
| `deemed_interest` | 가지급금 인정이자 (적수, 3억·5% 판정) | 법인세법 제52조, 영 제89조 |
| `unfair_transaction` | 부당행위계산 기준 (시가 차이 3억·5%) | 영 제88조③ |
| `loss_carryforward_limit` | 이월결손금 공제 한도율 | 법인세법 제13조 |
| `minimum_tax` | 최저한세 | 조특법 제132조 |
| `underreporting_penalty` | 과소신고가산세 (10%·40%) | 국세기본법 제47조의3 |
| `late_payment_penalty` | 납부지연가산세 (이율 변경일 안분) | 국세기본법 제47조의4 |
| `invoice_penalty` | 세금계산서 가산세 (가공·미발급·지연 등, 공급일 기준) | 부가가치세법 제60조 |
| `assessment_limitation` | 부과제척기간·만료일 (역외거래·상증 포함) | 국세기본법 제26조의2 |
| `income_tax` | 종합소득세 산출세액 | 소득세법 제55조 |
| `withholding_tax` | 원천징수세액 (소득 종류·지급연도) | 소득세법 제129조 |
| `retirement_income_tax` | 퇴직소득세 | 소득세법 제48조 |
| `vat_deemed_rent` | 간주임대료 | 부가가치세법 시행령 제65조 |
| `nonbusiness_interest_disallowance` | 업무무관자산 관련 지급이자 손금불산입 | 법인세법 제28조 |
| `business_car_expense` | 업무용승용차 관련비용 (업무사용비율·감가상각 한도) | 법인세법 제27조의2 |
| `donation_limit` | 기부금 한도·한도초과·이월 | 법인세법 제24조 |
| `bad_debt_allowance` | 대손충당금 한도 | 법인세법 제34조 |
| `missing_receipt_disallowance` | 적격증빙 미수취 기업업무추진비 | 법인세법 제25조② |
| `vat_deemed_input_credit` | 의제매입세액공제 | 부가가치세법 제42조 |
| `vat_common_input_allocation` | 공통매입세액 안분 | 부가가치세법 시행령 제81조 |
| `vat_simplified_taxpayer` | 간이과세자 납부세액 | 부가가치세법 제63조 |
| `vat_card_sales_credit` | 신용카드매출전표 발행세액공제 | 부가가치세법 제46조 |
| `vat_bad_debt_credit` | 대손세액공제 | 부가가치세법 제45조 |
| `wage_income_tax` | 근로소득공제·산출세액·근로소득세액공제 | 소득세법 제47·55·59조 |
| `daily_worker_withholding` | 일용근로자 원천징수 | 소득세법 제134조 |
| `deemed_bonus_resettlement` | 소득처분 상여 연말정산 재정산 | 소득세법 시행령 제192조 |

## 유의

- 계산 결과는 검토 보조 자료이며 세무 자문이 아닙니다. 신고 전 원문 조문과 확인하세요.
- 지방소득세는 별도입니다.
- 세율표가 검증되지 않은 연도는 계산하지 않고 오류를 돌려줍니다.
- **데이터 전송 안내** — 모든 계산은 설치한 컴퓨터 안에서 코드로 처리하며 외부 API로 전송하는 내용은 없습니다.

## 함께 쓰면 좋은 MCP

- [korean-tax-mcp](https://github.com/UpstageAI/korean-tax-mcp) — 국세청 해석·판례·통칙·시점별 조문

## 라이선스

MIT © 2026 Upstage

Created by Mia(윤승미)
