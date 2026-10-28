"""세무조사 판정(audit)용 계산 함수 — engine/calc_cit.py를 그대로 씁니다.

예전에는 engine 사본을 따로 두어 연도별 규칙 수정(퇴직 근속연수공제 구표, 원천징수 '일용' 등)이 사전검토에 반영되지 않았음.
한 곳(engine)만 고치면 되도록 다시 내보내기만 한다 (Claude 2026-10-28)."""
from ...engine.calc_cit import *  # noqa: F401,F403
from ...engine import calc_cit as _engine

# import * 가 빠뜨리는 밑줄 이름 중 사전검토가 쓰는 것
_period = getattr(_engine, "_period", None)
_y = getattr(_engine, "_y", None)
_tier = getattr(_engine, "_tier", None)
