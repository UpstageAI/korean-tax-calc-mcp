# SPEC_form_style — 서식 시트 모양 마무리 · 작성 Claude 2026-10-25
브랜치 `feat/workbook-forms`(이어서). 정답 테스트 `tests/test_form_templates.py::test_render_style` + 전체 통과. 커밋 1개(제목: fix: 서식 시트 숫자 서식·행 높이·정렬). push 금지, 테스트·틀 JSON 수정 금지.
- slot·table 금액 칸: 수식을 쓴 **뒤에** `#,##0`, 오른쪽·세로 가운데 정렬(지금은 값 쓰기 전에 서식을 적용해 빈칸만 서식이 붙음). 틀 `formats`{셀: 서식}가 있으면 그것 우선.
- 행 높이: 틀 `default_row_height`를 서식 영역(print_area 행 범위) 모든 행에 적용한 뒤 `row_heights`로 덮어씀.
- 문구 칸: 모두 세로 가운데 + 줄바꿈(가로는 `al`).
- 틀 `fill`(회색 칸) 적용.
- `목록` 시트에서 도구 영문 이름 열은 빼고 시트 이름·서식 표기·(자료 없음/해당 없음) 줄만.
