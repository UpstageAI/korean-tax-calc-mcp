# SPEC_form_templates4 — PR #36 리뷰 반영 · 작성 Claude 2026-10-25
브랜치 `feat/workbook-forms`(이어서). 정답 테스트 `tests/test_form_templates4.py` + 전체. 커밋 1개(제목: fix: 교차 참조 대체값·틀 회색 칸). push 금지, 테스트·틀 JSON 수정 금지.
1. 공개 함수 `load_templates() -> {key: 틀}`(data/form_templates 전부), `cross_fallback_value(ref_key, ref_id, *, templates, results) -> 숫자`: 대상 틀의 그 slot `check` 경로를 대상 틀 `tool`의 도구 결과(`results[tool]`)에서 `tool_value`로 읽음. check가 없거나 결과·값이 없으면 KeyError. 지금의 조정 소스 데이터 조회 방식은 버림.
2. 렌더러는 `{틀key!id}` 대상 틀이 없을 때 이 함수를 쓰고, KeyError면 내보내기 오류(입력 확인 필요 형식)로 — 셀에 `None` 문자열을 절대 쓰지 않음.
3. 틀 `cells`의 `fill`(예 `808080`·`BFBFBF`)을 그 범위 모든 칸에 단색 채우기로 적용.
