"""신고서 사전검토(모드 A) 규칙 엔진. 작성 Mia(윤승미)
조사 착수 전, 신고서·재무제표 값만으로 "오류 의심"을 뽑는다. 확정 판단은 조사 후.

규칙 작성 형식 (세목별 모듈 corp.py / vat.py / income.py):
    @rule("C-015", "법인", "기업업무추진비조정명세서", "한도초과액 재계산 불일치", "법인세법 제25조④",
          needs=["기업업무추진비.해당액", "수입금액.일반", ...], source="12 서식6-3")
    def _(d):
        ...                       # d: Data — d["키"] 로 값, 없으면 Missing 예외 → '자료 부족'으로 처리
        return hit(신고, 재계산, "설명")   # 오류 의심
        return ok()                        # 이상 없음
입력 키는 각 모듈의 SCHEMA = {키: 설명} 에 정의한 이름만 쓴다(서식.항목). 금액은 원 단위 int.
"""
from dataclasses import dataclass, field

REGISTRY = []


class Missing(Exception):
    pass


class Data(dict):
    """d["키"]: 없으면 Missing. d.get("키", 기본값)은 그대로."""
    def __getitem__(self, k):
        if k not in self or super().__getitem__(k) is None: raise Missing(k)
        return super().__getitem__(k)


@dataclass
class Rule:
    id: str
    세목: str
    서식: str
    제목: str
    근거: str
    needs: list = field(default_factory=list)
    source: str = ""
    kind: str = "수식"          # 수식 | 외부자료 | 사실판단(사실판단은 체크리스트로만 출력)
    fn: object = None


def rule(id, 세목, 서식, 제목, 근거, needs=(), source="", kind="수식"):
    def deco(fn):
        REGISTRY.append(Rule(id, 세목, 서식, 제목, 근거, list(needs), source, kind, fn)); return fn
    return deco


def _num(x): return isinstance(x, (int, float)) and not isinstance(x, bool)


def hit(reported=None, recomputed=None, note="", tol=None):
    """오류 의심. 둘 다 숫자면 차이가 tol 이하일 때 이상 없음으로 되돌린다.
    tol 기본값: 둘 다 정수(원 단위 금액)면 1원, 비율·실수면 1e-9(사실상 일치), bool·문자열은 같을 때만."""
    if tol is None: tol = 1 if isinstance(reported, int) and isinstance(recomputed, int) else 1e-9
    if _num(reported) and _num(recomputed) and abs(reported - recomputed) <= tol:
        return {"결과": "이상 없음"}
    if not _num(reported) and reported is not None and reported == recomputed:
        return {"결과": "이상 없음"}
    return {"결과": "오류 의심", "신고": reported, "재계산": recomputed,
            "차이": (recomputed - reported) if isinstance(reported, (int, float)) and isinstance(recomputed, (int, float)) else None, "내용": note}


def ok(note=""): return {"결과": "이상 없음", "내용": note}


def check(reported, recomputed, note="", tol=None):
    return hit(reported, recomputed, note, tol)


def run(data, 세목=None):
    from . import corp, vat, income  # noqa: F401 — 규칙 등록
    d = Data(data)
    out = {"오류 의심": [], "이상 없음": [], "자료 부족": [], "사실 확인 필요": []}
    for r in REGISTRY:
        if 세목 and r.세목 != 세목: continue
        head = {"규칙": r.id, "세목": r.세목, "서식": r.서식, "항목": r.제목, "근거": r.근거}
        if r.kind == "사실판단":
            out["사실 확인 필요"].append({**head, "확인": r.fn.__doc__ or r.제목}); continue
        try:
            res = r.fn(d)
        except Missing as e:
            allm = [k for k in r.needs if d.get(k) is None] or [str(e)]
            out["자료 부족"].append({**head, "필요": str(e), "필요전체": allm}); continue
        except ZeroDivisionError:
            out["자료 부족"].append({**head, "필요": "분모 0"}); continue
        out[res["결과"]].append({**head, **{k: v for k, v in res.items() if k != "결과"}})
    out["요약"] = {k: len(v) for k, v in out.items() if isinstance(v, list)}
    try:
        from . import needs, corp as _c, vat as _v, income as _i
        schema = {**_c.SCHEMA, **_v.SCHEMA, **_i.SCHEMA}
        out["자료 부족 안내"] = needs.guide(out["자료 부족"], {r.id: r for r in REGISTRY}, schema)
    except Exception as e:
        out["자료 부족 안내"] = [{"주제": "안내 생성 실패", "오류": str(e)[:200]}]
    return out
