# SPEC_gold_gaps3 — 인적공제·연금소득·결손금 공제·재해손실세액공제 이식과 보강 · 작성 Claude 2026-10-24

브랜치 `feat/gold-gaps3`(main에서). 정답 테스트 `tests/test_gold_gaps3.py`(11개) + `tests/test_b1_*.py`(27개, 예전 정답 테스트 그대로) + 기존 전부 통과. 커밋 2개: ① 이식 ② 보강. push 금지, 테스트 수정 금지.

## 왜
정답 인자 세트에서 도구가 없던 인적공제(2문항+)·연금소득·결손금 통산(2문항)·재해손실세액공제(2문항)는 로컬 브랜치 `feat/itemized`에 이미 만들어 둔 도구 4개(personal_deduction·pension_income·income_loss_offset·disaster_loss_credit, 항목형 입력)로 풀린다(맞는 입력으로 정답 재현 확인). main에 없을 뿐이다. 남은 실패 지점은 모델이 앞 단계 계산을 손으로 해야 하는 곳(연금 과세분 비율, 전년도 결손금 이월액)이라 그 계산을 도구로 옮긴다.

## 1. 이식 (커밋 ①: `feat: 계산 도구 4개 — 인적공제·연금소득금액·결손금 공제·재해손실세액공제`)
- `feat/itemized`의 다음 커밋 내용을 main 위로 옮긴다(cherry-pick 또는 수동 적용, 충돌은 main 쪽 기존 동작을 유지하는 방향으로 해결): 06c2af5, bbdbcd9, 1aafcb7, 7ff558b, a3689d0, 9540dea, 45f830c. **bff9013은 옮기지 않는다**(다른 실험분).
- 대상: `engine/calc.py`·`engine/calc_income.py`의 해당 함수, `data/personal_income_rules.json`, `server.py` 도구 4개 등록. README·버전은 건드리지 않음.
- main에 이미 있는 이름·상수(`calc_income.RELATION_SYNONYMS`, `ALLOWED_RELATIONS` 등)와 겹치면 main 것을 쓰고 중복 정의하지 않는다.
- 이식 후 `tests/test_b1_*.py` 27개 통과.

## 2. 보강 (커밋 ②: `feat: 인적공제 관계 동의어·연금 과세분 비율·결손금 이전 연도 자동 이월`)
### 2-1. personal_deduction
- `persons[].relation`: main의 `RELATION_SYNONYMS`로 정규화(아들·딸·자녀 → 직계비속, 부친·모친·부모 → 직계존속 등). 정규화 후에도 허용값(배우자·직계존속·직계비속·입양자·형제자매·수급자·위탁아동) 밖이면 error `"입력 확인 필요 — persons '…': relation '…' 허용값 아님 — …"`. 도구 설명의 오타 `직계비즈속` → `직계비속`.
- `income_items` kind에 `공적연금_과세제외` 추가: 연금보험료 소득공제를 받지 않은 기여분에서 나온 공적연금(소득세법 시행령 제40조 과세제외기여금 몫). 소득금액에 0으로 반영, 처리 문장 `"과세 제외 — 소득공제 받지 않은 기여금 기초 연금 (소득세법 시행령 제40조)"`.
### 2-2. pension_income
- 새 선택 인자 `public_pension_detail: {수령액, 환산소득_2002이후, 환산소득_전체, 과세제외기여금?(기본 0)}`. 공적연금 과세분 = `max(0, int(수령액 × 환산소득_2002이후 ÷ 환산소득_전체) − 과세제외기여금)`(소득세법 시행령 제40조①, 국민연금 기준). 판단·산식에 비율을 적는다.
- `public_pension`(0 아님)과 `public_pension_detail`을 함께 주면 error. 환산소득_전체 ≤ 0이거나 2002이후 > 전체면 error.
### 2-3. income_loss_offset
- 새 선택 인자 `history: [{year, incomes, business?, financial_flat_rate?, estimated?}]` — 대상 연도보다 앞선 연도들. year 오름차순으로 같은 규칙(제45조)으로 계산하고, 각 연도의 남은 결손금(사업·부동산임대 구분, 발생 연도 포함)을 다음 연도의 carryforwards로 넘긴다. 이월 공제 기한(발생 연도별 10년·15년)은 기존 규칙 그대로.
- 대상 연도 결과의 `계산`(또는 결과)에 `이력_계산: [{year, 종합소득금액, 남은_결손금}]`을 남긴다.
- `history`와 `carryforwards`를 함께 주면 error `"입력 확인 필요 — history와 carryforwards 중 하나만"`. history의 year가 대상 연도 이상이면 error.
### 2-4. disaster_loss_credit — 공제대상 법인세 항목형 입력(법 제58조①, 영 제95조③)
조문 확인(2023·2025 시행본 동일): 영 제95조③ "법 제58조제1항 각 호에 따른 법인세액에는 법 제75조의3과 국세기본법 제47조의2부터 제47조의5까지의 규정에 따른 가산세를 포함". 당기 법인세는 산출세액에서 다른 법률(조세특례제한법 등)에 따른 공제·감면세액을 뺀 금액이고, 법인세법상 공제(외국납부세액공제 등)는 빼지 않는다.
- 새 선택 인자 `credit_items: [{종류:'조세특례제한법'|'법인세법', 금액}]` — '조세특례제한법'만 current_tax에서 차감, '법인세법'은 차감하지 않고 판단에 `"법인세법상 공제 — 공제대상 법인세에서 빼지 않음"`.
- 새 선택 인자 `penalty_items: [{근거:'법인세법 제75조의3'|'국세기본법 제47조의2'|'국세기본법 제47조의3'|'국세기본법 제47조의4'|'국세기본법 제47조의5'|'기타', 금액}]` — '기타'를 뺀 나머지만 가산(영 제95조③), '기타'는 판단에 제외 사유.
- `unpaid_prior_tax`는 미납 법인세 전액(그 안의 가산세 포함)으로 받는다.
- `other_credits`와 `credit_items`, `penalty`와 `penalty_items`를 함께 주면 error. 기존 other_credits·penalty 입력은 그대로 동작(호환).
- 공제액은 상실된 자산가액을 넘지 않는다(법 제58조① 괄호) — 이미 있으면 유지.

## 금지
- 기존 도구·결과 키 이름 변경 금지. 새 외부 패키지 금지. 버전·CHANGELOG·README 도구 수는 건드리지 않음.
