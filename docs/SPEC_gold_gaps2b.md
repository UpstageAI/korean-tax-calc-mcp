# SPEC_gold_gaps2b — 새 도구 5개 검수 반영 · 작성 Claude 2026-10-24

브랜치 `fix/gold-gaps2`. `korean_tax_calc_mcp/server.py`의 새 도구만 고친다. `tests/test_gold_gaps2.py` 21개(새 6개 포함) + 기존 전부 통과. 커밋 1개. push 금지, 테스트 수정 금지.

1. `vat_exempt_use_deemed_supply` 비상각 경로: `int(시가를)` 오타로 NameError → `int(시가)`.
2. `vat_exempt_use_deemed_supply` 입력 검증: `구분`이 '건물'|'구축물'|'기타'|'토지'|'비상각' 밖이면 error. 경과과세기간수가 음수(전용일이 취득일보다 앞선 과세기간)면 error `"입력 확인 필요 — 자산 '…': 전용일이 취득일보다 앞섬"`.
3. `estimated_business_income`: `multiplier`는 배율이라 `_rate_norm`을 쓰지 않는다(2.8은 2.8). `revenues`·`expenses`의 `구분`이 허용값 밖이면 error(조용히 빼지 않음).
4. `corporate_deemed_rent_income`: `임대면적비율`도 `_rate_norm`으로(20 → 0.2). 0을 주면 0으로(지금은 `or 1` 때문에 1이 됨), 키가 없을 때만 기본 1.
5. `income_adjustment_total`: `방향`이 '가산'|'차감'|'없음' 밖이면 error.
