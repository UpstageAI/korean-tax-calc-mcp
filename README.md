# korean-tax-calc-mcp — Korea Tax Calculator MCP (한국 세금 계산)

<!-- mcp-name: io.github.UpstageAI/korean-tax-calc-mcp -->

![데모: 손익계산서·계정별 원장 엑셀 → 적격증빙 미수취 선별·비지정기부금 손금불산입 → 세무조정 → 별지 제3·15·23·29호 법정서식에 수식 연결](https://raw.githubusercontent.com/UpstageAI/korean-tax-calc-mcp/main/docs/demo.gif)

<sub>영상: Claude 앱(코워크) + 이 서버. 손익계산서와 계정별 원장 엑셀을 주면 세무조정부터 법정서식 초안까지 한 번에 이어집니다(2026-11-08 공개, 회사·숫자는 가상 예시).</sub>

[![PyPI](https://img.shields.io/pypi/v/korean-tax-calc-mcp)](https://pypi.org/project/korean-tax-calc-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--calc--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-calc-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Built with Upstage Solar Pro 4](https://img.shields.io/badge/Built%20with-Upstage%20Solar%20Pro%204-7A3FF2)](https://www.upstage.ai/) · [English](README-EN.md)

> **작성 주체(정확한 고지):** 0.3.0부터 0.12.2까지(2026-10-10부터 10-26까지)는 **Solar Pro 4**(Solar Work CLI)가 코드를 쓰고 CodeSolar가 리뷰, Claude가 테스트로 교차 검증했습니다(0.8.0 일부 문법 오류와 0.9.2는 Claude가 수정·작성). **0.13.0(2026-10-28)부터는 기존 계산기 뼈대는 Solar Pro 4 그대로이고, 새 도구·연도별 조문 대조·버그 수정은 Claude(Anthropic)가 작성**하며 CodeSolar가 리뷰합니다. **0.26.0(2026-11-10)부터 새 도구는 Claude가 명세·정답 테스트를 먼저 쓰고 Solar Pro 4가 뼈대를 구현한 뒤 Claude가 검수·보완합니다**(커밋별 작성자 표기). 버전별 작성 주체는 [CHANGELOG](CHANGELOG.md) 각 절 머리에 적혀 있습니다. 도구 109개.

**Korean tax calculations for AI agents — code, not guesses.** [English](README-EN.md)

---

> 세금 계산은 AI가 자주 틀립니다. 이 서버는 계산을 코드로 하고, 결과마다 근거 조문을 붙입니다. 연도표가 없는 해는 추정하지 않고 멈춥니다.

## 작동 방식

```mermaid
flowchart LR
  Q["AI의 입력<br/>연도·금액·항목"] --> V["입력 확인<br/>모르는 항목·빠진 값 거부"]
  V --> T["그해 기준값<br/>세율·한도·공제율"]
  T --> E["계산<br/>조문 순서대로"]
  E --> R["결과<br/>세액·세무조정·근거 조문"]
  T -.->|표 없는 연도| X["멈춤<br/>추정 계산 안 함"]
```

1. **입력 확인** — 모르는 항목·빠진 값이 있으면 계산하지 않고 무엇이 필요한지 알려 줍니다.
2. **그해 기준값** — 세율·한도는 코드 안 연도표(법인세·소득세 2016–2026, 부가세 2016년 1기–2026년 2기), 항목별 판단 기준은 `facts_vocab.json`(적용 기간·근거 조문 포함)에서 꺼냅니다.
3. **계산** — 조문 순서대로 계산합니다. 예: 과세표준 → 그해 세율 구간 → 산출세액.
4. **결과** — 세액·중간 계산·항목별 판단·세무조정(소득처분)·근거 조문을 함께 돌려줍니다.

도구 115개 중 111개는 생성형 AI 없이 코드로 동작합니다(시세·공시가격 조회 2개는 KRX·브이월드 공개 데이터만 가져옵니다). PDF 도구 3개만 `UPSTAGE_API_KEY`가 있을 때 Upstage를 씁니다.

### 법인세 세무조정이 이어지는 모양

도구는 하나씩도 쓰지만, 법인세는 앞 도구의 결과가 다음 도구의 입력이 되도록 이어집니다.

```mermaid
flowchart TD
  L["장부·사실관계<br/>항목 이름·금액·증빙"] --> A["항목별 세무조정<br/>기업업무추진비·감가상각·대손<br/>인정이자·지급이자·승용차"]
  A -->|조정 목록| T["차가감소득금액<br/>income_adjustment_total"]
  T -->|기준소득| D["기부금 한도<br/>donation_limit"]
  D -->|한도초과액| T
  T --> B["과세표준<br/>이월결손금 한도"]
  B --> C["산출세액·최저한세<br/>corporate_tax · minimum_tax"]
  C --> X["검토용 엑셀<br/>export_workbook"]
```

항목별 조정 도구는 소득처분(유보·상여·기타사외유출 등)까지 돌려주고, `export_workbook`은 같은 호출을 다시 실행해 별지 서식끼리 수식으로 연결된 엑셀을 만듭니다. 어떤 도구를 쓸지 모르면 `find_tool`에 평소 말로 물어보면 됩니다.

## 이렇게 물어보세요

- "2025 사업연도 과세표준 5억 법인세 산출세액은?"
- "가지급금 3월 1일 2억 대여, 9월 30일 1억 회수 — 인정이자 계산해줘"
- "과소신고 1천만 원을 10월 7일에 납부하면 가산세는?"
- "퇴직금 1억, 근속 15년 퇴직소득세"
- "기업업무추진비 원장 5건 그대로 줄게 — 2025 사업연도 세무조정 뽑아줘"

## 설치

```bash
claude mcp add korean-tax-calc -- uvx korean-tax-calc-mcp
```

```json
{
  "mcpServers": {
    "korean-tax-calc": { "command": "uvx", "args": ["korean-tax-calc-mcp"] },
    "korean-tax":      { "command": "uvx", "args": ["korean-tax-mcp"], "env": { "LAW_OC": "법제처 OC(무료, 선택)" } }
  }
}
```

두 번째 줄의 [korean-tax-mcp](https://github.com/UpstageAI/korean-tax-mcp)는 조문·부칙·해석·판례를 찾는 짝 서버입니다. 같이 두면 **근거 찾기 → 계산 → 서식**이 한 대화에서 이어지고, 이 서버의 `find_tool`도 계산 도구가 없는 질문(월세·연금계좌 세액공제, 주식 양도 등)에 바로 부를 조문 호출값을 돌려줍니다. 계산만 쓰려면 첫 줄만 넣어도 됩니다.

새 버전으로 바로 바꾸려면 `uvx --refresh korean-tax-calc-mcp`(uvx는 받은 버전을 캐시합니다). 특정 버전 고정은 `uvx korean-tax-calc-mcp@0.28.1`.

키 없이 동작합니다. 선택: `LAW_OC`(세무조사 판정 도구 2개의 법제처 조문 조회), `UPSTAGE_API_KEY`(PDF 표 추출).

## 함께 쓰면 좋은 지침

AI가 도구를 언제 부르고, 도구의 답을 언제 믿을지 정해 주는 다섯 줄입니다. 서버 안내문(instructions)에도 같은 규칙이 들어 있지만, 클라이언트에 따라 안내문을 약하게 반영하거나 읽지 않습니다. 아래를 시스템 프롬프트에 넣으면 더 잘 지킵니다(Claude Desktop 프로젝트 지침, Claude Code의 `CLAUDE.md`, 그 밖의 맞춤 지침).

```text
세금 질문에 답할 때 korean-tax-mcp와 korean-tax-calc-mcp를 이렇게 쓴다.
1. 숫자 하나, 판단 하나마다 쓸 수 있는 도구가 있는지 먼저 찾는다. 이름을 모르면 find_tool로 찾고, 귀속·공급시기는 timing_rules를 먼저 본다.
2. 도구가 있으면 손으로 풀기 전에 도구부터 부른다.
3. 도구의 답과 내 계산이 다르면 바로 고르지 않는다. 입력을 다시 확인하고, 차이를 가르는 조문을 law_article로 열어 요건을 사실관계에 하나씩 맞춰 본다.
4. 조문에서 도구가 틀렸다는 근거를 못 찾으면 도구의 답을 따른다. 다른 값을 쓰면 그 이유(입력 오류 또는 조문 번호)를 한 줄 적는다.
5. 답이 두 개 나오면(안분 전후, 전체와 과세분 등) 질문이 묻는 하나만 답한다.
```

## 도구 (115개)

묶음 이름을 누르면 도구 목록이 펼쳐집니다.

<details>
<summary><b>법인세</b> (27)</summary>

| 도구 | 하는 일 |
|---|---|
| `corporate_tax` | 산출세액 |
| `foreign_tax_credit` | 외국납부세액공제 |
| `entertainment_limit` | 기업업무추진비 한도 |
| `deemed_interest` | 가지급금 인정이자 |
| `unfair_transaction` | 부당행위 기준 |
| `loss_carryforward_limit` | 이월결손금 한도 |
| `minimum_tax` | 최저한세 |
| `minimum_tax_adjustment` | 최저한세 조정(감면·공제 배제 순서·별지 제4호·제8호서식(갑)) |
| `nonbusiness_interest_disallowance` | 업무무관 지급이자(가지급금 제외 판정·적수·순위) |
| `business_car_expense` | 업무용승용차 |
| `donation_limit` | 기부금 한도 |
| `nonprofit_reserve_limit` | 비영리내국법인 고유목적사업준비금 손금산입 한도(법 제29조) |
| `bad_debt_allowance` | 대손충당금 한도 |
| `thin_capitalization` | 과소자본 |
| `missing_receipt_disallowance` | 적격증빙 미수취 |
| `dividend_received_deduction` | 수입배당금 익금불산입 |
| `foreign_subsidiary_dividend` | 외국자회사 수입배당금 익금불산입·외국납부세액공제 |
| `expat_cost_recharge` | 해외 파견 인건비 청구액·정상가격·손금·비과세 |
| `corporate_filing_obligations` | 외부감사·외부세무조정·국제거래 자료 제출 의무 판정 |
| `cfc_deemed_dividend` | 특정외국법인(CFC) 유보소득 배당간주액 — 저율과세·지분율 10%·적용제외·배당가능 유보소득·적용되는 배당간주(전부/수동소득) 판정(국조법 제27조~제31조) |
| `tax_adjustment_schedule` | 연도별 세무조정 묶음 — 여러 사업연도의 순손익·조정 → 각 사업연도 소득·이월결손금 공제·과세표준·산출세액·항목별 유보 잔액(법인세법 제14조·제13조·제67조) |
| `loss_carryforward_ledger` | 이월결손금 다기간 추적 — 발생 연도별 잔액, 연도별 공제액·과세표준, 공제기간 경과 소멸(법인세법 제13조①, 영 제10조②) |
| `foreign_subsidiary_liquidation` | 해외 자회사 청산 손익 — 의제배당 또는 청산손실과 손금 귀속 사업연도(법인세법 제16조①4호) |
| `arm_length_range` | 정상가격 범위와 조정액 — 비교대상 이익률로 사분위·전체 범위, 중위값, 분석대상 값의 범위 안 여부, 조정액(국조령 제15조⑤⑥) |
| `provision_reserve_ledger` | 충당부채(포인트·마일리지, 판매보증) 세무조정 다기간 추적 — 연도별 적립·사용·유효기간 소멸에 따른 손금불산입·손금산입·유보 잔액(법인세법 제40조) |
| `foreign_exchange_reporting` | 해외직접투자 해당 여부·외국환 신고(사전/사후) 기한·기관·서류, 사후관리 보고서 일정, 청산, 해외직접투자명세 기한 |
| `individual_foreign_tax_credit` | 거주자 외국납부세액공제 — 국가별 한도·조약 제한세율 상한·10년 이월·퇴직소득(소득세법 제57조) |
| `overseas_account_reporting` | 해외금융계좌 신고의무(월말 잔액 5억 초과)·면제·신고기한·미신고 과태료·수정신고 감경·소명 불이행 과태료(국조법 제53조·제90조) |
| `capital_gains_unfair_transaction` | 양도소득 부당행위계산 — 저가양도·고가취득 시가 재계산(3억·5% 기준), 증여 후 10년 내 양도 비교 판정(소득세법 제101조) |
| `asset_grant_reserve` | 일시상각충당금 |
| `corporate_deemed_rent_income` | 임대보증금 간주익금 |
| `liquidation_income` | 청산소득 |
| `disaster_loss_credit` | 재해손실세액공제 |

</details>
<details>
<summary><b>소득세·원천·양도·상속증여</b> (24)</summary>

| 도구 | 하는 일 |
|---|---|
| `income_tax` | 종합소득세 |
| `withholding_tax` | 원천징수 |
| `nonresident_withholding` | 비거주자 원천징수 |
| `retirement_income_tax` | 퇴직소득세 |
| `wage_income_tax` | 근로소득세 |
| `daily_worker_withholding` | 일용근로자 |
| `deemed_bonus_resettlement` | 소득처분 상여 재정산 |
| `special_tax_credit` | 특별세액공제 |
| `capital_gains_income` | 양도소득 |
| `inheritance_tax` | 상속세 |
| `gift_tax` | 증여세 |
| `estimated_business_income` | 추계 사업소득 |
| `personal_deduction` | 인적공제 |
| `pension_income` | 연금소득금액 |
| `income_loss_offset` | 결손금 공제 |
| `pension_account_withdrawal` | 연금계좌 인출 |
| `inheritance_gift_valuation` | 상속·증여재산 평가 |
| `capital_gains_tax` | 양도소득 산출세액 |
| `housing_deemed_rent_income` | 주택 간주임대료 |
| `housing_rental_income` | 주택임대소득(비과세·분리과세) |
| `child_tax_credit` | 자녀세액공제 |
| `dividend_tax_credit` | 배당세액공제(비교산출세액) |
| `religious_income` | 종교인소득 |
| `individual_donation_expense` | 개인사업자 기부금 필요경비 한도 |

</details>
<details>
<summary><b>부가세·가산세·제척기간·경정청구</b> (17)</summary>

| 도구 | 하는 일 |
|---|---|
| `vat_deemed_rent` | 간주임대료 |
| `vat_deemed_input_credit` | 의제매입세액 |
| `vat_common_input_allocation` | 공통매입세액 안분 |
| `vat_simplified_taxpayer` | 간이과세 납부세액 |
| `vat_card_sales_credit` | 카드 발행세액공제 |
| `vat_bad_debt_credit` | 대손세액공제(회수하면 매출세액 가산) |
| `underreporting_penalty` | 과소신고가산세 |
| `late_payment_penalty` | 납부지연가산세 |
| `withholding_late_payment_penalty` | 원천징수 납부지연가산세(국세기본법 제47조의5, 3%+일할, 한도) |
| `invoice_penalty` | 세금계산서 가산세 |
| `assessment_limitation` | 부과제척기간 |
| `refund_claim_deadline` | 경정청구 기한(통상 5년·후발적 3개월·증액경정분 3개월, 토·일·공휴일 기한 특례 반영) |
| `vat_exempt_use_deemed_supply` | 면세전용 간주공급 |
| `vat_input_tax_deduction` | 매입세액 공제 판정 |
| `vat_deemed_supply_items` | 간주공급 판정 |
| `vat_tax_base_adjustments` | 과세표준 조정 — 반품(환입)·에누리·할인·장려금·대손금, 마일리지·포인트 결제 거래의 공급가액(부가가치세법 제29조, 시행령 제61조) |
| `vat_supply_timing` | 공급시기 판정(예정·확정 귀속) |

</details>
<details>
<summary><b>사실관계·원장 → 세무조정</b> (15)</summary>

| 도구 | 하는 일 |
|---|---|
| `bad_debt_adjustment` | 대손 조정 |
| `entertainment_adjustment` | 기업업무추진비 조정 |
| `deemed_dividend_bonus_shares` | 무상주 의제배당 |
| `financial_income_aggregate` | 금융소득 합산 |
| `other_income_aggregate` | 기타소득 |
| `earned_income_gross_pay` | 근로소득 총급여 |
| `simplified_vat_return` | 간이과세 확정신고 |
| `vat_return_general` | 일반과세자 부가가치세 신고서(별지 제21호서식) 집계 — 부품 도구 결과를 차가감 납부(환급)세액까지 합산 |
| `vat_foreign_currency_base` | 외화 대가 부가가치세 과세표준 환산(시행령 제59조·제95조제3항) |
| `vat_reverse_charge` | 국외사업자 용역등 대리납부(법 제52조) |
| `common_input_tax` | 공통매입세액 정산 |
| `input_tax_recalculation` | 매입세액 재계산 |
| `bundled_supply_split` | 토지·건물 안분 |
| `depreciation_adjustment` | 감가상각 시부인 |
| `retirement_allowance_adjustment` | 퇴직급여충당금 |
| `deemed_dividend_capital_reduction` | 감자 의제배당 |
| `inventory_valuation_adjustment` | 재고자산 평가 |
| `income_adjustment_total` | 차가감소득금액 |

</details>
<details>
<summary><b>주식·재산 평가</b> (7)</summary>

| 도구 | 하는 일 |
|---|---|
| `stock_major_shareholder` | 주식 양도세 대주주 판정(주주 명부로 지분율·합산 범위까지) |
| `stock_capital_gains_tax` | 주식 양도소득세(과세 대상 여부·세율·예정신고기한) |
| `unlisted_stock_valuation` | 비상장주식 상속·증여 평가(순손익·순자산 가중평균, 할증) |
| `stock_basis_income_tax` | 비상장주식 소득세법 기준시가 |
| `building_standard_price` | 건물 기준시가(국세청 고시 산식) |
| `stock_price_lookup` | 상장주식 시세 조회(KRX) |
| `official_property_price` | 부동산 공시가격 조회(브이월드, VWORLD_KEY) |

</details>
<details>
<summary><b>세무조사 판정</b> (9)</summary>

| 도구 | 하는 일 |
|---|---|
| `related_judge` | 특수관계(생계를 함께하는 친족 포함) |
| `kinship_check` | 친족관계 |
| `ownership_ratio` | 간접보유비율 |
| `dominant_shareholder` | 지배주주 |
| `tunnelling_gift` | 일감몰아주기 |
| `tunnelling_gift_nts` | 일감몰아주기(국세청 산식) |
| `related_provision_at` | 특수관계 조문 위치 |
| `return_precheck` | 신고서 사전검토 |
| `precheck_schema` | 사전검토 입력 목록 |

</details>
<details>
<summary><b>PDF 표 추출</b> (3)</summary>

| 도구 | 하는 일 |
|---|---|
| `extract_relations` | 관계표 |
| `tunnelling_from_pdf` | 일감몰아주기 자료 |
| `return_precheck_pdf` | 법인세 신고서 |

</details>
<details>
<summary><b>국세징수</b> (1)</summary>

| 도구 | 하는 일 |
|---|---|
| `tax_priority_distribution` | 국세 우선권 매각대금 배분 |

</details>
<details>
<summary><b>엑셀 내보내기</b> (1)</summary>

| 도구 | 하는 일 |
|---|---|
| `export_workbook` | 계산 근거 엑셀 |

</details>
<details>
<summary><b>도구 찾기</b> (1)</summary>

| 도구 | 하는 일 |
|---|---|
| `find_tool` | 평소 말로 맞는 도구 찾기 |

</details>

- **계산 근거 엑셀**: `export_workbook`은 여러 도구 호출을 다시 실행해 법정서식 모양(별지 제3호·제4호·제8호(갑)·제15호·제21호·제23호(갑)(을)·제29호·제32호·제33호·제34호·제20호(1)·제16호의2·제26호(갑)(을)·제50호(을), 부가세 공제받지 못할 매입세액 명세서, 종합소득세 부속 명세서, 양도소득세 별지 제84호 신고서 세액 계산·부표1 양도소득금액 계산명세서 등)의 검토용 엑셀로 만듭니다. 금액 칸은 서식 산식 그대로의 수식이고 서식끼리 연결되며(모든 금액 칸이 '입력·가정' 이름이나 앞 칸을 가리키는 수식 — 도구 값을 숫자로 박지 않음), 도구 값과 대조하는 확인 칸이 붙습니다. 계산 과정을 보여 주는 참고 자료이며 세무조정계산서 작성·신고 대리가 아닙니다. 기업업무추진비는 `entertainment_limit` 도구로도 별지 제23호(갑)·(을)가 나옵니다.
- **원장 그대로 입력**: 세무조정 도구는 장부 항목(이름·금액·증빙·성격)을 그대로 받아 항목 판단 → 세무조정 → 소득처분까지 돌려줍니다.
- **쟁점 표시**: 비거주자 원천징수·과소자본 결과에는 다툼이 될 수 있는 지점과 확인할 자료를 함께 붙입니다(결론은 내리지 않음).
- **지원 연도**: 법인세 2016–2026 사업연도, 소득세 2016–2026 귀속연도, 부가가치세 2016년 1기–2026년 2기, 가산세·제척기간은 현행 조문. 그 밖의 연도는 오류로 멈춥니다. 지방소득세는 별도입니다.

## 처리하지 않는 경우

처리하지 못하는 경우에는 계산하지 않고 "입력 확인 필요"나 오류로 멈추거나, 결과의 `판단`에 "확인 필요"로 알립니다. 결과를 쓰기 전에 아래에 해당하는지 먼저 확인해 주세요.

**공통**
- 지원 연도 밖(법인세 2016–2026 사업연도, 소득세 2016–2026 귀속연도, 부가가치세 2016년 1기–2026년 2기)과 지방소득세
- 주택 수·특수관계·사업 관련성처럼 사실관계 판단이 먼저인 항목은 사용자가 판단해 넣은 값으로 계산합니다(도구가 판단하지 않음)
- 합병·분할 세무조정 전용 도구는 없습니다

<details>
<summary>도구별로 처리하지 않는 경우 (도구 설명에서 모음)</summary>

| 도구 | 처리하지 않는 경우 |
|---|---|
| `retirement_allowance_adjustment` | 확정기여형 전환 전 근무분 퇴직급여충당금(시행규칙 제31조제2항)은 입력한 금액을 떼어 두는 것까지만 처리 — 금액 계산, 확정기여형만 있는 회사의 입력, 그 몫의 지급·이전, 관련 부인누계 구분은 하지 않음. 별지 제33호서식 ⑧이 음수일 때의 익금산입 |
| `capital_gains_income`·`capital_gains_tax` | 분양권·조합원입주권·주식, 2018.4.1. 전 양도 지정지역 3주택 이상 가산, 주택 수 계산, 비과세 보유기간 예외, 주거용 전환, 고가주택 일부 양도 |
| `stock_capital_gains_tax` | 2019년 이전 국외주식, 파생상품, 양도차손 통산 |
| `housing_rental_income` | 겸용주택 주택 부분 판정, 공동소유 주택의 주택 수 판정(주택 수를 직접 넣으면 계산) |
| `dividend_tax_credit` | 종합소득공제가 금융소득 외 소득보다 큰 경우, 조세특례제한법 제104조의27 배당(2016–2018), 다른 세액공제·감면 |
| `religious_income` | 근로소득 선택 경로, 간이세액표·연말정산 세액, 비과세 요건 판정, 다른 기타소득과의 300만 원 합산 판정 |
| `gift_tax` | 상속세 및 증여세법 제58조제1항 단서(가산분 증여세가 제척기간 만료로 부과되지 않은 경우) |
| `inheritance_gift_valuation` | 토지·건물 소유자가 다를 때 환산가액 안분, 공동저당 안분 |
| `unlisted_stock_valuation` | 평가심의위원회, 자산별 시가의 평가기간 판정, 국외 비상장주식 |
| `vat_supply_timing` | 상품권·가공·무인판매기·국내 위탁판매·간주공급, 부동산 임대·선불 연회비, 외국항행용역, 폐업일 의제, 공급시기 후 발급 가산세(수출은 직수출·중계무역·보세구역반출·위탁판매수출·외국인도수출·위탁가공무역·원료반출 지원) |
| `vat_deemed_supply_items` | 2020년 제1기 이전 사용인 선물 한도 |
| `refund_claim_deadline` | 2016년 전 사유·통지, 2015년 전 개정 경과조치, 후발적 사유 해당 여부 판정 |
| `tax_priority_distribution` | 가압류채권 안분·흡수배당, 조세 상호간 흡수배당, 담보권 순환관계, 공과금, 납세담보 등(입력 확인 필요로 반환) |
| `individual_donation_expense` | 기부금 세액공제 금액 자체 |
| `stock_major_shareholder` | 시가총액 조회(사용자가 계산해 넣음) |
| `minimum_tax_adjustment` | 선박표준이익(119), 법인세법 제59조 감면·공제 순서와 적용제외 항목 한도, 기부금 한도 재계산, 공제감면세액계산서(부표)·추가납부세액(을) |

각 도구의 설명에 자세한 범위가 있습니다.
</details>

## 면책 및 고지

- **면책:** 이 도구의 결과는 세무 자문이 아닙니다. 법령·해석을 바탕으로 계산·판정 과정을 보여 주는 참고 자료이며, 실제 신고·세무조사·불복 판단은 세무사·회계사·변호사 등 전문가에게 확인하세요. 근거 조문·판례는 원문으로 확인하세요.
- **세무대리 아님:** 이 도구는 **세무사법 제2조의 세무대리**(세무조정계산서 작성, 신고 대리, 세무상담 등)를 수행하지 않으며, 그 업무는 세무사와 등록한 공인회계사·변호사만 할 수 있습니다(세무사법 제20조). 법령에 적힌 산식을 코드로 옮겨 입력값에 대한 계산 과정을 보여 주는 소프트웨어이고, 입력 사실관계의 확인과 최종 판단은 세무 전문가(세무사·회계사·변호사)와 함께 해 주세요.
- **AI 사용 고지:** 계산·판정·조회 도구 101개는 코드로 동작하며 생성형 AI를 쓰지 않습니다. PDF 검토 도구 3개(`extract_relations`, `tunnelling_from_pdf`, `return_precheck_pdf`)는 UPSTAGE_API_KEY가 있으면 생성형 AI(Upstage Solar Pro 4)로 표를 추출하며 결과에 그 사실을 표시합니다. 키가 없으면 pypdf로 로컬 텍스트 추출(host_ai 모드) 후 정리 안내에 따라 다음 도구 입력으로 직접 정리할 수 있습니다.
- **데이터 전송:** UPSTAGE_API_KEY를 설정해 PDF 도구를 사용할 때만 문서 내용이 Upstage API(api.upstage.ai)로 전송됩니다. 시세 조회(`stock_price_lookup`)는 KRX로 종목코드·날짜를, 공시가격 조회(`official_property_price`, VWORLD_KEY 필요)는 브이월드로 주소·필지번호·연도를 보냅니다. 키 없이 사용하면(pypdf 로컬 추출) 외부 전송이 없습니다. 민감정보가 담긴 문서는 API 전송 시 넣지 마세요.

## 라이선스

MIT © 2026 Upstage · Created by Mia(윤승미)
