# Changelog

## 0.9.1 (2026-10-15)

- `tunnelling_gift_nts`: 엔진 호출 시 `dividends`(⑮ 배당공제)와 `excluded_by_corp`(⑩ 과세제외액)를 자리 순서로 바꿔 넘기던 버그 수정 — 배당공제를 주면 `TypeError`로 계산이 깨졌음. 키워드 인자로 전달. 데모 시나리오(중견기업 일감몰아주기, 2026 신고안내 산식) 작성 중 발견, Claude 수정, 기존 테스트 12건·전체 283건 통과
- `docs/demo.gif` 교체: 2025 사업연도 법인세 조정 통합 시나리오(원장 → 조정 7종 → 과세표준 → 산출세액·최저한세), 실제 도구 호출 결과로 렌더

## 0.9.0 (2026-10-14) — 호환 깨짐

- `entertainment_adjustment`·`simplified_vat_return`·`common_input_tax`: 옛 입력 파라미터 제거 — `expenses`·`revenue_general`·`revenue_related`(entertainment_adjustment), `supplies`·`purchases`(simplified_vat_return), `input_tax`(common_input_tax). 세 도구 모두 원장형 `ledger`만 받도록 통일(필수). 빈 원장(`[]`·공급 항목 없음)은 계산하지 않고 error 반환. entertainment_adjustment의 ledger 항목 `증빙`이 허용값('없음'|'영수증 등'|'적격') 밖이면 계산하지 않음(0.8.x의 '검토 필요' 처리 통일)
- `_guard` 공통: 같은 입력 재호출 시 결과 맨 앞에 `"안내": "같은 입력으로 {n}번째 계산입니다..."` 추가. 프로세스 내 키별 호출 횟수 추적(최근 500개). 테스트용 `_reset_call_memo()` 추가
- `tests/_legacy_to_ledger.py`: 변환기에서 common매입세액이 모두 0인 경우 ledger가 비지 않도록 0원 항목 유지(빈 원장 error 방지)

## 0.8.1 (2026-10-14)

- `entertainment_adjustment`: `revenue`(원장형 수입금액)를 `expenses`와 같이 주면 무시되던 버그 수정(한도가 기본한도만 적용됨). 회귀 테스트 추가

## 0.8.0 (2026-10-14)

- 세무조정 출력 통일: `bad_debt_adjustment`·`entertainment_adjustment`의 `결과` 첫 키를 `세무조정`(구분·금액·소득처분 목록)·`소득처분별_합계`·`손금불산입_합계`로 — 조정명세서에 적는 모양 그대로. 기존 키는 그 뒤에 유지
- 원장형 입력(기존 입력의 대안, 둘 다 주면 error): `entertainment_adjustment`에 `ledger`(항목·금액·증빙·성격·시가·장부가액)와 `revenue`(매출액·특수관계매출·매출할인등) — 교제목적 지출·직원단체(법인) 복리시설비 포함, 비법인 단체·임직원 부담분 제외, 현물은 시가·장부가액 중 큰 금액(법 제25조①, 영 제40조①②, 영 제42조①⑥); `simplified_vat_return`에 `ledger`(공급·매입 항목명과 금액, 어휘 키워드로 역할 판정 — 현금영수증·직불카드도 발급세액공제 대상); `common_input_tax`에 `ledger`(사용처 과세·면세·공통·실지귀속·불공제, 실지귀속은 과세비율·횟수·면적)와 `prior_common_input_tax`
- 계산기 연결: `input_tax_recalculation`에 `bundle`(토지·건물 일괄공급 입력) — 안분해서 건물 매입세액을 구한 뒤 재계산, `결과.건물_매입세액`
- 사실관계 어휘 3항목 추가(39개): `기업업무추진비_포함항목`·`간이과세자_원장항목`·`공통매입세액_귀속` (법제처 2026-01-01 시행본 확인)
- 정답 테스트 274개(공개 검증 사례 17건). Solar Pro 4(Solar Work CLI) 작성, 실행 시간 초과로 남은 문법·결과 조립 오류는 Claude가 수정, CodeSolar·Claude 검수

## 0.7.0 (2026-10-14)

- 끝에서 끝까지 계산기 6종 추가(도구 50개): `deemed_dividend_bonus_shares`(잉여금 자본전입 의제배당, 자기주식 교부/미교부), `other_income_aggregate`(기타소득 과세 구분·비과세·필요경비·원천징수·종합소득 합산), `simplified_vat_return`(간이과세자 확정신고 차가감납부세액), `common_input_tax`(겸영사업자 공통매입세액 안분·정산·공통사용재화 공급), `input_tax_recalculation`(감가상각자산 재계산), `bundled_supply_split`(토지·건물 일괄공급 안분)
- 사실관계 어휘 항목 36개(기타소득 7·간이과세 5·공통매입 4 추가), 모든 기준값은 어휘에서만 읽음(코드 상수·기본값 제거)
- `financial_income_aggregate`: 과세 제외 재원(주식발행초과금 등) 무상주는 `self_stock_shift`(자기주식 미배정 지분율 상승분, 0 가능)를 명시 입력해야 계산
- `deemed_dividend_bonus_shares`: 주주별 의제배당을 결과 맨 앞과 `주주별_의제배당` 요약으로
- 입력 가드: 몰수액·계약금 대체액이 총액 초과 시 거부, 실제 경비는 총수입 한도(소득세법 제37조②), 간이과세 납부의무 면제 시에도 미수취 가산세는 별도 적용(제69조②)
- 정답 테스트 261개(공개 검증 사례 12건). Solar Pro 4(Solar Work CLI) 작성, CodeSolar·Claude 검수

## 0.6.0 (2026-10-13)

- 끝에서 끝까지 계산기 3종: `bad_debt_adjustment`, `entertainment_adjustment`, `financial_income_aggregate` — 원래 사실관계를 받아 항목 판단→세법상 금액 조정→중간 계산→그 항목의 세무조정(소득처분)까지. 모르는 항목·빠진 사실은 계산하지 않고 허용값 반환
- 사실관계 어휘 `data/facts_vocab.json`(20항목): 허용값·기간별 기준(부터/까지)·별칭(접대비≤2023)을 파일에서 읽음 — 도구 44개

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
