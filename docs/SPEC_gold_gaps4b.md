# SPEC_gold_gaps4b — 부가세 판정 도구 입력 검증 보강 · 작성 Claude 2026-10-24
브랜치 `feat/gold-gaps4`(이어서). 정답 테스트 `tests/test_gold_gaps4b.py` 3개 + 기존 전부 통과. 커밋 1개. push 금지, 테스트 수정 금지.
1. `period`는 `YYYY-1`·`YYYY-2`만(YYYY는 4자리 숫자). `2025-3`·`abc`는 `{"error": "입력 확인 필요 — 계산하지 않음", "문제": ["period ..."]}` 형식으로(파이썬 예외 문장 노출 금지). 두 도구 모두.
2. vat_input_tax_deduction의 `공급가액`·`공급대가`·`실제공급가액`과 vat_deemed_supply_items의 `금액`·`시가`·`감가상각`·`1인당_연간금액`이 음수면 같은 형식의 error(어느 항목·어느 키인지 문장에).
