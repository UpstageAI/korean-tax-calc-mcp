# SPEC: export_workbook — calls를 JSON 문자열로 받아도 처리

## 문제
일부 모델(Solar Pro 4 등)은 목록 인자를 `"calls": "[{...}]"`처럼 JSON 문자열로 넘긴다. 지금은 MCP 입력 검증에서 `rejected arguments: ['calls']`로 거부되어 엑셀이 만들어지지 않는다. call 안의 `args`도 문자열로 오는 경우가 있다.

## 바꿀 것 (`korean_tax_calc_mcp/server.py`의 `export_workbook`만)
1. `calls` 타입을 `list | str`로. 문자열이면 `json.loads`로 풀고, 결과가 list가 아니거나 JSON이 아니면 `{"error": "입력 확인 필요 — calls는 [{label, tool, args}] 목록(JSON 배열)", ...}`를 돌려준다(예외 금지).
2. 각 call의 `args`가 문자열이면 `json.loads`로 풀어 dict로. dict가 아니거나 JSON이 아니면 그 call만 오류로 기록하고 나머지는 계속(기존 오류 call 처리와 같게).
3. 설명(docstring의 calls 줄)에 "JSON 문자열로 줘도 됨" 한 마디.

## 하지 말 것
다른 도구·렌더러·서식 틀 수정 금지, 테스트·명세 수정 금지.

## 통과 기준
`tests/test_calls_json_string.py` + 기존 테스트 전부.
