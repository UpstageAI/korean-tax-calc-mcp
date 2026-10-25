# SPEC_form_templates2b — 2단계 검수 반영 · 작성 Claude 2026-10-25
브랜치 `feat/workbook-forms`(이어서). 정답 테스트 `tests/test_form_templates2.py`(추가 2개) + 전체. 커밋 1개(제목: fix: 틀 없는 계산 시트는 계산식 모양 유지, slot별 검증 열). push 금지, 테스트·틀 JSON 수정 금지.
1. forms에서 틀 없는 call의 `계산 N` 시트가 키·값 나열로 바뀜(회귀). layout=steps의 `계산 N`(계산식_입력 표 + 계산식 단계 수식 + 도구 값·확인 열, 세무조정 표)을 그대로 만드는 같은 함수를 호출할 것.
2. slot에 `check_col`이 있으면 그 slot 검증은 그 열(도구 값)과 바로 오른쪽(확인)에. 없으면 틀의 `check_col`. (별지15 ②합계 J·⑤합계 L)
