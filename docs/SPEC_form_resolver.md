# SPEC_form_resolver — 서식 틀 토큰 해석을 작은 함수로 · 작성 Claude 2026-10-25
브랜치 `feat/workbook-forms`(이어서). 정답 테스트 `tests/test_forms_resolver.py`(함수 단위) + `tests/test_form_templates.py` + 기존 전부. 커밋 1~2개. push 금지, 테스트·틀 JSON 수정 금지.

## 왜
지금 렌더러는 토큰 해석이 export 함수 안에 길게 섞여 있고, `[계산.X]`·`[결과.X]`를 값이 아닌 통합 문서 이름(`호출1_결과_X` 등)으로 바꿔 다른 call 값이 섞임(데모에서 ⑪에 72,500,000). SPEC_form_templates 3절대로 **값**이어야 함.

## korean_tax_calc_mcp/forms_workbook.py에 순수 함수 3개(이 모듈이 렌더러 전부를 가짐, server.py는 호출만)
- `tool_value(res, path) -> 값|None`: `"결과.키"`→`res["결과"][키]`, `"계산.키"`→`res["계산"][키]`(점으로 더 깊이 가능). 없으면 None.
- `resolve_formula(f, *, res, call_idx, local, cross) -> str`:
  - `[입력.이름]` → `호출{call_idx+1}_이름` — 단, `res["계산식_입력"]`에 그 이름이 있고 값이 무한대가 아닐 때만. `[입력.이름|d]`는 없으면 `d`. 기본값 없이 없으면 KeyError.
  - `[계산.경로]`·`[결과.경로]` → `tool_value` 값을 숫자 문자열로(정수는 정수, bool은 TRUE/FALSE). `|d` 기본값 규칙 같음. 없으면 KeyError.
  - `{id}` → `local[id]`, `{틀key!id}` → `'시트이름'!셀`(`cross[(틀key,id)] = (시트이름, 셀)`). 없으면 KeyError.
  - 그 밖 문자는 그대로.
- `fill_text(t, *, res, meta) -> str`: `{{키}}`→`meta[키]`, `{{입력.이름}}`→계산식_입력 값(정수면 정수). 없으면 빈 문자열.
- 렌더러의 slot 수식·table 열 수식·문구·검증 값은 모두 이 세 함수만 써서 처리. 지금 있는 임시 토큰 처리 코드·DEBUG 출력은 지운다.
