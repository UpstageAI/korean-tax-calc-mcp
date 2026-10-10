# Changelog

## 0.5.1 (2026-10-10)

- 도구 41개로 확대: `precheck_schema(tax=법인|부가|소득)` 추가 — 신고서 사전검토 입력키·의미·단위·필수 여부 목록 반환
- 40개 도구 description을 SPEC c5 형식으로 통일: `<한 줄 요약>. 언제: <상황>. 입력: <매핑>. 결과: <값+근거>` (한국어 우선, 영문 한 줄 맨 끝 유지)
- 인자 description 보강: 금액 인자에 정확한 세법 용어 명시(예: retirement_income_tax.income → "퇴직소득금액(퇴직급여, 비과세 제외, 원)"), 비율 인자는 소수/퍼센트 구분 명시, 연도 인자에 지원 범위(2016~2026) 명시
- 세무조사 판정 도구 11개 입력 스키마 구조화: 인자별 Field(description=...)와 JSON 예시 추가, Pydantic 모델(PersonEntry·FamilyLink·StakeEntry 등) 정의
- return_precheck description에서 내부 파일 경로 문구 삭제, "입력키는 precheck_schema로 먼저 확인" 안내로 교체
- 서버 instructions에 "계산 문제는 먼저 해당 계산 도구가 있는지 확인하고, 문제 자료를 도구 입력으로 옮겨 계산할 것. 도구 결과의 단계별 값을 그대로 인용할 것" 추가
- 테스트 추가: 모든 도구 description에 '언제:'·'입력:' 포함 검사, 모든 인자(description 존재, lang 제외) 검사, precheck_schema 3종 반환 검사, 세무조사 도구(list·dict 직접 전달) 하위 호환 검사
- 버전 0.5.1: `__init__.py`, `CHANGELOG.md`.

## 0.5.0 (2026-10-10)

- `vat_simplified_taxpayer` 확장: 마일리지·카드·현금영수증·미수취 매입·직전연도 공급대가·예정부과세액 인자 추가, 단계별 계산 표 반환(납부의무 면제 판정 포함)
- `vat_deemed_input_credit` 확장: 구입액·운반비·과세/면세 사용분·공통 기말재고·과세/면세 공급가액 인자 추가, 운반비율 제외 및 공통분 안분 계산
- 도구 8개(entertainment_limit, vat_common_input_allocation, vat_deemed_input_credit, vat_simplified_taxpayer, missing_receipt_disallowance, vat_card_sales_credit, nonbusiness_interest_disallowance, withholding_tax) description에 "이런 문제·상황에 쓴다" 한 줄과 주요 입력 매핑 추가
- README 국문·영문에 간이과세자 전 과정·의제매입세액 연장 설명 보강
- 버전 0.5.0: `__init__.py`, `pyproject.toml`, `server.json`.

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
