# SPEC_gold_gaps4c — 다른 브랜치 도구 등록 제거 · 작성 Claude 2026-10-24
브랜치 `feat/gold-gaps4`(이어서). 정답 테스트 `tests/test_gold_gaps4c.py` 1개 + 기존 전부 통과. 커밋 1개(제목: fix: gaps3 도구 등록이 섞여 들어온 것 제거). push 금지, 테스트 수정 금지.
- d6df18e 커밋의 server.py에 `personal_deduction`·`pension_income`·`income_loss_offset`·`disaster_loss_credit` 도구 등록(데코레이터·함수 전체)이 섞여 들어옴. 이 넷은 feat/gold-gaps3 PR 소관이고 이 브랜치엔 엔진 함수가 없어 호출하면 오류. server.py에서 그 네 도구 정의만 지운다(부가세 도구 2개·다른 코드는 그대로).
