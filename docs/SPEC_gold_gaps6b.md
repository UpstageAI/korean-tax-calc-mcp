# SPEC_gold_gaps6b — 연금계좌 날짜 순서 검증 · 작성 Claude 2026-10-24
브랜치 `feat/gold-gaps6`(이어서). 정답 테스트 `tests/test_gold_gaps6b.py` 1개 + 기존 전부 통과. 커밋 1개. push 금지, 테스트 수정 금지.
1. pension_account_withdrawal: `join_date`가 `start_request_date`보다 늦거나, `birth_date`가 `join_date`보다 늦으면 `{"error": "입력 확인 필요 — 계산하지 않음", "문제": ["join_date ..."]}`(날짜 순서 문장). 다른 검사보다 먼저.
