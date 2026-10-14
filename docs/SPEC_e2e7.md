# SPEC e2e7 — 입력 단일화(원장형만)·같은 입력 재호출 안내 (2026-10-14, korean-tax-calc-mcp 0.9.0)

배경(28회차): 0.8.0에서 원장형 입력(ledger)을 **대안**으로 추가했더니 모델은 160문항에서 2번만 골랐고, 옛 구조 입력으로 현금영수증·실지귀속 항목을 또 빠뜨렸다(2025-76·2024-76). 또 결과가 기대와 다르면 같은 인자로 계산기를 15번 반복 호출하다 무응답으로 끝났다. 설명으로는 안 바뀌므로 **입력 형태를 하나로 줄이고**, **반복 호출을 도구가 알려 준다**.

규칙·기준값은 어휘(`facts_vocab.json`, 수정 금지)에서만. `tests/` 아래 파일·`docs/SPEC_e2e7.md` 수정 금지.

## A. 세 계산기의 입력을 원장형 하나로 (스키마에서 옛 입력 제거 — 호환 깨짐, 0.9.0)
| 도구 | 제거하는 파라미터 | 남기는 파라미터 |
|---|---|---|
| `entertainment_adjustment` | `expenses`, `revenue_general`, `revenue_related` | `year`, `sme`, `months`, **`ledger`(필수)**, `revenue`(선택, 없으면 수입금액 0) |
| `simplified_vat_return` | `supplies`, `purchases` | `year`, `business_type`, `prior_year_supplies`, **`ledger`(필수)**, `bad_debt_confirmed`, `prepaid_assessed` |
| `common_input_tax` | `input_tax` | `year`, `period`, `filing`, `supplies`, **`ledger`(필수)**, `new_business`, `prior_nondeductible`, `prior_common_input_tax`, `prior_period_supplies`, `common_asset_sales` |

- 함수 시그니처·도구 설명·README에서 옛 파라미터를 지운다. 내부 계산 코드는 0.8.x의 ledger 경로를 그대로 쓴다(옛 입력 → 내부 필드 변환 코드는 삭제해도 되고 남겨도 되나 스키마에 노출되면 안 됨)
- 빈 원장은 계산하지 않는다: `ledger`가 `[]`이거나 `{"공급": [], ...}`처럼 공급 항목이 없으면 `{"error": "입력 확인 필요 — 원장 항목이 없음", "허용값": ...}`
- `entertainment_adjustment`의 ledger 항목 `증빙`이 허용값('없음'|'영수증 등'|'적격') 밖이면 `error`(허용값 목록 포함, 어휘 `_specs_from_vocab("entertainment_adjustment", "evidence")`와 같은 목록). 0.8.x는 '검토 필요'로 넘겼음 → 계산하지 않음으로 통일
- 도구 설명(docstring) "입력"은 원장 항목 형태만 적는다. 옛 필드명(expenses·supplies·input_tax)은 설명 어디에도 남기지 않는다(모델이 보면 쓴다)
- 옛 입력 사용자(잠근 테스트)는 `tests/_legacy_to_ledger.py` 변환기로 이미 옮겨 둠 — 서버가 옛 키를 받을 필요 없음

## B. 같은 입력 재호출 안내 — `_guard` 공통
- `_guard`로 감싼 모든 계산기에 적용. 키 = (도구 이름, 인자를 `json.dumps(sort_keys=True, ensure_ascii=False, default=str)`로 정규화한 문자열). 프로세스 안에서 호출 횟수를 센다(최근 500개만 보관, 오래된 것부터 버림)
- 같은 키가 2번째 이상이면 결과 dict **맨 앞**에 `"안내": "같은 입력으로 {n}번째 계산입니다. 결과는 처음과 같습니다 — 빠진 사실이나 잘못 넣은 값이 없다면 이 결과를 그대로 쓰세요"` 를 넣는다(그 다음이 `결과`). `error` 결과에도 똑같이 붙인다
- 인자가 하나라도 다르면 새 키(안내 없음). 첫 호출에는 아무것도 붙이지 않는다
- 테스트용으로 `_reset_call_memo()` 함수를 둔다(모듈 수준, 도구 아님)

## C. 기타
- `pyproject`·`__init__`·`server.json` 0.9.0, CHANGELOG 0.9.0(호환 깨짐 명시: 세 도구의 옛 입력 제거)
- README의 세 도구 입력 설명을 원장형으로 교체

## 완료 조건
`tests/test_e2e7_golden.py` + 기존 전부 통과(옛 입력 테스트는 변환기를 거치므로 그대로 통과해야 함). `.venv/bin/python -m pytest tests -q`
