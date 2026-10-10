# korean-tax-calc-mcp — Korea Tax Calculator MCP (한국 세금 계산)

<!-- mcp-name: io.github.UpstageAI/korean-tax-calc-mcp -->

![데모: 법인세·가산세 계산](https://raw.githubusercontent.com/UpstageAI/korean-tax-calc-mcp/main/docs/demo.gif)

[![PyPI](https://img.shields.io/pypi/v/korean-tax-calc-mcp)](https://pypi.org/project/korean-tax-calc-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--calc--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-calc-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Built with Upstage Solar Pro 4](https://img.shields.io/badge/Built%20with-Upstage%20Solar%20Pro%204-7A3FF2)](https://www.upstage.ai/) · [English](README-EN.md)

> **0.3.0부터 업스테이지 Solar Pro 4로 개발합니다.** (0.2.1까지는 Solar Pro 4 이전 개발분) 2026년 법인세율, 비거주자 원천징수(`nonresident_withholding`), 과소자본(`thin_capitalization`)은 Solar Pro 4(Solar Code CLI)가 코드를 작성하고, Solar Pro 4 기반 코드 리뷰(CodeSolar)가 PR을 검토했으며, Claude가 테스트로 교차 검증했습니다. **0.4.0: 세무조사 판정 도구 11개 통합. 0.5.1: precheck_schema 추가·41개 도구로 확대, description·인자 설명 전면 정비.**

**Korean tax calculations for AI agents — code, not guesses.** Corporate tax, entertainment limits, deemed interest, penalties, limitation periods, withholding, income tax and VAT, using year-by-year rate tables (2016–2026). Each result cites its statute. Years without a verified table stop with an error instead of estimating. 41 tools (29 computation + 12 tax audit judgment) — precheck_schema 추가로 41개. → [English README](README-EN.md)

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

- **연도별 세율표** — 2016~2026 사업연도·귀속연도별 세율·한도율, 없는 해는 추정하지 않고 오류
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
| `vat_deemed_input_credit` | 의제매입세액공제(연장·운반비 제외·공통분 안분) | 부가가치세법 제42조, 시행령 제81·84조 |
| `vat_common_input_allocation` | 공통매입세액 안분 | 부가가치세법 시행령 제81조 |
| `vat_simplified_taxpayer` | 간이과세자 납부세액 전 과정(과세표준·매입공제·카드공제·가산세·면제판정) | 부가가치세법 제46·63·68조의2·69조 |
| `vat_card_sales_credit` | 신용카드매출전표 발행세액공제 | 부가가치세법 제46조 |
| `vat_bad_debt_credit` | 대손세액공제 | 부가가치세법 제45조 |
| `wage_income_tax` | 근로소득공제·산출세액·근로소득세액공제 | 소득세법 제47·55·59조 |
| `daily_worker_withholding` | 일용근로자 원천징수 | 소득세법 제134조 |
| `deemed_bonus_resettlement` | 소득처분 상여 연말정산 재정산 | 소득세법 시행령 제192조 |

### 세무조사 판정 (11개)

| 도구 | 계산·판정 | 근거 |
|---|---|---|
| `related_judge` | 두 당사자의 특수관계 여부·호수를 국세기본법·법인세법·상증법 기준으로 판정(기준일 YYYY-MM-DD 필수) | 국세기본법 시행령 제1조의2, 법인세법 시행령 제2조, 상증법 시행령 제2조의2 |
| `kinship_check` | 두 개인의 친족관계(촌수·배우자)와 기준일 친족 범위 해당 여부 | 국세기본법 시행령 제1조의2①, 상증법 시행령 제2조의2①1호 |
| `ownership_ratio` | 보유자→법인 직접·간접 보유비율(경로별 곱, 순환출자 반영) | 상증법 시행령 제34조의3② |
| `dominant_shareholder` | 수혜법인 지배주주 판정(최대주주등 중 직접보유 최고자 / 법인이면 직접+간접 최고 개인) | 상증법 시행령 제34조의3① |
| `tunnelling_gift` | 일감몰아주기 증여의제이익(상증법 제45조의3) — ⑩항 과세제외매출액 입력, ⑭·⑮ 미반영 | 상증법 제45조의3, 시행령 제34조의3 |
| `tunnelling_gift_nts` | 일감몰아주기 증여의제이익 — 국세청 2026 신고안내 산식(⑫·⑭1·3호·⑮ 배당공제) | 상증법 제45조의3, 시행령 제34조의3, 국세청 2026 신고안내 |
| `related_provision_at` | 특수관계인 범위 조문이 기준일에 어디 있었는지(law=국기|법인|상증) — LAW_OC 있으면 법제처 API, 없으면 고정 이동표 | 국세기본법·법인세법·상증법 시행령 |
| `extract_relations` | 주주명부·가족관계·임원명단 PDF → 관계표 추출. UPSTAGE_API_KEY 없이도 pypdf 로컬 추출 후 related_judge 입력으로 정리 가능(기본). 키 설정 시 Document Parse + Solar Pro 4로 더 정교한 표 추출 | — |
| `tunnelling_from_pdf` | 일감몰아주기 검토 자료 PDF → 표 추출 → 지배주주·출자관계·증여의제이익 계산. UPSTAGE_API_KEY 없이도 pypdf 로컬 추출 후 입력 정리 가능(기본). 키 설정 시 Document Parse + Solar Pro 4로 더 정교한 표 추출 | 상증법 제45조의3 |
| `return_precheck` | 신고서 사전검토(오류 의심 목록): data={입력키: 값}, tax=법인|부가|소득 — audit/agents/precheck 규칙 엔진 사용 | 서식별 근거 조문(각 규칙 근거 참조) |
| `return_precheck_pdf` | 법인세 신고서 PDF(별지 1·3·50호) → 표 추출 → 사전검토. UPSTAGE_API_KEY 없이도 pypdf 로컬 추출 후 return_precheck 입력으로 정리 가능(기본). 키 설정 시 Document Parse + Solar Pro 4로 더 정교한 표 추출 | 서식 간 대사·세액 체인 재계산 |
| `precheck_schema` | 신고서 사전검토 입력스키마 반환: tax=법인|부가|소득 지정 시 해당 세목 입력키의 의미·단위·필수 여부 목록 제공. return_precheck·PDF 도구 입력 전에 먼저 호출 | 각 규칙의 needs 기반 요건별 필수·선택 구분 |

## 쟁점 표시

비거주자·외국법인 원천징수(`nonresident_withholding`)와 과소자본(`thin_capitalization`) 결과는 계산된 세액과 함께 **쟁점** 리스트를 반환할 수 있습니다. 쟁점은 "이 소득 구분이 맞는지", "이 조약 세율이 그대로 적용되는지"처럼 실무에서 다툼이 될 수 있는 지점을 정리한 것으로, 도구는 결론을 내리지 않고 **확인할 자료와 참고 근거(조문·적부·판례 번호)**만 제시합니다. 각 쟁점 항목의 `판단` 필드는 항상 "세무사 확인 필요"로 고정되어 있으며, 도구가 "사업소득임", "사용료임" 같은 단정 문구를 결과 어디에도 쓰지 않습니다. 쟁점 데이터는 코드 하드코딩 없이 `korean_tax_calc_mcp/data/issues.json`에서 읽어옵니다.

## 면책 및 고지

- **면책:** 이 도구의 결과는 세무 자문이 아닙니다. 법령·해석을 바탕으로 계산·판정 과정을 보여 주는 참고 자료이며, 실제 신고·세무조사·불복 판단은 세무사·회계사·변호사 등 전문가에게 확인하세요. 근거 조문·판례는 원문으로 확인하세요.
- **AI 사용 고지:** 계산·판정 도구 29개는 코드로 동작하며 생성형 AI를 쓰지 않습니다. PDF 검토 도구 3개(`extract_relations`, `tunnelling_from_pdf`, `return_precheck_pdf`)는 UPSTAGE_API_KEY가 있으면 생성형 AI(Upstage Solar Pro 4)로 표를 추출하며 결과에 그 사실을 표시합니다. 키가 없으면 pypdf로 로컬 텍스트 추출(host_ai 모드) 후 정리 안내에 따라 다음 도구 입력으로 직접 정리할 수 있습니다.
- **데이터 전송:** UPSTAGE_API_KEY를 설정해 PDF 도구를 사용할 때만 문서 내용이 Upstage API(api.upstage.ai)로 전송됩니다. 키 없이 사용하면(pypdf 로컬 추출) 외부 전송이 없습니다. 민감정보가 담긴 문서는 API 전송 시 넣지 마세요.

## 유의

- 계산 결과는 검토 보조 자료이며 세무 자문이 아닙니다. 신고 전 원문 조문과 확인하세요.
- 지방소득세는 별도입니다.
- 세율표가 검증되지 않은 연도는 계산하지 않고 오류를 돌려줍니다.
- **데이터 전송 안내** — 계산·판정 도구 29개는 설치한 컴퓨터 안에서 코드로 처리하며 외부 API로 전송하는 내용은 없습니다. PDF 도구 3개만 Upstage API로 문서를 전송합니다.

## 지원 연도

세목별 연도표는 2016~2026을 지원하며, 표에 없는 연도는 추정 계산하지 않고 오류로 멈춘다. 연도는 사업연도·귀속연도·지급연도·과세기간 기준으로 세목마다 적용 기간이 다르다.

| 세목 | 도구 예시 | 지원 연도 | 기준 |
|---|---|---|---|
| 법인세 | `corporate_tax`, `entertainment_limit`, `minimum_tax` 등 | 2016~2026 사업연도 | calc_cit.YEAR (법인세법 제55조 등) |
| 소득세(종합소득세) | `income_tax`, `wage_income_tax` | 2016~2026 귀속연도 | calc_income.RATES (소득세법 제55조) |
| 원천징수 | `withholding_tax`, `daily_worker_withholding` | 2016~2026 지급연도 | 소득세법 제129조·제134조 |
| 비거주자·외국법인 원천징수 | `nonresident_withholding` | 조약별 (국내세율은 현행) | 소득세법 제156조 / 법인세법 제98조 |
| 과소자본 손금불산입 | `thin_capitalization` | 사업연도 기준 (현행 국조법 제22조) | 국제조세조정법 제22조 |
| 부가가치세 | `vat_deemed_rent`, `vat_simplified_taxpayer` 등 | 2016년 1기 ~ 2026년 2기 | calc_vat 연도표 (부가가치세법) |
| 가산세·제척기간 등 | `invoice_penalty`, `assessment_limitation` 등 | 현행 조문 (날짜 기준 적용) | 국세기본법·부가가치세법 등 |

## 함께 쓰면 좋은 MCP

- [korean-tax-mcp](https://github.com/UpstageAI/korean-tax-mcp) — 국세청 해석·판례·통칙·시점별 조문

## 라이선스

MIT © 2026 Upstage

Created by Mia(윤승미)
