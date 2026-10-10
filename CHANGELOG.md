# Changelog

## 0.4.0 (2026-10-10)

- 세무조사 판정 도구 11개 통합: `related_judge`, `kinship_check`, `ownership_ratio`, `dominant_shareholder`, `tunnelling_gift`, `tunnelling_gift_nts`, `related_provision_at`, `extract_relations`, `tunnelling_from_pdf`, `return_precheck`, `return_precheck_pdf`
- 도구 총 40개(계산·판정 29 + 세무조사 판정 11). list_tools 40개 확인.
- 서버 instructions에 특수관계인 판정 기준일 필수·'확인 필요' 추측 금지 문구 추가.
- PDF 도구 3개(`extract_relations`, `tunnelling_from_pdf`, `return_precheck_pdf`) 결과에 AI 생성 표시 필드 추가(국문·영문). AI 기본법 제31조 대응.
- 면책·고지 섹션 신설(README 국문·영문): 면책, AI 사용 고지, 데이터 전송 안내.
- audit/agents/calc.py·calc_cit.py·calc_income.py·calc_vat.py는 계산기 engine/과 별도 사본으로 유지(사전검토 엔진 통합은 다음 버전).
- 버전 0.4.0: `__init__.py`, `pyproject.toml`, `server.json`.

## 0.3.1 (2026-09-??)

- 미성년자·청년 요건을 반영한 원천징수·연말정산 정밀 검증 규칙 보강.
- 비거주자 원천징수 쟁점 표시 개선(쟁점 데이터 issues.json 기반).
- 테스트 추가·정리.

## 0.3.0 (2026-08-??)

- Solar Pro 4(Solar Code CLI) 기반 개발 전환.
- 2026 법인세율, 비거주자 원천징수(`nonresident_withholding`), 과소자본(`thin_capitalization`) 추가.
- CodeSolar(Solar Pro 4 기반 코드 리뷰) PR 검토 도입.
