# Changelog

## 0.12.2 (2026-10-26)

- `export_workbook`: 정의 이름을 엑셀 규칙에 맞춤 — 공백·괄호가 든 이름(예 `호출1_시부인 대상`) 때문에 Microsoft Excel이 파일을 열 때 복구 창을 띄우던 문제. 허용 문자(한글·영문·숫자·`_`·`.`) 밖은 `_`로 바꾸고, 셀 주소처럼 읽히는 이름·중복을 피함. forms 레이아웃에서 같은 이름을 두 번 등록하던 부분 정리. 시트 글자·계산 값은 그대로
- Solar Pro 4 작성, CodeSolar·Claude 검수

## 0.12.1 (2026-10-25)

- `export_workbook`: `calls`와 각 call의 `args`를 JSON 문자열로 줘도 처리(일부 모델이 목록·객체 인자를 문자열로 넘겨 입력 검증에서 거부되던 문제). 잘못된 `calls`는 오류 안내, 잘못된 `args`는 그 call만 오류로 기록하고 나머지 계속
- Solar Pro 4 작성, CodeSolar·Claude 검수

## 0.12.0 (2026-10-25)

- 계산 근거 엑셀 `export_workbook`(새 도구): 여러 도구 호출을 서버가 다시 실행해 엑셀로 냄. 기본 `layout: forms`는 법정서식 모양 그대로 — 서식 틀 12개(법인세 별지 제3호·제15호·제23호(갑)(을)·제20호(1)·제16호의2·제50호(을), 부가세 별지 제22호·공통사용재화·일괄양도 계산 근거, 종합소득세 배당·이자·근로소득 명세서), 금액 칸은 서식 산식 그대로의 수식, 서식 사이 연결(별지23·20·16의2 → 별지15 → 별지3), 도구 값 대조 칸(인쇄 영역 밖), A4 한 쪽 인쇄, 자료 없는 서식은 목록에 표시. `layout: steps`는 요약·계산 N 시트(입력 셀을 참조하는 살아 있는 수식). `company`·`period`·`biz_no` 인자
- 새 계산 도구 13개: `corporate_deemed_rent_income`(임대보증금 간주익금), `estimated_business_income`(추계 사업소득), `vat_exempt_use_deemed_supply`(면세전용 간주공급), `liquidation_income`(청산소득), `income_adjustment_total`(차가감소득금액·세무조정 집계), `personal_deduction`(인적공제), `pension_income`(연금소득금액), `income_loss_offset`(결손금 공제), `disaster_loss_credit`(재해손실세액공제), `vat_input_tax_deduction`(매입세액 공제 판정), `vat_deemed_supply_items`(간주공급 판정), `pension_account_withdrawal`(연금계좌 인출), `inheritance_gift_valuation`(상속·증여재산 평가)
- 기존 도구 확장: `entertainment_adjustment` 전통시장 등 추가한도(조특법 제136조⑥, 부칙대로 2023·2024 사업연도 10%·2025 20%+지역사랑상품권·2026 온누리상품권 추가), `other_income_aggregate` 승마투표권 환급금·슬롯머신 당첨금, `financial_income_aggregate` 손해배상 법정이자·공익신탁 이익, `capital_gains_income` 부담부증여 양도분, `deemed_dividend_bonus_shares` 자본전입 재원 3개
- 주요 계산 도구 8개(기업업무추진비·차가감소득금액·감가상각·수입배당금·공통매입세액·일괄공급 안분·총급여·금융소득)가 계산식 단계(입력·식·값)를 돌려줌 → 엑셀 수식의 바탕
- Solar Pro 4 작성, CodeSolar·Claude 검수

## 0.11.0 (2026-10-22)

- 항목형 입력: `capital_gains_income`에 취득세·취득 중개수수료·보유 중 납부 재산세·거주 시작일/종료일 칸(취득가액 합산과 거주기간 계산을 도구가 함, 환산취득가액 경로의 취득가액 구성 표시), `vat_deemed_input_credit`에 품목별 `items`(수입품 관세의 과세가격·운임 포함액·용도 비율, 용도 표기 3가지 형태 허용·같은 품목 행 병합·한국어 오류 안내), `special_tax_credit` 교육비에 회사 학자금·비과세 장학금 칸(차감 규칙을 결과에 항상 표기)
- 입력 의미: `persons.relation` 허용값 검증과 동의어(자녀·아들·딸 → 직계비속 등), `income_ok` 설명, 의제매입 `purchase` 산정 규칙 설명
- 규칙 공백 수정: `common_input_tax` 과세기간 중 공급한 공통사용재화 매입세액을 직전 과세기간 비율로 안분 공제(영 제81조④)·건물 신축 겸용 예정 시 `신축건물`로 예정사용면적비율 우선, `dividend_received_deduction` 배당기준일 전 3개월 취득분 제외 시 지급이자 차감 적수도 제외·피출자법인별 음수 방지, `entertainment_adjustment` 현물 접대비 = max(시가, 장부가액) + 부가세(`부가세별도` 기본 true)·성격 `사적사용`(시부인 제외, 손금불산입·상여), `inheritance_tax` `spouse.legal_share` 소수 허용
- 2026 소규모 임대법인 세율표 현행화, README 정리
- Solar Pro 4 작성, CodeSolar·Claude 검수

## 0.10.0 (2026-10-18)

- 새 계산 도구 12개: `capital_gains_income`(토지·건물·주택 양도소득세 — 1세대1주택 비과세·고가주택 안분·장기보유특별공제·기본공제·과세표준), `depreciation_adjustment`(개별 자산 감가상각 시부인 — 상각범위액·회사계상액 비교, 상각부인·유보·추인·감면법인 의제상각·세무상 미상각잔액), `retirement_allowance_adjustment`(퇴직급여충당금·확정급여형 퇴직연금충당금 세무조정 — 한도·지급여부·부인액 추인·부담금 손금산입), `foreign_tax_credit`(외국납부세액공제 — 직접·간주·간접, 국가별 한도, 한도초과 이월, Gross-up), `deemed_dividend_capital_reduction`(감자·주식소각·퇴사·탈퇴·해산 의제배당 — 받은 금전·재산가액 − 소멸 주식 취득가액, 단기소각·평균단가), `earned_income_gross_pay`(근로소득 항목별 과세·비과세 판정 — 총급여액·근로소득공제·근로소득금액), `inheritance_tax`(거주자 피상속인 상속세 과세가액·상속공제·과세표준·산출세액·납부할세액), `gift_tax`(거주자 수증자 증여세 과세가액·증여재산공제·과세표준·산출세액·납부할세액), `dividend_received_deduction`(내국법인 수입배당금액 익금불산입 — 피투자법인별 익금불산입률·지급이자 차감·세무조정), `inventory_valuation_adjustment`(재고자산 평가 세무조정 — 세법상 평가방법 결정·평가차 유보), `special_tax_credit`(근로소득자 특별세액공제 — 보험료·의료비·교육비와 표준세액공제 비교), `asset_grant_reserve`(국고보조금·공사부담금·보험차익 일시상각충당금·압축기장충당금 세무조정)
- 입력 보강: 정의되지 않은 최상위 인자 거부를 모든 도구에 적용, 목록 금액 칸의 참/거짓·숫자 문자열 거부, 간주임대료 윤년(366일) 반영·rate 인자 추가, vat_deemed_input_credit 운반비 제외 방식 변경(구입액 기준 비율)·base와 taxable_supply가 모두 0이면 오류·used_taxable > 매입가액 거부, deemed_interest fiscal_start(사업연도 개시일) 인자·received_interest 인자 추가, entertainment_adjustment 문화접대비 성격 항목 집계 시 증빙='적격' 필터링, capital_gains_income acquisition_price=0 시 환산취득가액 사용(산정 기준시가 둘 다 필요), other_income_aggregate 산업재산권대여·일시적인적용역에 actual_cost·actual_expense 허용 필드 추가, vat_bad_debt_credit supply_receivable 인자로 공급 대가 채권 여부 판단(아니면 대손세액 0), vat_card_sales_credit individual·prior_year_supply 인자로 법인·직전연도 공급가액 10억 초과 시 공제 0, vat_deemed_rent 윤년 366일 반영·rate 인자 추가·적용_이자율 결과 포함
- 사실관계 어휘 추가
- Solar Pro 4 작성, CodeSolar·Claude 검수

## 0.9.2 (2026-10-16)

- `other_income_aggregate`: 일시적 인적용역·산업재산권 대여 필요경비율을 연도별로 — 2017년까지 80%, 2018년 70%(3.31까지 받은 금액은 80% 주의 표시), 2019년부터 60%(소득세법 시행령 제87조). 이전에는 2010~2018년을 모두 70%로 계산
- `bad_debt_adjustment` 등 사실관계 입력: 별칭으로 들어온 종류(예: 파산 → 회수불능)를 정식 이름으로 바꿔 계산 분기에 전달 — 이전에는 '검토 필요'로만 나옴. `회수불능` 별칭에 파산·강제집행·사업폐지·사망·실종·형의집행 추가
- CI: MCP Registry 등록을 PyPI 배포 성공 뒤 자동 실행, PyPI 새 버전이 보일 때까지 대기. `server.json` 설명 도구 수 50, `__version__` 0.9.0으로 남아 있던 것 맞춤
- 주석·테스트 사례 표기 정리
- Claude 작성, Claude 검수

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
