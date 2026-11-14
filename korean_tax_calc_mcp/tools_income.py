"""근로소득 총급여(earned_income_gross_pay) 본문 — server.py에서 분리. 도구 등록(스키마·docstring·_guard)은 server.py의 얇은 래퍼가 맡는다."""
from datetime import date
from .engine import calc_income as I
from . import vocab


# ───────── 0.2 추가: 근로소득 총급여 ─────────
# 근거 조문: 소득세법 제20조(근로소득)·제12조3호(비과세)·제47조(근로소득공제), 시행령 제11조·제12조·제17조·제17조의2~제17조의4·제38조·제49조
_EGP_KIND_필요사실 = {
    "급여":             ["amount"],
    "상여":             ["amount"],
    "잉여금처분상여":   ["amount", "resolution_date"],
    "인정상여":         ["amount"],
    "식사대":           ["amount", "months", "meal_provided"],
    "자가운전보조금":   ["amount", "months", "vehicle", "business_use", "actual_travel_reimbursed"],
    "출산·보육수당":    ["amount", "purpose"],
    "직무발명보상금":   ["amount", "retired"],
    "연장근로수당":     ["amount", "eligible_occupation"],
    "사택제공이익":     ["amount", "position"],
    "주택자금대여이익": ["amount", "sme"],
    "단체보험료":       ["amount"],
    "학자금":           ["amount", "beneficiary"],
    "실비변상여비":     ["amount", "actual_cost"],
    "사회보험료_본인부담분_회사대납": ["amount"],
    "사회보험료_사용자부담분":        ["amount"],
}

_EGP_월한도_종류 = {"식사대", "자가운전보조금", "출산·보육수당"}

# 부칙이 '지급받는(받는) 분부터'인 종류 → 지급일 규칙에서 가져올 키. 경계 연도는 지급일을 안 넣었을 때 안내할 귀속연도.
_EGP_지급일_종류 = {"식사대": ("월한도",), "출산·보육수당": ("월한도", "보육_자녀1명당"),
                 "연장근로수당": ("월정액급여한도", "직전연도총급여한도", "연한도")}
_EGP_지급일_경계 = {"식사대": (2022,), "출산·보육수당": (2023, 2025), "연장근로수당": (2025,)}


_EGP_근무월수_종류 = ("식사대", "자가운전보조금", "출산·보육수당")


def _egp_월정액급여_산정(year: int, items: list, 판정: dict, 제외_idx: dict, 본인_idx: int) -> dict:
    """영 제17조① 후단의 월정액급여를 같은 호출의 다른 항목으로 산정한다.
    월정액급여 = 매월 직급별로 받는 봉급·급료·보수·임금·수당, 그 밖에 이와 유사한 성질의 급여
      (상여 등 부정기적인 급여, 영 제12조 실비변상적 급여, [2021~] 영 제17조의4 복리후생적 급여 제외)의 총액
      − 「근로기준법」 연장·야간·휴일근로 급여(·「선원법」 생산수당).
    판정: {원래 index: 항목별 dict(과세액·비과세액·비과세_성격)}, 제외_idx: {원래 index: 제외 사유}.
    반환: {"월정액급여", "근무월수", "포함", "제외", "산식"} 또는 {"error", ...}."""
    복리후생_제외 = year >= 2021   # 영 제17조① 개정 2021.2.17 — 제17조의4 복리후생적 급여 제외 문구 추가
    포함: list[dict] = []
    포함_i: list[int] = []      # 포함 항목의 원래 index(계산식에서 항목 입력을 가리킬 때)
    제외: list[dict] = []

    def _포함(i, d):
        포함.append(d)
        포함_i.append(i)
    모호: list[str] = []
    필요: dict[str, list[str]] = {}

    def _모호(k, 문구, 키="regular_monthly"):
        모호.append(f"{k}: {문구}")
        필요.setdefault(k, [])
        if 키 not in 필요[k]:
            필요[k].append(키)

    # 근무월수 — 연장근로수당 facts.months, 없으면 월 한도 항목의 months(모두 같을 때), 둘 다 없으면 12
    본인_facts = (items[본인_idx].get("facts") or {})
    if 본인_facts.get("months") not in (None, ""):
        근무월수 = int(본인_facts["months"]); 월수_출처 = "연장근로수당 facts.months"
    else:
        월수들 = {int((it.get("facts") or {})["months"]) for it in items
                  if it.get("kind") in _EGP_근무월수_종류 and (it.get("facts") or {}).get("months") not in (None, "")}
        if len(월수들) > 1:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"연장근로수당: 월정액급여 산정용 근무월수가 항목마다 다름 {sorted(월수들)} — "
                             "연장근로수당 facts.months(근무월수)를 넣거나 monthly_regular_wage를 직접 입력"],
                    "필요 입력": {"연장근로수당": ["months", "monthly_regular_wage"]}}
        if 월수들:
            근무월수 = 월수들.pop(); 월수_출처 = "식사대·자가운전보조금 등 facts.months"
        else:
            근무월수 = 12; 월수_출처 = "근무월수 입력 없음 — 12개월로 봄"
    if 근무월수 <= 0:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["연장근로수당: 근무월수(months)가 0 이하"],
                "필요 입력": {"연장근로수당": ["months"]}}

    if not any(it.get("kind") == "급여" and i not in 제외_idx for i, it in enumerate(items)):
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["연장근로수당: monthly_regular_wage가 없고, 월정액급여를 산정할 해당 연도 급여(봉급·임금) 항목도 없음"],
                "필요 입력": {"연장근로수당": ["monthly_regular_wage"], "급여": ["amount"]}}

    for i, it in enumerate(items):
        k = it.get("kind", "")
        amount = int(it.get("amount", 0) or 0)
        facts = it.get("facts") or {}
        정기 = facts.get("regular_monthly")   # 매월 정기 지급 여부(선택)
        if i in 제외_idx:
            제외.append({"kind": k, "금액": amount, "사유": f"{year}년 근로소득 아님 — {제외_idx[i]}"})
            continue
        p = 판정.get(i) or {"과세액": amount, "비과세액": 0}   # 연장근로수당(아직 판정 전)은 금액 그대로
        과세, 비과세 = p["과세액"], p["비과세액"]
        if k == "연장근로수당":
            제외.append({"kind": k, "금액": amount, "사유": "「근로기준법」 연장·야간·휴일근로로 통상임금에 더하여 받는 급여 — 총액에서 뺌(영 제17조① 후단)"})
        elif k in ("상여", "잉여금처분상여", "인정상여"):
            제외.append({"kind": k, "금액": amount, "사유": "상여 등 부정기적인 급여 — 제외(영 제17조① 후단 괄호)"})
        elif k == "사회보험료_사용자부담분":
            제외.append({"kind": k, "금액": amount, "사유": "사용자 부담분 — 근로자가 받는 급여 아님(법 제12조3호너목)"})
        elif k in ("급여", "식사대", "사회보험료_본인부담분_회사대납") or (k == "출산·보육수당" and facts.get("purpose") == "보육"):
            if 정기 is False:
                제외.append({"kind": k, "금액": amount, "사유": "매월 정기 지급 아님(regular_monthly=false) — 부정기적인 급여로 제외"})
            else:
                사유 = {"급여": "매월 받는 봉급·급료·임금 — 포함",
                        "식사대": "매월 받는 수당 — 포함(비과세 식사대도 영 제17조의2 근거로 제12조 실비변상·제17조의4 복리후생 제외 대상 아님)",
                        "사회보험료_본인부담분_회사대납": "근로자 부담분 회사 대납 — 매월 급여와 유사한 성질의 급여로 포함",
                        "출산·보육수당": "매월 받는 보육수당 — 포함(비과세 근거 법 제12조3호머목, 제외 대상 아님)"}[k]
                _포함(i, {"kind": k, "금액": amount, "사유": 사유})
        elif k == "자가운전보조금":
            if 비과세 > 0:
                제외.append({"kind": k, "금액": 비과세, "사유": "비과세 자가운전보조금 — 영 제12조 실비변상적 급여로 제외"})
            if 과세 > 0:
                if 정기 is False:
                    제외.append({"kind": k, "금액": 과세, "사유": "과세분 — 매월 정기 지급 아님(regular_monthly=false)"})
                else:
                    _포함(i, {"kind": k, "금액": 과세, "사유": "비과세 한도 초과 과세분 — 영 제12조 실비변상적 급여 아님, 매월 받는 수당으로 포함"})
        elif k == "실비변상여비":
            if 비과세 > 0:
                제외.append({"kind": k, "금액": 비과세, "사유": "실비변상 여비 — 영 제12조 실비변상적 급여로 제외"})
            if 과세 > 0:
                if 정기 is None:
                    _모호(k, "실비 정산이 아닌 여비(과세분) — 매월 정기 지급 수당인지(regular_monthly) 입력 필요")
                elif 정기:
                    _포함(i, {"kind": k, "금액": 과세, "사유": "실비 정산 아닌 정액 여비, 매월 정기 지급 — 포함"})
                else:
                    제외.append({"kind": k, "금액": 과세, "사유": "부정기 지급 — 제외"})
        elif k in ("사택제공이익", "주택자금대여이익", "단체보험료"):
            나머지 = amount
            if 비과세 > 0 and 복리후생_제외:
                제외.append({"kind": k, "금액": 비과세, "사유": "영 제17조의4 복리후생적 급여 — 제외(영 제17조① 후단, 2021.2.17 개정분)"})
                나머지 -= 비과세
            if p.get("비과세_성격") == "근로소득 아님":
                제외.append({"kind": k, "금액": 나머지, "사유": "근로소득 아님(영 제38조① 단서) — 급여 총액에 넣지 않음"})
                나머지 = 0
            if 나머지 > 0:
                if 정기 is None:
                    근거문 = "" if 복리후생_제외 else f"({year}년 영 제17조①에는 복리후생적 급여 제외 문구 없음 — 2021.2.17 개정으로 추가) "
                    _모호(k, f"{나머지:,}원 {근거문}— 매월 정기적으로 받는 급여인지(regular_monthly) 입력 필요")
                elif 정기:
                    _포함(i, {"kind": k, "금액": 나머지, "사유": "매월 정기적으로 받는 급여 — 포함"})
                else:
                    제외.append({"kind": k, "금액": 나머지, "사유": "부정기 — 제외"})
        else:
            # 직무발명보상금·학자금·출산 급여 등 — 지급 형태가 항목 이름만으로 정해지지 않음
            if 정기 is None:
                _모호(k, "매월 정기 지급(월정액급여 포함)인지 부정기 지급(제외)인지 알 수 없음 — regular_monthly(true/false) 입력 필요")
            elif 정기:
                _포함(i, {"kind": k, "금액": amount, "사유": "매월 정기 지급 — 포함"})
            else:
                제외.append({"kind": k, "금액": amount, "사유": "부정기적인 급여 — 제외(영 제17조① 후단 괄호)"})

    if 모호:
        필요.setdefault("연장근로수당", []).append("monthly_regular_wage")
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"연장근로수당: monthly_regular_wage가 없어 월정액급여를 항목으로 산정하려 했으나 판단할 수 없는 항목이 있음 — {m}"
                         for m in 모호],
                "필요 입력": 필요}

    포함합 = sum(x["금액"] for x in 포함)
    월정액 = 포함합 // 근무월수
    산식 = (f"월정액급여 = (" + " + ".join(f"{x['kind']} {x['금액']:,}" for x in 포함) +
            f") ÷ {근무월수}개월 = {포함합:,} ÷ {근무월수} = {월정액:,}원 ({월수_출처})")
    return {"월정액급여": 월정액, "포함_합계": 포함합, "근무월수": 근무월수, "포함": 포함, "제외": 제외, "산식": 산식,
            "포함_i": 포함_i, "월수_출처": 월수_출처}


def earned_income_gross_pay_impl(year, items) -> dict:
    """server.earned_income_gross_pay의 본문(서명·설명은 그쪽 참조)."""
    from .server import _ok, _validate_items, _specs_from_vocab   # 순환 import 회피 — 호출 시점에 가져옴

    # ── 1. vocab 기반 허용값 검증 ──
    _v = _validate_items(items, "kind", _specs_from_vocab("earned_income_gross_pay", "kind"))
    if _v: return _v

    # ── 2. 전적 월한도 항목 중복 체크 ──
    월한도_건수: dict[str, int] = {}
    for it in items:
        k = it.get("kind", "")
        if k in _EGP_월한도_종류:
            월한도_건수[k] = 월한도_건수.get(k, 0) + 1
    for k, cnt in 월한도_건수.items():
        if cnt > 1:
            # 지급일이 다른 해에 걸쳐 한도가 달라지면(부칙 '지급받는 분부터') 지급일별로 나눠 넣을 수 있음 — 모든 항목에 facts.paid_date, (지급일, 자녀) 서로 다름
            _같은 = [it for it in items if it.get("kind") == k]
            _키 = [((it.get("facts") or {}).get("paid_date"), (it.get("facts") or {}).get("child")) for it in _같은]
            if all(pd not in (None, "") for pd, _c in _키) and len(set(_키)) == len(_키):
                continue
        if cnt > 1 and k == "출산·보육수당" and vocab.rule(k, year).get("보육_자녀1명당"):
            # 2026~ 보육수당은 자녀 1명당 월 20만원(제12조3호머목2) — 자녀별 항목(facts.child 서로 다름)이면 허용
            _보육 = [it for it in items if it.get("kind") == k]
            _자녀 = [(it.get("facts") or {}).get("child") for it in _보육]
            if all((it.get("facts") or {}).get("purpose") == "보육" for it in _보육) \
                    and all(c not in (None, "") for c in _자녀) and len(set(_자녀)) == len(_자녀):
                continue
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"같은 kind '{k}'가 {cnt}번 입력됨 — {year}년 보육수당은 자녀 1명당 월 한도이므로 "
                             "자녀별로 나눌 때는 모든 항목을 purpose='보육'으로 하고 facts.child(자녀 이름)를 서로 다르게 넣거나, "
                             "한 항목에 child_ages(과세기간 개시일 기준 자녀 나이 목록)를 넣으세요"],
                    "필요 입력": {k: ["amount", "months", "purpose", "child", "child_age"]}}
        if cnt > 1:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"같은 kind '{k}'가 {cnt}번 입력됨 — 월 한도는 한 항목으로 합쳐 입력하세요"],
                    "필요 입력": {k: ["amount", "months", "meal_provided" if k == "식사대" else
                                       "vehicle" if k == "자가운전보조금" else "purpose"]}}

    # ── 3. 필요 사실 누락 체크 ──
    # facts 자체가 없는 항목({kind, amount}만 있는 경우)은 허용:
    #   · 급여·상여·인정상여: service_year가 없어도 귀속연도=year로 계산
    #   · 단체보험료·사회보험료_본인부담분_회사대납·사회보험료_사용자부담분: facts 불필요
    #   · 그 외 kinds는 필요한 facts가 빠지면 필요 입력 error
    누락: dict[str, list[str]] = {}
    for it in items:
        k = it.get("kind", "")
        사실과있음 = bool(it.get("facts"))   # facts 키 자체가 없거나 빈 dict면 False
        facts = it.get("facts", {}) or {}
        필요 = _EGP_KIND_필요사실.get(k, ["amount"])
        빠진 = []
        for f in 필요:
            if f == "amount":
                if it.get("amount") in (None, ""):
                    빠진.append("amount")
            elif 사실과있음 and (f not in facts or facts.get(f) in (None, "", [])):
                빠진.append(f)
        if 빠진:
            누락[k] = 빠진
    if 누락:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"항목 kind='{k}': 필요 사실 {빠진} 누락" for k, 빠진 in 누락.items()],
                "필요 입력": 누락}

    # ── 4. 항목별 판정 ──
    항목별: list[dict] = []
    월정액_식: dict | None = None   # 연장근로수당 비과세 판정에 월정액급여를 산정했으면 계산식용 정보
    제외_항목: list[dict] = []
    총급여액 = 0
    비과세_합계 = 0
    근로소득_아님_합계 = 0
    직무발명보상금_비과세_사용액 = 0
    산식_목록: list[str] = []
    근거_목록: list[list[str]] = []
    판단_목록: list[dict] = []
    지급일_주의: list[str] = []
    # 연장근로수당은 월정액급여를 다른 항목 판정 결과로 산정할 수 있게 맨 뒤에 판정(출력 순서는 입력 순서 유지)
    처리순서 = [i for i, it in enumerate(items) if it.get("kind") != "연장근로수당"] + \
              [i for i, it in enumerate(items) if it.get("kind") == "연장근로수당"]
    판정_idx: dict[int, dict] = {}     # 원래 index → 항목별 dict
    제외_idx: dict[int, str] = {}      # 원래 index → 제외 사유

    for _idx in 처리순서:
        it = items[_idx]
        k = it["kind"]
        amount = int(it.get("amount", 0))
        facts = it.get("facts", {}) or {}
        r = vocab.rule(k, year)
        b = vocab.basis(k, year)
        # 지급일 기준 부칙(식사대: 법률 제18975호, 출산·보육: 법률 제19933호·제21221호, 연장근로: 영 제36129호 부칙 제3조) — facts.paid_date
        if k in _EGP_지급일_종류:
            _pd = facts.get("paid_date")
            if _pd not in (None, ""):
                try:
                    _pdd = date.fromisoformat(str(_pd)[:10])
                except ValueError:
                    return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"{k}: facts.paid_date={_pd!r} — 지급일 YYYY-MM-DD"],
                            "필요 입력": {k: ["paid_date"]}}
                rp, used = vocab.rule_paid(k, year, _pdd)
                if used and not (k == "출산·보육수당" and facts.get("purpose") != "보육"):
                    r = {**r, **{kk: rp.get(kk) for kk in _EGP_지급일_종류[k]}}
                    b = vocab.basis(k, _pdd.year)
                    지급일_주의.append(f"{k} {amount:,}원: 귀속연도 {year}년이지만 지급일 {_pdd} — 부칙이 지급받는 분 기준이라 {_pdd.year}년 한도 적용"
                                    "(원천징수시기 특례 소득세법 제135조 아래 실제 지급일로 볼지는 국세청 해석 확인 필요)")
                elif _pdd.year != year and k == "출산·보육수당" and facts.get("purpose") != "보육" and vocab.rule_paid(k, year, _pdd)[1]:
                    지급일_주의.append(f"{k}(출산) {amount:,}원: 지급일 {_pdd} — 출산 급여 비과세는 지급일·신고 시기별 부칙이 달라 귀속연도 {year}년 규정으로만 계산함, 확인 필요")
            elif year in _EGP_지급일_경계.get(k, ()) and not (k == "출산·보육수당" and facts.get("purpose") != "보육") \
                    and not (k == "연장근로수당" and not facts.get("eligible_occupation")):
                지급일_주의.append(f"{k}: {year}년분 중 {year + 1}년에 지급한 금액(예: 12월분을 다음 해 1월 지급)이 있으면 facts.paid_date(지급일)로 항목을 나눠 넣으세요 — "
                                f"부칙이 지급받는 분 기준이라 그 금액은 {year + 1}년 한도 적용. 원천징수시기 특례(소득세법 제135조) 아래 실제 지급일로 볼지는 국세청 해석 확인 필요")
        구분 = r.get("구분", "과세")
        과세액 = amount
        비과세액 = 0
        비과세_성격 = ""
        사유 = ""

        # ── 귀속시기 확인 (제외 판정) ──
        if k in ("급여", "상여"):
            sy = facts.get("service_year")
            if sy is not None and int(sy) != year:
                제외_항목.append({"kind": k, "금액": amount, "사유": f"{int(sy)}년 귀속(근로 제공 연도) — {year}년 총급여에서 제외",
                                  "근거": b})
                제외_idx[_idx] = 제외_항목[-1]["사유"]; continue
        elif k == "잉여금처분상여":
            rd = facts.get("resolution_date")
            if rd:
                결의연도 = int(str(rd)[:4])
                if 결의연도 != year:
                    제외_항목.append({"kind": k, "금액": amount, "사유": f"{결의연도}년 귀속(잉여금처분결의일) — {year}년 총급여에서 제외",
                                      "근거": b})
                    제외_idx[_idx] = 제외_항목[-1]["사유"]; continue
        elif k == "인정상여":
            sy = facts.get("service_year")
            if sy is not None and int(sy) != year:
                제외_항목.append({"kind": k, "금액": amount, "사유": f"{int(sy)}년 귀속(근로 제공 사업연도) — {year}년 총급여에서 제외",
                                  "근거": b})
                제외_idx[_idx] = 제외_항목[-1]["사유"]; continue

        # ── 항목별 과세·비과세 판정 ──
        if k == "식사대":
            months = int(facts.get("months", 0))
            meal_provided = facts.get("meal_provided", False)
            월한도 = r["월한도"]
            if meal_provided:
                비과세액 = 0
                과세액 = amount
                사유 = "현물 식사 별도 제공 — 식사대 전액 과세(영 제17조의2 2호 단서)"
                비과세_성격 = "과세(현물 식사 제공)"
            else:
                비과세액 = min(amount, 월한도 * months)
                과세액 = amount - 비과세액
                사유 = f"월 {월한도:,}원 × {months}개월 = {월한도 * months:,}원 이내 비과세"
                비과세_성격 = "월한도비과세"
            if 비과세액 > 0:
                산식_목록.append(f"{k}: min({amount:,}, {월한도:,}×{months}) = {비과세액:,}원 비과세, 과세 {과세액:,}원")

        elif k == "자가운전보조금":
            months = int(facts.get("months", 0))
            vehicle = facts.get("vehicle", "기타")
            business_use = facts.get("business_use", False)
            actual_travel = facts.get("actual_travel_reimbursed", False)
            월한도 = r["월한도"]
            차량요건 = r.get("차량요건", [])
            비과세_대상 = (vehicle in 차량요건) and bool(business_use) and not actual_travel
            if 비과세_대상:
                비과세액 = min(amount, 월한도 * months)
                과세액 = amount - 비과세액
                사유 = f"본인 소유·임차 차량 업무 사용, 실제 여비 별도 수령 없음 — 월 {월한도:,}원 × {months}개월 이내 비과세(영 제12조 3호)"
                비과세_성격 = "월한도비과세"
            else:
                과세액 = amount
                비과세액 = 0
                if vehicle not in 차량요건:
                    사유 = f"차량 요건 미충족(차량: {vehicle}, 허용: {차량요건}) — 전액 과세"
                elif not business_use:
                    사유 = "업무 사용 아님 — 전액 과세"
                else:
                    사유 = "실제 여비 별도 수령 — 전액 과세"
                비과세_성격 = "과세(요건 미충족)"
            if 비과세액 > 0:
                산식_목록.append(f"{k}: min({amount:,}, {월한도:,}×{months}) = {비과세액:,}원 비과세, 과세 {과세액:,}원")

        elif k == "출산·보육수당":
            purpose = facts.get("purpose", "")
            months = int(facts.get("months", 0))
            child_age = facts.get("child_age")
            within_2y = facts.get("within_2y_of_birth", False)
            payment_count = facts.get("payment_count", 0)
            related_party = facts.get("related_party", False)
            월한도 = r["월한도"]
            출산전액 = r.get("출산전액비과세", False)

            if purpose == "보육":
                # 자녀 나이는 과세기간 개시일(1/1) 현재 만 나이 — "6세 이하"(제12조3호머목2)
                자녀1명당 = bool(r.get("보육_자녀1명당"))   # 2026~ 자녀 1명당 월 20만원, 2025년까지 근로자 1인당
                child_ages = facts.get("child_ages")
                if child_ages:
                    대상자녀수 = sum(1 for a in child_ages if int(a) <= 6)
                elif facts.get("child_count") is not None:
                    대상자녀수 = int(facts["child_count"])
                else:
                    대상자녀수 = 0 if (child_age is not None and int(child_age) > 6) else 1
                if 대상자녀수 == 0:
                    과세액 = amount; 비과세액 = 0
                    _나이 = child_ages if child_ages else f"{int(child_age)}세"
                    사유 = f"자녀 나이 {_나이}(과세기간 개시일 기준) — 6세 이하 아님, 전액 과세"
                    비과세_성격 = "과세(연령 초과)"
                else:
                    배수 = 대상자녀수 if 자녀1명당 else 1
                    월한도 = 월한도 * 배수
                    비과세액 = min(amount, 월한도 * months)
                    과세액 = amount - 비과세액
                    if 자녀1명당:
                        사유 = (f"6세 이하 자녀 {대상자녀수}명 보육 — 자녀 1명당 월 {r['월한도']:,}원 × {대상자녀수}명 × "
                                f"{months}개월 이내 비과세({year}년~ 제12조3호머목2)")
                    else:
                        사유 = f"6세 이하 자녀 보육 — 월 {월한도:,}원 × {months}개월 이내 비과세"
                        if 대상자녀수 > 1:
                            사유 += f"({year}년은 자녀 수와 관계없이 근로자 1인당 월 한도 — 자녀 1명당 한도는 2026년부터)"
                    비과세_성격 = "월한도비과세"
            elif purpose == "출산":
                # 2024년 지급분은 2021.1.1. 이후 출생 자녀면 '출생일 이후 2년 이내'가 아니어도 대상(제12조3호머목1) 괄호)
                _born = str(facts.get("child_born_on") or "")[:10]
                특례_2024 = year == 2024 and _born >= "2021-01-01"
                기간요건 = bool(within_2y) or 특례_2024
                if year >= 2024 and 출산전액 and 기간요건 and payment_count <= r.get("출산지급횟수한도", 2) and not related_party:
                    비과세액 = amount; 과세액 = 0
                    _기간 = ("출생 후 2년 이내" if within_2y else f"2021.1.1. 이후 출생 자녀({_born})에 대해 2024년에 지급받은")
                    사유 = (f"{_기간} {int(payment_count)}번째 출산 급여 — 전액 비과세"
                            "(특수관계자 제외, 법 제12조3호머목1)·영 제17조의2)")
                    비과세_성격 = "출산전액비과세"
                    if year == 2024:
                        지급일_주의.append("출산·보육수당(출산): 출산 급여 전액 비과세(제12조제3호머목1))는 법률 제20615호 부칙상 2025.1.1. 이후 확정신고·연말정산하는 분부터 — "
                                        "2024년 중 중도퇴사 연말정산에서 반영하지 못했으면 종합소득세 확정신고로 반영")
                elif year >= 2025:
                    # 2025.1.1. 이후 지급분: 머목은 1) 출산 급여 전액, 2) 6세 이하 자녀 보육 급여 월 한도뿐 — 요건을 못 갖춘 출산 급여에는 월 한도 없음
                    비과세액 = 0; 과세액 = amount
                    _미충족 = ("사용자와 특수관계" if related_party else
                              "출생일 이후 2년 이내가 아님" if not within_2y else
                              f"사용자별 {int(payment_count)}번째 지급(두 번째까지만)")
                    사유 = (f"출산 급여 전액 비과세 요건 미충족({_미충족}) — 전액 과세. {year}년 제12조3호머목은 1) 출산 급여 전액과 "
                            "2) 6세 이하 자녀 보육 급여 월 한도만 두므로, 보육과 관련해 받은 급여면 purpose='보육'으로 입력")
                    비과세_성격 = "과세(요건 미충족)"
                else:
                    비과세액 = min(amount, 월한도 * months)
                    과세액 = amount - 비과세액
                    사유 = (f"출산 급여 — 월 {월한도:,}원 × {months}개월 이내 비과세"
                            + ("(2024년 지급분 전액 비과세 요건 미충족 — 종전 머목 월 한도 적용. 2021.1.1. 이후 출생 자녀면 child_born_on 입력)"
                               if year == 2024 else "(2023년까지 출산·보육 월 한도)"))
                    비과세_성격 = "월한도비과세"
            else:
                비과세액 = min(amount, 월한도 * months)
                과세액 = amount - 비과세액
                사유 = f"출산·보육수당 — 월 {월한도:,}원 × {months}개월 이내 비과세"
                비과세_성격 = "월한도비과세"
            if 비과세액 > 0:
                산식_목록.append(f"{k}: min({amount:,}, {월한도:,}×{months}) = {비과세액:,}원 비과세, 과세 {과세액:,}원")

        elif k == "직무발명보상금":
            retired = facts.get("retired", False)
            related_party = facts.get("related_party", False)
            연한도 = r.get("연한도", 0)
            근로해당 = r.get("근로소득해당", True)
            특수관계제외 = r.get("특수관계제외", False)

            if year == 2016:
                제외_항목.append({"kind": k, "금액": amount, "사유": "기타소득(2016년까지는 근로소득 범위 밖 — 소득세법 제20조 2016 시행본에 직무발명보상금 없음)",
                                  "근거": b})
                제외_idx[_idx] = 제외_항목[-1]["사유"]; continue
            if retired:
                제외_항목.append({"kind": k, "금액": amount, "사유": "기타소득(퇴직 후 수령 — 발명진흥법 직무발명보상금, 소득세법 제21조 22호의2)",
                                  "근거": b})
                제외_idx[_idx] = 제외_항목[-1]["사유"]; continue
            if year >= 2024 and 특수관계제외 and related_party:
                과세액 = amount; 비과세액 = 0
                사유 = "2024년부터 사용자등과 특수관계자는 비과세 제외(영 제17조의3 ②)"
                비과세_성격 = "과세(특수관계)"
            else:
                비과세액 = min(amount, 연한도)
                과세액 = amount - 비과세액
                직무발명보상금_비과세_사용액 += 비과세액
                사유 = f"재직 중 직무발명보상금 — 연 {연한도:,}원 이내 비과세(영 제17조의3)"
                비과세_성격 = "연한도비과세"

        elif k == "연장근로수당":
            eligible = facts.get("eligible_occupation", False)
            mine_or_daily = facts.get("mine_or_daily", False)
            if eligible:
                mrw = facts.get("monthly_regular_wage")
                pYG = facts.get("prior_year_gross")
                if pYG is None:
                    # 직전 과세기간 총급여액은 이번 호출 항목으로 알 수 없음 — 항상 입력 필요
                    return {"error": "입력 확인 필요 — 계산하지 않음",
                            "문제": ["연장근로수당: eligible_occupation=True이나 직전연도 총급여(prior_year_gross) 누락"
                                     + ("" if mrw is not None else " — 월정액급여는 monthly_regular_wage가 없으면 같은 호출의 항목으로 산정")],
                            "필요 입력": {"연장근로수당": ["prior_year_gross"] + (
                                ["monthly_regular_wage"] if mrw is None and not any(x.get("kind") == "급여" for x in items) else [])}}
                월정액한도 = r["월정액급여한도"]
                총급여한도 = r["직전연도총급여한도"]
                월정액_초과 = None
                월정액_산정됨 = mrw is None
                if mrw is None:
                    # 영 제17조① 후단 정의대로 같은 호출의 다른 항목으로 월정액급여 산정
                    산정 = _egp_월정액급여_산정(year, items, 판정_idx, 제외_idx, _idx)
                    if "error" in 산정:
                        return 산정
                    mrw = 산정["월정액급여"]
                    월정액_초과 = 산정["포함_합계"] > 월정액한도 * 산정["근무월수"]   # 원 단위 절사 전 비교
                    월정액_식 = {"idx": _idx, "산정": 산정, "월정액한도": 월정액한도, "총급여한도": 총급여한도,
                               "직전": int(pYG), "광산일용": bool(mine_or_daily), "연한도": r.get("연한도", 0), "지급액": amount}
                    산식_목록.append(산정["산식"])
                    판단_목록.append({"항목": "월정액급여 산정(영 제17조① 후단)",
                                     "결론": f"월정액급여 {mrw:,}원 — {'한도 ' + format(월정액한도, ',') + '원 초과' if 월정액_초과 else '한도 ' + format(월정액한도, ',') + '원 이하'}",
                                     "포함": 산정["포함"], "제외": 산정["제외"], "산식": 산정["산식"],
                                     "근거": "소득세법 시행령 제17조① 후단(상여 등 부정기 급여·영 제12조 실비변상적 급여"
                                             + ("·영 제17조의4 복리후생적 급여" if year >= 2021 else "")
                                             + " 제외, 연장·야간·휴일근로 급여 차감)",
                                     "주의": "연간 금액을 근무월수로 나눈 평균 — 달마다 월정액급여가 달라 한도를 넘는 달이 있으면 monthly_regular_wage로 그 달 금액을 직접 입력"})
                if 월정액_초과 is None:
                    월정액_초과 = int(mrw) > 월정액한도
                if 월정액_초과 or int(pYG) > 총급여한도:
                    과세액 = amount; 비과세액 = 0
                    사유 = f"월정액급여 {int(mrw):,}원 > {월정액한도:,}원 또는 직전연도 총급여 {int(pYG):,}원 > {총급여한도:,}원 — 비과세 요건 미충족(영 제17조①)"
                    비과세_성격 = "과세(요건 미충족)"
                elif mine_or_daily:
                    비과세액 = amount; 과세액 = 0
                    사유 = "광산·일용근로자 — 연장근로수당 전액 비과세(영 제17조② 1호)"
                    비과세_성격 = "연한도비과세(전액)"
                else:
                    연한도 = r["연한도"]
                    비과세액 = min(amount, 연한도)
                    과세액 = amount - 비과세액
                    사유 = f"생산직 등 요건 충족 — 연 {연한도:,}원 이내 비과세(영 제17조② 1호)"
                    비과세_성격 = "연한도비과세"
                if 월정액_산정됨:
                    사유 += f" [월정액급여 {int(mrw):,}원은 같은 입력 항목으로 산정 — 판단 참고]"
            else:
                과세액 = amount; 비과세액 = 0
                사유 = "생산직 등 요건 미해당 — 전액 과세"
                비과세_성격 = "과세(비대상)"

        elif k == "사택제공이익":
            position = facts.get("position", "")
            비과세대상 = r.get("비과세대상", [])
            비과세성격_v = r.get("비과세성격", "비과세")
            if position in 비과세대상:
                if 비과세성격_v == "근로소득 아님":
                    # 2016~2020년: 사택제공이익은 비과세 금액이나 비과세_합계가 아닌 근로소득_아님_합계에 산입
                    과세액 = 0; 비과세액 = 0
                    사유 = f"비과세 대상({position}) — 사택 제공 이익 근로소득에서 제외(비과세 성격: 근로소득 아님, 영 제38조①6호 단서)"
                    비과세_성격 = 비과세성격_v
                else:
                    비과세액 = amount; 과세액 = 0
                    사유 = f"비과세 대상({position}) — 사택 제공 이익 비과세(영 제38조①6호, 영 제17조의4 1호)"
                    비과세_성격 = 비과세성격_v
            else:
                과세액 = amount; 비과세액 = 0
                사유 = f"비과세 대상 아님({position}) — 전액 과세"
                비과세_성격 = "과세(비대상)"

        elif k == "주택자금대여이익":
            sme = facts.get("sme", False)
            related_party = facts.get("related_party", False)
            중소기업제외 = r.get("중소기업제외", False)
            특수관계제외 = r.get("특수관계제외", False)
            비과세성격_v = r.get("비과세성격", "근로소득 아님")
            if not sme or not 중소기업제외:
                # sme=False: 중소기업 종업원 아님 → 전액 과세
                # 중소기업제외=False(2016~2019): 중소기업 종업원이라도 예외 없음 → 전액 과세
                과세액 = amount; 비과세액 = 0
                사유 = "중소기업 종업원 아님 또는 해당 연도 중소기업 예외 없음 — 주택자금 대여이익 전액 과세(영 제38조①7호)"
                비과세_성격 = "과세(비대상)"
            elif year >= 2024 and 특수관계제외 and related_party:
                # 영 제34265호 부칙 제4조①: 제17조의4제2호 단서는 이 영 시행(2024.2.29.) 이후 발생하는 소득부터 — 그 전 발생분은 종전대로 비과세
                기준일 = str(r.get("특수관계제외_발생기준일") or "")
                전_발생 = facts.get("accrued_before_20240229")
                if 기준일[:4] == str(year) and 전_발생 not in (None, ""):
                    전_발생 = min(int(전_발생), amount)
                    비과세액 = 전_발생; 과세액 = amount - 전_발생
                    사유 = (f"특수관계자(지배주주등·친족) — 2024.2.28.까지 발생분 {전_발생:,}원은 종전대로 비과세, 2024.2.29. 이후 발생분 {과세액:,}원은 과세"
                            "(영 제17조의4 2호 단서, 영 제34265호 부칙 제4조①: 시행 이후 발생 소득부터)")
                    비과세_성격 = "일부 비과세(특수관계 — 발생일 경계)"
                else:
                    과세액 = amount; 비과세액 = 0
                    사유 = "2024년부터 중소기업 종업원이라도 특수관계자(지배주주등·친족)는 비과세 제외 — 전액 과세(영 제17조의4 2호 단서, 부칙 2024.2.29)"
                    비과세_성격 = "과세(특수관계)"
                    if 기준일[:4] == str(year):
                        지급일_주의.append("주택자금대여이익: 특수관계자 비과세 제외는 2024.2.29. 이후 발생 소득부터(영 제34265호 부칙 제4조①) — "
                                        "2024.2.28.까지 발생한 대여이익이 있으면 facts.accrued_before_20240229(그 금액)를 넣어 비과세로 나눠 계산")
            else:
                if 비과세성격_v == "근로소득 아님":
                    # 2020년: 중소기업 종업원 주택자금 대여이익은 근로소득에서 제외(비과세 금액 아님)
                    과세액 = 0; 비과세액 = 0
                    사유 = "중소기업 종업원 주택자금 대여이익 — 근로소득에서 제외(비과세 성격: 근로소득 아님, 영 제38조①7호 단서)"
                    비과세_성격 = 비과세성격_v
                else:
                    비과세액 = amount; 과세액 = 0
                    사유 = "중소기업 종업원 주택자금 대여이익 — 비과세(영 제38조①7호 단서, 영 제17조의4 2호)"
                    비과세_성격 = 비과세성격_v

        elif k == "단체보험료":
            연한도 = r["연한도"]
            비과세액 = min(amount, 연한도)
            과세액 = amount - 비과세액
            사유 = f"단체순수보장성·환급부보장성 보험료 — 연 {연한도:,}원 이내 비과세(영 제38조①12호, 영 제17조의4 3호가목)"
            비과세_성격 = "연한도비과세"

        elif k == "학자금":
            beneficiary = facts.get("beneficiary", "")
            if beneficiary == "본인":
                req = facts.get("requirements_met", False)
                if req:
                    비과세액 = amount; 과세액 = 0
                    사유 = "근로자 본인 학자금 — 업무관련·지급기준·반납조건 3요건 충족, 비과세(영 제11조, 법 제12조3호아목)"
                    비과세_성격 = "요건비과세"
                else:
                    과세액 = amount; 비과세액 = 0
                    사유 = "근로자 본인 학자금이나 3요건(업무관련·지급기준·반납조건) 미충족 — 전액 과세"
                    비과세_성격 = "과세(요건 미충족)"
            else:
                과세액 = amount; 비과세액 = 0
                사유 = "가족(자녀 등) 학자금 — 전액 과세(영 제11조, 법 제12조3호아목)"
                비과세_성격 = "과세(가족 학자금)"

        elif k == "실비변상여비":
            actual_cost = facts.get("actual_cost")
            if actual_cost is None:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": ["실비변상여비: actual_cost(실비 정산 여부, true/false) 누락"],
                        "필요 입력": {"실비변상여비": ["actual_cost"]}}
            if not isinstance(actual_cost, bool):
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": ["실비변상여비: actual_cost는 실비 정산 여부(true/false)여야 함 — 숫자가 입력됨"],
                        "필요 입력": {"실비변상여비": ["actual_cost"]}}
            if actual_cost:
                비과세액 = amount; 과세액 = 0
                사유 = "실비변상 실제 비용 정산 지급 — 전액 비과세(영 제12조 3호, 법 제12조3호자목)"
                비과세_성격 = "요건비과세"
            else:
                과세액 = amount; 비과세액 = 0
                사유 = "실비변상 실제 비용 정산 미지급 — 전액 과세(영 제12조 3호, 법 제12조3호자목)"
                비과세_성격 = "과세"

        elif k == "사회보험료_본인부담분_회사대납":
            과세액 = amount; 비과세액 = 0
            사유 = "근로자 본인 부담 사회보험료 회사 대납 — 근로소득 과세(법 제20조①1호, 법 제12조3호너목 단서)"
            비과세_성격 = "과세"

        elif k == "사회보험료_사용자부담분":
            비과세액 = amount; 과세액 = 0
            사유 = "사용자 부담 사회보험료 — 근로소득 아님(법 제12조3호너목)"
            비과세_성격 = "비과세"

        else:
            # 기타 과세 항목 (급여, 상여, 잉여금처분상여, 인정상여)
            과세액 = amount; 비과세액 = 0
            사유 = "과세 근로소득"
            비과세_성격 = "과세"

        # 항목별 kind는 vocab 정식 이름(별칭이 입력됐어도 정식 이름으로 출력)
        정식_kind = vocab.resolve(k)["이름"]

        항목별.append({
            "kind": 정식_kind,
            "금액": amount,
            "과세액": 과세액,
            "비과세액": 비과세액,
            "비과세_성격": 비과세_성격,
            "근거": b,
            "사유": 사유,
        })
        판정_idx[_idx] = 항목별[-1]
        총급여액 += 과세액
        비과세_합계 += 비과세액

        # 근로소득 아님 항목 집계: vocab 판단.비과세성격이 "근로소득 아님"인 항목만
        # 사택제공이익(2016~2020)·주택자금대여이익(2020) 등. 사회보험료_사용자부담분은
        #   vocab 판단.비과세성격 필드가 없고 판단.구분="비과세" → 비과세_합계에만 포함.
        if r.get("비과세성격") == "근로소득 아님":
            근로소득_아님_합계 += amount

    # 출력 순서는 입력 순서대로(연장근로수당을 뒤에서 판정했어도)
    _순번 = {id(v): i for i, v in 판정_idx.items()}
    항목별.sort(key=lambda x: _순번.get(id(x), 0))

    # ── 5. 근로소득공제·근로소득금액 ──
    근로소득공제 = I.earned_deduction(총급여액, year)
    근로소득금액 = 총급여액 - 근로소득공제

    if 직무발명보상금_비과세_사용액 > 0:
        산식_목록.append(f"직무발명보상금 비과세 사용액: {직무발명보상금_비과세_사용액:,}원 (기타소득 비과세 한도 공유용, 영 제18조②)")
    산식_목록.append(f"총급여액 = Σ 과세액 = {총급여액:,}원")
    산식_목록.append(f"근로소득공제 = earned_deduction({총급여액:,}원, {year}) = {근로소득공제:,}원 (소득세법 제47조①)")
    산식_목록.append(f"근로소득금액 = 총급여액 {총급여액:,}원 − 근로소득공제 {근로소득공제:,}원 = {근로소득금액:,}원")

    근거_목록.extend(b for _, _, b in [(it["kind"], it["금액"], it["근거"]) for it in 항목별])

    # ── 계산식 단계 (SPEC_export_workbook_f) ──────────────────────────────
    # 항목별 과세액을 계산식_입력으로 추가
    계산식_입력 = []
    항목식_parts = []
    월정액_단계: list[dict] = []
    연장_entry = 판정_idx.get(월정액_식["idx"]) if 월정액_식 else None
    위치 = {id(item): idx for idx, item in enumerate(항목별, 1)}
    for idx, item in enumerate(항목별, 1):
        과세액 = item["과세액"]
        항목식_parts.append(f"항목{idx}")
        if item is not 연장_entry:
            계산식_입력.append({"이름": f"항목{idx}", "값": 과세액, "설명": f"{item['kind']} 과세액 = {과세액:,}원"})
            continue
        # 연장근로수당: 월정액급여(영 제17조① 후단)를 같은 입력 항목으로 산정 → 비과세 요건 → 과세액까지 식으로
        산정 = 월정액_식["산정"]
        refs = []
        for m, (j, x) in enumerate(zip(산정["포함_i"], 산정["포함"]), 1):
            e = 판정_idx.get(j)
            if e is not None and e is not 연장_entry and e["과세액"] == x["금액"]:
                refs.append(f"항목{위치[id(e)]}")
            else:
                계산식_입력.append({"이름": f"월정액_포함{m}", "값": x["금액"], "설명": f"월정액급여 포함 — {x['kind']}: {x['사유']}"})
                refs.append(f"월정액_포함{m}")
        계산식_입력 += [
            {"이름": "월정액_근무월수", "값": 산정["근무월수"], "설명": f"근무월수 ({산정['월수_출처']})"},
            {"이름": "월정액급여한도", "값": 월정액_식["월정액한도"], "설명": "생산직 등 연장근로수당 비과세 월정액급여 한도(영 제17조①)"},
            {"이름": "직전연도총급여", "값": 월정액_식["직전"], "설명": "직전 과세기간 총급여액(입력)"},
            {"이름": "직전연도총급여한도", "값": 월정액_식["총급여한도"], "설명": "직전 과세기간 총급여액 한도(영 제17조①)"},
            {"이름": "연장근로수당_지급액", "값": 월정액_식["지급액"], "설명": "연장·야간·휴일근로수당 지급액"},
            {"이름": "광산일용여부", "값": 월정액_식["광산일용"], "설명": "광산근로자·일용근로자면 TRUE — 전액 비과세(영 제17조②1호)"},
            {"이름": "연장근로_연한도", "값": 월정액_식["연한도"] or 0, "설명": "연 비과세 한도(영 제17조②1호)"},
        ]
        월정액_단계 += [
            {"이름": "월정액_포함합계", "식": "+".join(refs) if refs else "0*월정액_근무월수", "값": 산정["포함_합계"],
             "설명": "매월 받는 봉급·수당 합계(상여 등 부정기 급여·실비변상적 급여" + ("·복리후생적 급여" if year >= 2021 else "") + " 제외, 연장근로 급여 차감)"},
            {"이름": "월정액급여", "식": "ROUNDDOWN(월정액_포함합계/월정액_근무월수,0)", "값": 산정["월정액급여"], "설명": "포함 합계 ÷ 근무월수(영 제17조① 후단)"},
            {"이름": "연장근로_비과세", "식": "IF(월정액_포함합계>월정액급여한도*월정액_근무월수,0,IF(직전연도총급여>직전연도총급여한도,0,"
                                           "IF(광산일용여부,연장근로수당_지급액,MIN(연장근로수당_지급액,연장근로_연한도))))",
             "값": item["비과세액"], "설명": "월정액급여·직전연도 총급여 요건 충족 시 연 한도 안에서 비과세(영 제17조①②)"},
            {"이름": f"항목{idx}", "식": "연장근로수당_지급액-연장근로_비과세", "값": 과세액, "설명": f"{item['kind']} 과세액"},
        ]

    # 근로소득공제 구간표 (2016~2026 동일)
    # 500만 이하 70%, 1500만 이하 40%, 4500만 이하 15%, 1억 이하 5%, 초과 2%
    # 2020년부터 한도 2,000만
    한도적용 = year >= 2020

    if len(항목식_parts) > 0:
        총급여_식 = "+".join(항목식_parts)
    else:
        총급여_식 = "0"

    # 근로소득공제 식 (중첩 IF)
    공제_식 = (
        f"IF(총급여액<=5000000,총급여액*0.7,"
        f"IF(총급여액<=15000000,5000000*0.7+(총급여액-5000000)*0.4,"
        f"IF(총급여액<=45000000,5000000*0.7+10000000*0.4+(총급여액-15000000)*0.15,"
        f"IF(총급여액<=100000000,5000000*0.7+10000000*0.4+30000000*0.15+(총급여액-45000000)*0.05,"
        f"5000000*0.7+10000000*0.4+30000000*0.15+55000000*0.05+(총급여액-100000000)*0.02))))"
    )
    if 한도적용:
        공제_식 = f"MIN({공제_식},20000000)"

    계산식 = 월정액_단계 + [
        {"이름": "총급여액", "식": 총급여_식, "값": 총급여액,
         "설명": f"총급여액 = Σ 항목별 과세액 = {총급여액:,}원 (비과세 판정 후 금액 합계)"},
        {"이름": "근로소득공제", "식": 공제_식, "값": 근로소득공제,
         "설명": f"근로소득공제 = 구간별 공제율 적용 (500만↓70%, 1500만↓40%, 4500만↓15%, 1억↓5%, 초과2%) {'+ 한도 2,000만(2020~)' if 한도적용 else '(한도 없음)'} = {근로소득공제:,}원 (소득세법 제47조①)"},
        {"이름": "근로소득금액", "식": "총급여액-근로소득공제", "값": 근로소득금액,
         "설명": f"근로소득금액 = 총급여액 − 근로소득공제 = {총급여액:,} − {근로소득공제:,} = {근로소득금액:,}원"},
    ]

    return _ok({
        "총급여액": 총급여액,
        "비과세_합계": 비과세_합계,
        "근로소득_아님_합계": 근로소득_아님_합계,
        "근로소득공제": 근로소득공제,
        "근로소득금액": 근로소득금액,
        "직무발명보상금_비과세_사용액": 직무발명보상금_비과세_사용액,
    }, 근거_목록,
       항목별=항목별,
       제외_항목=제외_항목,
       산식=산식_목록,
       계산식_입력=계산식_입력,
       계산식=계산식,
       **({"판단": 판단_목록} if 판단_목록 else {}),
       **({"주의": 지급일_주의} if 지급일_주의 else {}))
