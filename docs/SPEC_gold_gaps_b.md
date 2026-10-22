# SPEC_gold_gaps_b — SPEC_gold_gaps 마무리(시간 초과분) · 작성 Claude 2026-10-22

작업 트리에 SPEC_gold_gaps.md의 수정이 미커밋 상태로 있다(server.py·calc_cit.py·calc_inhgift.py·facts_vocab.json, tests/test_gold_gaps.py). 이어서 아래 3가지만 끝내고 커밋 2개(test 먼저: `test: 정답 인자 대조 도구 공백 5건 정답 테스트`, fix: `fix: 공통사용재화 매입세액 직전기 안분·3개월 제외 적수 차감·현물 접대비 평가·사적사용·신축건물 면적비율·legal_share 소수`). push 금지. 현재 상태: 3 failed, 525 passed.

## 1. 사적사용 손금불산입이 손금불산입_합계에 빠짐
`tests/test_gold_gaps.py::test_entertainment_private_use_is_bonus_not_limit_test`: 직부인_대표자상여 1,000,000은 맞는데 `손금불산입_합계`가 0. 손금불산입_합계 = 직부인(없음·사적사용 등 상여) + 직부인(영수증 등 기타사외유출) + 한도초과. `소득처분별_합계["상여"]`에도 들어가야 한다.

## 2. 기존 테스트 2개의 기대값을 새 규칙(현물 = max(시가, 장부가액) + 부가세 10%)에 맞춰 갱신
둘 다 도구 초기 설계값을 적은 실무형 테스트이고, 현물 접대 시 매출세액 상당액을 접대비에 포함하는 것이 현행 실무(법인세법 기본통칙 25-0…, 시행령 제42조⑥)다. 테스트 주석에 "현물은 시가·장부가액 중 큰 금액 + 부가세"로 고친다.
- `tests/test_e2e6_golden.py::test_ledger_exclusions_and_in_kind_valuation`: 현물 시가 3,000,000·장부 4,000,000 → 4,400,000. `k["시부인 대상"] == 4_400_000`, 한도 15,000,000, 한도초과 0 그대로.
- `tests/test_e2e6_golden.py::test_2026_62_ledger_forward`: 시부인 대상 90,000,000 → 91,500,000(현물 15,000,000 × 1.1), 한도 64,760,000 그대로, 한도초과 25,240,000 → 26,740,000. 같은 테스트 안의 다른 단언(세무조정 금액 등)도 한도초과 26,740,000에 맞춘다.

## 3. 확인
- `python3 -m pytest -q tests` 전부 통과(skip 1 허용).
- 도구 설명(entertainment_adjustment docstring)에 `부가세별도`(기본 True) 키와 '사적사용' 성격이 적혀 있는지 확인. 없으면 적는다.
