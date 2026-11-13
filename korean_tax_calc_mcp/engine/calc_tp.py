"""정상가격 범위와 조정액 계산. Claude 작성(2026-11-12).

근거(2021.12.31.·2026.11.1. 시행본 대조): 국제조세조정에 관한 법률 시행령 제15조⑤ — 특수관계 없는 자 간 둘 이상의 거래로 정상가격 범위를 산정해
신고(법 제6조)·결정·경정(법 제7조) 여부 판정에 쓸 수 있다. ⑥ — 거래가격이 그 범위를 벗어나면 범위 거래의 평균값, 중위값, 최빈값, 그 밖의 합리적인
특정 가격을 기준으로 한다. 범위를 어떻게 좁히는지(전체 범위·사분위 범위)는 국조법령에 정해져 있지 않다 — 사분위 범위는 OECD 이전가격지침 3.57이
비교가능성 결함이 남을 때 쓰는 통계적 도구로 든다. 이 도구는 입력한 비교대상 값으로 범위·기준점·차이만 계산하고, 비교대상이 적절한지는 판단하지 않는다."""
from fractions import Fraction

BASIS = "국제조세조정에 관한 법률 시행령 제15조⑤⑥, 법 제6조·제7조"
YEAR_MIN, YEAR_MAX = 2021, 2026


def _fr(x):
    return Fraction(str(x))


def _quantile(xs, q, method):
    """xs 정렬됨. inclusive: 위치 (n−1)q(엑셀 QUARTILE.INC), exclusive: 위치 (n+1)q − 1(엑셀 QUARTILE.EXC, n≥3)."""
    n = len(xs)
    pos = (n - 1) * q if method == "inclusive" else (n + 1) * q - 1
    if pos <= 0: return xs[0]
    if pos >= n - 1: return xs[-1]
    lo = int(pos)
    return xs[lo] + (xs[lo + 1] - xs[lo]) * (pos - lo)


def arm_length_range(comparables, tested_value, base_amount=None, range_type="사분위", point="중위값", point_value=None,
                     tested_is_resident=None, higher_is_more_income=True, quartile_method="inclusive", year=None):
    문제 = []
    vals, names = [], []
    if not isinstance(comparables, list) or len(comparables) < 2:
        문제.append("comparables — 비교대상 값 둘 이상(시행령 제15조⑤: 둘 이상의 거래). 숫자 목록 또는 [{이름, 값}]")
    else:
        for i, c in enumerate(comparables):
            v = c.get("값") if isinstance(c, dict) else c
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                문제.append(f"comparables[{i}] — 숫자(이익률은 소수, 예: 0.035)"); continue
            vals.append(_fr(v)); names.append(c.get("이름", f"비교대상{i + 1}") if isinstance(c, dict) else f"비교대상{i + 1}")
    if not isinstance(tested_is_resident, bool):
        문제.append("tested_is_resident — 분석대상 당사자가 국내 법인(거주자)이면 True, 국외특수관계인(해외 자회사·모회사 등)이면 False. "
                  "어느 쪽이냐에 따라 조정 방향이 반대가 되므로 비워 두면 계산하지 않음(회사 이름으로 추측하지 않음)")
    if isinstance(tested_value, bool) or not isinstance(tested_value, (int, float)):
        문제.append("tested_value — 분석대상 당사자의 값(숫자)")
    if range_type not in ("사분위", "전체"):
        문제.append("range_type — '사분위' 또는 '전체'")
    if point not in ("중위값", "평균값", "직접입력"):
        문제.append("point — '중위값'·'평균값'·'직접입력'")
    if point == "직접입력" and (isinstance(point_value, bool) or not isinstance(point_value, (int, float))):
        문제.append("point_value — point='직접입력'이면 기준점 값(숫자) 필요")
    if quartile_method not in ("inclusive", "exclusive"):
        문제.append("quartile_method — 'inclusive'(엑셀 QUARTILE.INC) 또는 'exclusive'(QUARTILE.EXC)")
    if base_amount is not None and (isinstance(base_amount, bool) or not isinstance(base_amount, (int, float)) or base_amount < 0):
        문제.append("base_amount — 지표의 분모 금액(원, 0 이상): 매출액 대비 이익률이면 매출액, 원가 대비면 원가")
    if year is not None and not (isinstance(year, int) and YEAR_MIN <= year <= YEAR_MAX):
        문제.append(f"year={year!r} — {YEAR_MIN}~{YEAR_MAX}(시행령 제15조는 2021.1.1. 시행 전부개정 조문 — 그 전 사업연도는 구 시행령을 대조하지 않아 지원하지 않음)")
    if range_type == "사분위" and quartile_method == "exclusive" and len(vals) < 3:
        문제.append("quartile_method='exclusive'는 비교대상 셋 이상 필요")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    xs = sorted(vals)
    n = len(xs)
    median = _quantile(xs, Fraction(1, 2), "inclusive")
    mean = sum(xs) / n
    q1 = _quantile(xs, Fraction(1, 4), quartile_method)
    q3 = _quantile(xs, Fraction(3, 4), quartile_method)
    lo, hi = (q1, q3) if range_type == "사분위" else (xs[0], xs[-1])
    t = _fr(tested_value)
    inside = lo <= t <= hi
    ref = median if point == "중위값" else mean if point == "평균값" else _fr(point_value)
    판단 = [{"항목": "범위", "결론": (f"비교대상 {n}개의 " + ("사분위 범위(제1사분위~제3사분위)" if range_type == "사분위" else "전체 범위(최솟값~최댓값)")
                                + f" {float(lo):.4%} ~ {float(hi):.4%}"),
           "근거": "시행령 제15조⑤" + (" — 사분위로 좁히는 방법은 국조법령에 없고 OECD 지침 3.57의 통계적 도구" if range_type == "사분위" else "")}]
    결과 = {"비교대상_수": n, "최솟값": float(xs[0]), "제1사분위": float(q1), "중위값": float(median), "제3사분위": float(q3), "최댓값": float(xs[-1]),
           "평균값": float(mean), "범위": {"종류": range_type, "하한": float(lo), "상한": float(hi)}, "분석대상_값": float(t), "범위_안": inside}
    if inside:
        결과.update({"조정_필요": False, "차이": 0.0, "조정액": 0})
        판단.append({"항목": "판정", "결론": f"분석대상 값 {float(t):.4%}이 범위 안 — 조정하지 않음", "근거": "시행령 제15조⑤, OECD 지침 3.60"})
    else:
        if point == "직접입력" and not (lo <= ref <= hi):
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"point_value={float(ref)} — 기준점은 정상가격 범위({float(lo):.6f}~{float(hi):.6f}) 안의 값이어야 함(시행령 제15조⑥: 그 범위 거래의 값)"]}
        diff = ref - t
        below = t < lo
        # 소득 방향: 지표가 높을수록 그 당사자 소득이 큰 지표(이익률)인지, 분석대상이 거주자인지
        tested_income_low = below if higher_is_more_income else not below
        resident_income_low = tested_income_low if tested_is_resident else not tested_income_low
        결과.update({"조정_필요": True, "기준점": {"종류": point, "값": float(ref)}, "차이": float(diff),
                   "거주자_소득": "과소" if resident_income_low else "과다",
                   "방향": (f"분석대상({'국내' if tested_is_resident else '국외'} 법인) 값 {float(t):.4%}이 범위 " + ("하한 미만" if below else "상한 초과")
                          + " → 국내 법인 소득 " + ("과소 → 증액 조정 대상" if resident_income_low else "과다 → 정상가격 기준 신고·경정청구 검토"))})
        if base_amount is not None:
            amt = abs(diff) * _fr(base_amount)
            결과["조정액"] = int(amt)      # 원 미만 절사
        판단.append({"항목": "판정", "결론": (f"분석대상 값 {float(t):.4%}이 범위 " + ("하한 미만" if below else "상한 초과") + f" — 기준점({point}) {float(ref):.4%}까지 조정, 차이 {float(abs(diff)):.4%}p"),
                   "근거": "시행령 제15조⑥(범위 거래의 평균값, 중위값, 최빈값, 그 밖의 합리적인 특정 가격)"})
        판단.append({"항목": "조정 방향", "결론": ("거주자 소득이 정상가격보다 적음 — 과세당국의 증액 결정·경정 대상(법 제7조), 납세자는 정상가격 기준으로 신고할 수 있음(법 제6조)" if resident_income_low
                                          else "거주자 소득이 정상가격보다 많음 — 납세자가 정상가격 기준으로 신고하거나 경정청구할 수 있음(법 제6조). 상대국 과세와 맞물리면 대응조정·상호합의 검토"),
                   "근거": "국제조세조정에 관한 법률 제6조·제7조"})
    비교대상_확인 = [
        {"항목": "비교가능 거래의 뜻", "내용": "비교되는 상황 간의 차이가 가격이나 순이익에 중대한 영향을 주지 않거나, 주더라도 그 차이를 제거할 합리적 조정이 가능한 거래", "근거": "시행령 제14조①1호"},
        {"항목": "분석요소", "내용": "재화·용역의 종류와 특성, 사업활동의 기능, 거래에 수반되는 위험, 사용되는 자산, 계약 조건, 경제 여건(시장 규모·거래단계·경쟁 정도), 사업전략", "근거": "시행령 제14조②, 시행규칙 제6조①"},
        {"항목": "내부 비교가능 거래", "내용": "분석대상 당사자가 특수관계 없는 독립된 사업자와 한 거래를 외부 자료보다 먼저 수집·검토", "근거": "시행규칙 제7조①4호·5호"},
        {"항목": "제외할 수 있는 거래", "내용": "거래 당사자가 임의로 조작해 정상적인 거래로 볼 수 없는 거래는 비교가능한 거래로 선택하지 않을 수 있음", "근거": "시행령 제14조④"},
        {"항목": "이익률 자료의 한계", "내용": "공시 재무제표나 데이터베이스에서 얻은 이익률만으로는 기능·위험·거래 조건·규모가 비슷한지 확인할 수 없음 — 탐색 조건, 단계별 탈락 사유, 차이 조정을 문서로 남겨야 비교대상으로 설명할 수 있음", "근거": "시행규칙 제7조①7호·8호, 개별기업보고서 Ⅱ-12·Ⅱ-13"},
        {"항목": "과세당국의 재산정", "내용": "과세당국은 다른 비교대상이나 산출방법으로 정상가격을 다시 산정할 수 있음 — 한 출처에 기대지 말고 내부 거래·공시 자료·데이터베이스 등 여러 출처로 맞춰 봄", "근거": "국제조세조정에 관한 법률 제7조①"}]
    out = {"결과": 결과, "비교대상_확인": 비교대상_확인, "계산": {"비교대상_정렬": [{"이름": nm, "값": float(v)} for v, nm in sorted(zip(vals, names))],
                             "사분위_계산법": ("위치 (n−1)×q 선형보간(엑셀 QUARTILE.INC)" if quartile_method == "inclusive" else "위치 (n+1)×q−1 선형보간(엑셀 QUARTILE.EXC)")},
           "판단": 판단, "근거": BASIS,
           "주의": ["비교대상이 적절한지(비교가능성, 차이 조정, 손실·극단값 처리)는 판단하지 않음 — 입력한 값으로 범위와 차이만 계산",
                  "범위를 사분위로 좁힐지 전체로 볼지, 기준점을 중위값으로 할지는 국조법령이 특정하지 않음 — 선택 이유를 보고서(개별기업보고서 Ⅱ-10·Ⅱ-15)에 밝혀야 함",
                  "사분위 값은 계산법에 따라 달라짐 — 과세당국·상대방이 쓴 계산법과 같은지 확인",
                  "조정액은 차이 × base_amount(지표의 분모)로 본 금액 — 다년도 평균 지표를 썼으면 연도별 배분은 따로"]}
    return out
