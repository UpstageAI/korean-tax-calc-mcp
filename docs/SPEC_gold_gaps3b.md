# SPEC_gold_gaps3b — 인적공제 입력 오류 문장 · 작성 Claude 2026-10-24
브랜치 `feat/gold-gaps3`(이어서). 정답 테스트 `tests/test_gold_gaps3b.py` 2개 + 기존 전부 통과. 커밋 1개. push 금지, 테스트 수정 금지.
1. personal_deduction에서 persons 항목에 `birth_year`가 없으면 KeyError 문장(`입력 오류: 'birth_year'`) 대신 `{"error": "입력 확인 필요 — 계산하지 않음", "문제": ["persons[0] (직계비속): birth_year 필요 ..."]}`. taxpayer도 같은 규칙.
2. 오타 `계산하기 않음` → `계산하지 않음`(서버 전체).
