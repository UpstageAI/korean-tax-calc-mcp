"""정상가격 범위와 조정액 계산. Claude 작성(2026-11-12).

근거(2021.12.31.·2026.11.1. 시행본 대조): 국제조세조정에 관한 법률 시행령 제15조⑤ — 특수관계 없는 자 간 둘 이상의 거래로 정상가격 범위를 산정해
신고(법 제6조)·결정·경정(법 제7조) 여부 판정에 쓸 수 있다. ⑥ — 거래가격이 그 범위를 벗어나면 범위 거래의 평균값, 중위값, 최빈값, 그 밖의 합리적인
특정 가격을 기준으로 한다. 범위를 어떻게 좁히는지는 법·시행령·시행규칙 조문에 없지만, 시행규칙 별지 제1호서식(거래가격 조정신고서) 작성방법 10이
2022.3.18. 시행규칙부터 비교대상 수익성지표 값의 '정상사분위범위'를 적게 한다(2021.3.16. 시행본에는 없음, 2026-11-14 로컬 보관 원문 대조). 계산법(포함형·배제형)은
정하지 않는다. 사분위 범위는 OECD 이전가격지침 3.57이 비교가능성 결함이 남을 때 쓰는 통계적 도구로 든다. 이 도구는 입력한 비교대상 값으로 범위·기준점·차이만 계산하고, 비교대상이 적절한지는 판단하지 않는다.

2016~2020 개시 사업연도(2026-11-15 구 시행령 2016.2.5.~2020.8.12. 시행본 대조): 구 시행령 제6조④⑤가 같은 내용(둘 이상의 거래로 정상가격 범위, 벗어나면
평균값·중위값·최빈값·그 밖의 합리적인 특정 가격). 2019년까지 개시분은 과세당국의 과세조정(구 법 제4조) 판정에만 쓰는 문언이고, 2020.1.1. 이후 개시분부터
거주자의 신고(구 법 제4조의2)에도 쓴다(대통령령 제30405호 부칙 제2조). 조문 연결은 tp_era."""
from fractions import Fraction

from . import tp_era as ERA

BASIS = "국제조세조정에 관한 법률 시행령 제15조⑤⑥, 법 제6조·제7조"
YEAR_MIN, YEAR_MAX = 2016, 2026


def _fr(x):
    return Fraction(str(x))


def _quantile(xs, q, method):
    """xs 정렬됨. nts(기본): 아래 설명. excel_inc(별칭 inclusive): 위치 (n−1)q(엑셀 QUARTILE.INC — 0.60.x까지 기본), exclusive: 위치 (n+1)q − 1(엑셀 QUARTILE.EXC, n≥3).
    us: 미국 26 CFR §1.482-1(e)(2)(iii)(C) — 보간 없이, 값 이하인 결과가 q 이상이 되는 가장 작은 값.
        그 값 이하인 결과가 정확히 q이면 그 값과 다음 값의 평균(중위값은 q=1/2로 같은 규칙, §1.482-1(e)(3)).
    nts: 국조법 기본통칙 8-15…1(국세청 「외국법인 및 외국인투자기업 납세안내」 2026, 인쇄 272~273쪽) — 아래 사분위 위치 (n+2)/4,
        위 사분위 위치 (3n+2)/4. 위치가 정수면 그 값, 소수면 관례대로 인접 두 값의 평균."""
    n = len(xs)
    if method == "nts":
        if q not in (Fraction(1, 4), Fraction(3, 4)):
            return _quantile(xs, q, "excel_inc")       # 통칙은 아래·위 사분위 위치만 정함 — 중위값은 보통 중앙값
        pos = Fraction(n + 2, 4) if q == Fraction(1, 4) else Fraction(3 * n + 2, 4)   # 1부터 센 위치
        lo = max(1, min(n, int(pos)))
        if pos == lo:
            return xs[lo - 1]
        return (xs[lo - 1] + xs[min(n, lo + 1) - 1]) / 2   # 소수 위치면 관례상 인접 두 값 평균
    if method == "us":
        for i in range(1, n + 1):
            frac = Fraction(i, n)
            if frac >= q:
                return (xs[i - 1] + xs[i]) / 2 if frac == q and i < n else xs[i - 1]
        return xs[-1]
    pos = (n + 1) * q - 1 if method == "exclusive" else (n - 1) * q       # excel_inc·inclusive
    if pos <= 0: return xs[0]
    if pos >= n - 1: return xs[-1]
    lo = int(pos)
    return xs[lo] + (xs[lo + 1] - xs[lo]) * (pos - lo)


QM_ALIASES = {"inclusive": "excel_inc", "nts_rule_8_15": "nts"}
QM_BASIS = "국조법 기본통칙 8-15…1 — 현행 통칙은 조문 MCP에서 확인"
QM_LABEL = {"excel_inc": "엑셀 QUARTILE.INC — 위치 (n−1)×q 선형보간(0.60.x까지 기본)", "exclusive": "위치 (n+1)×q−1 선형보간(엑셀 QUARTILE.EXC)",
            "us": "미국 26 CFR §1.482-1(e)(2)(iii)(C) — 보간 없이 그 값 이하가 25%·50%·75% 이상이 되는 가장 작은 값(정확히 같으면 다음 값과 평균)",
            "nts": "국조법 기본통칙 8-15…1 — 아래 사분위 위치 (n+2)/4, 위 사분위 위치 (3n+2)/4, 소수 위치면 인접 두 값 평균(관례), 중위값은 가운데 값(짝수면 두 값 평균)"}
QM_ALL = ("nts", "nts_rule_8_15", "excel_inc", "inclusive", "exclusive", "us")


def norm_qm(m):
    return QM_ALIASES.get(m, m)


def median_of(xs, m):
    return _quantile(xs, Fraction(1, 2), "us" if m == "us" else "excel_inc")


def method_info(m, n):
    m = norm_qm(m)
    return {"방식": m, "설명": QM_LABEL[m], "n": n, "근거": QM_BASIS if m == "nts" else
            ("26 CFR §1.482-1(e)(2)(iii)(C)" if m == "us" else "엑셀 함수 — 국조법령·통칙 근거 아님(이전 결과 재현용)"), "조정점": "중위값"}


def quartile_sensitivity(xs, t):
    """같은 비교대상으로 세 방식(국세청 통칙·엑셀 INC·미국식) 사분위 범위 — 사용하지 않은 방식은 민감도로."""
    xs = sorted(xs)
    out = {}
    for m, nm in (("nts", "국세청 통칙 8-15…1(기본)"), ("excel_inc", "엑셀 QUARTILE.INC"), ("us", "미국식 26 CFR §1.482-1(e)(2)(iii)(C)")):
        q1, q3 = _quantile(xs, Fraction(1, 4), m), _quantile(xs, Fraction(3, 4), m)
        med = median_of(xs, m)
        out[m] = {"이름": nm, "제1사분위": float(q1), "중위값": float(med), "제3사분위": float(q3),
                  **({"범위_안": q1 <= t <= q3} if t is not None else {})}
    return out


def arm_length_range(comparables, tested_value, base_amount=None, range_type="사분위", point="중위값", point_value=None,
                     tested_is_resident=None, higher_is_more_income=True, quartile_method="nts", year=None):
    문제 = []
    vals, names = [], []
    if not isinstance(comparables, list) or len(comparables) < 2:
        문제.append("comparables — 비교대상 값 둘 이상(시행령 제15조⑤, 2020년까지 구 시행령 제6조④: 둘 이상의 거래). 숫자 목록 또는 [{이름, 값}]")
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
    if quartile_method not in QM_ALL:
        문제.append("quartile_method — 'nts'(국조법 기본통칙 8-15…1, 기본) · 'excel_inc'(엑셀 QUARTILE.INC, 0.60.x까지 기본 — 'inclusive'도 같음) · 'exclusive'(QUARTILE.EXC) · 'us'(미국 26 CFR §1.482-1(e)(2)(iii)(C), 보간 없음)")
    if base_amount is not None and (isinstance(base_amount, bool) or not isinstance(base_amount, (int, float)) or base_amount < 0):
        문제.append("base_amount — 지표의 분모 금액(원, 0 이상): 매출액 대비 이익률이면 매출액, 원가 대비면 원가")
    if year is not None and not (isinstance(year, int) and YEAR_MIN <= year <= YEAR_MAX):
        문제.append(f"year={year!r} — 사업연도 개시연도 {YEAR_MIN}~{YEAR_MAX}")
    if range_type == "사분위" and quartile_method == "exclusive" and len(vals) < 3:
        문제.append("quartile_method='exclusive'는 비교대상 셋 이상 필요")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    A = ERA.RANGE[ERA.era(year)]
    xs = sorted(vals)
    n = len(xs)
    quartile_method = norm_qm(quartile_method)
    median = median_of(xs, quartile_method)
    mean = sum(xs) / n
    q1 = _quantile(xs, Fraction(1, 4), quartile_method)
    q3 = _quantile(xs, Fraction(3, 4), quartile_method)
    lo, hi = (q1, q3) if range_type == "사분위" else (xs[0], xs[-1])
    t = _fr(tested_value)
    inside = lo <= t <= hi
    ref = median if point == "중위값" else mean if point == "평균값" else _fr(point_value)
    판단 = [{"항목": "범위", "결론": (f"비교대상 {n}개의 " + ("사분위 범위(제1사분위~제3사분위)" if range_type == "사분위" else "전체 범위(최솟값~최댓값)")
                                + f" {float(lo):.4%} ~ {float(hi):.4%}"),
           "근거": A["범위"] + ((" — 사분위 범위: 조문에는 없고 거래가격 조정신고서(시행규칙 별지 제1호서식, 2022.3.18. 시행규칙부터) 작성방법 10이 정상사분위범위 기재를 전제, 계산법은 정하지 않음(OECD 지침 3.57)" if (year or 2026) >= 2022 else " — 사분위로 좁히는 방법은 국조법령에 없음(OECD 지침 3.57의 통계적 도구)") if range_type == "사분위" else "")}]
    결과 = {"비교대상_수": n, "최솟값": float(xs[0]), "제1사분위": float(q1), "중위값": float(median), "제3사분위": float(q3), "최댓값": float(xs[-1]),
           "평균값": float(mean), "범위": {"종류": range_type, "하한": float(lo), "상한": float(hi)}, "분석대상_값": float(t), "범위_안": inside,
           "사분위_방식": method_info(quartile_method, n)}
    if inside:
        결과.update({"조정_필요": False, "차이": 0.0, "조정액": 0})
        판단.append({"항목": "판정", "결론": f"분석대상 값 {float(t):.4%}이 범위 안 — 조정하지 않음", "근거": A["범위"] + ", OECD 지침 3.60"})
    else:
        if point == "직접입력" and not (lo <= ref <= hi):
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"point_value={float(ref)} — 기준점은 정상가격 범위({float(lo):.6f}~{float(hi):.6f}) 안의 값이어야 함({A['기준점']}: 그 범위 거래의 값)"]}
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
                   "근거": A["기준점"] + "(범위 거래의 평균값, 중위값, 최빈값, 그 밖의 합리적인 특정 가격)"})
        신고 = f"납세자는 정상가격 기준으로 신고할 수 있음({A['법_신고']})" if A["법_신고"] else "납세자가 정상가격으로 스스로 신고하는 조문(구 법 제4조의2)은 2020.1.1. 이후 개시 과세연도부터 — 이 연도는 수정신고로 반영(구 시행령 제15조의2①)"
        판단.append({"항목": "조정 방향", "결론": (f"거주자 소득이 정상가격보다 적음 — 과세당국의 증액 결정·경정 대상({A['법_경정']}), {신고}" if resident_income_low
                                          else "거주자 소득이 정상가격보다 많음 — " + (f"납세자가 정상가격 기준으로 신고하거나 경정청구할 수 있음({A['법_신고']})" if A["법_신고"] else "감액은 경정청구·상호합의 등 절차를 따로 확인(구 법 제4조의2는 2020.1.1. 이후 개시 과세연도부터)") + ". 상대국 과세와 맞물리면 대응조정·상호합의 검토"),
                   "근거": A["법"]})
    비교대상_확인 = [
        {"항목": "비교가능 거래의 뜻", "내용": "비교되는 상황 간의 차이가 가격이나 순이익에 중대한 영향을 주지 않거나, 주더라도 그 차이를 제거할 합리적 조정이 가능한 거래", "근거": A["비교가능"]},
        {"항목": "분석요소", "내용": "재화·용역의 종류와 특성, 사업활동의 기능, 거래에 수반되는 위험, 사용되는 자산, 계약 조건, 경제 여건(시장 규모·거래단계·경쟁 정도), 사업전략", "근거": A["분석요소"]},
        {"항목": "내부 비교가능 거래", "내용": "분석대상 당사자가 특수관계 없는 독립된 사업자와 한 거래를 외부 자료보다 먼저 수집·검토", "근거": A["내부거래"]},
        {"항목": "제외할 수 있는 거래", "내용": "거래 당사자가 임의로 조작해 정상적인 거래로 볼 수 없는 거래는 비교가능한 거래로 선택하지 않을 수 있음", "근거": A["제외"]},
        {"항목": "이익률 자료의 한계", "내용": "공시 재무제표나 데이터베이스에서 얻은 이익률만으로는 기능·위험·거래 조건·규모가 비슷한지 확인할 수 없음 — 탐색 조건, 단계별 탈락 사유, 차이 조정을 문서로 남겨야 비교대상으로 설명할 수 있음", "근거": A["이익률"]},
        {"항목": "과세당국의 재산정", "내용": "과세당국은 다른 비교대상이나 산출방법으로 정상가격을 다시 산정할 수 있음 — 한 출처에 기대지 말고 내부 거래·공시 자료·데이터베이스 등 여러 출처로 맞춰 봄", "근거": A["재산정"]}]
    out = {"결과": 결과, "사분위_민감도": quartile_sensitivity(xs, t), "비교대상_확인": 비교대상_확인, "계산": {"비교대상_정렬": [{"이름": nm, "값": float(v)} for v, nm in sorted(zip(vals, names))],
                             "사분위_계산법": QM_LABEL[quartile_method],
                             "비교대상_수": n, "조정점": "중위값" if point == "중위값" else point},
           "판단": 판단, "근거": A["근거"],
           "주의": ["비교대상이 적절한지(비교가능성, 차이 조정, 손실·극단값 처리)는 판단하지 않음 — 입력한 값으로 범위와 차이만 계산. 후보 목록을 거르는 일은 tp_comparable_screen",
                  "사분위 계산법과 기준점(중위값 등)은 국조법령이 특정하지 않음 — 기본은 국세청 기본통칙 8-15…1(위치 (n+2)/4·(3n+2)/4, quartile_method='nts'), 엑셀 QUARTILE.INC('excel_inc')·미국식('us')은 사분위_민감도에 함께. 2022.3.18. 시행규칙부터 거래가격 조정신고서는 정상사분위범위 기재를 전제함. 선택 이유를 보고서(개별기업보고서 Ⅱ-10·Ⅱ-15)에 밝혀야 함",
                  *(["2019년까지 개시한 과세연도: 구 시행령 제6조④⑤는 정상가격 범위를 과세당국의 과세조정 판정에 쓰는 것으로만 정함 — 거주자의 신고에 쓰는 문언은 2020.1.1. 이후 개시 과세연도부터(대통령령 제30405호 부칙 제2조)"] if ERA.era(year) == ERA.ERA_OLD else []),
                  "사분위 값은 계산법에 따라 달라짐 — 과세당국·상대방이 쓴 계산법과 같은지 확인",
                  "조정액은 차이 × base_amount(지표의 분모)로 본 금액 — 다년도 평균 지표를 썼으면 연도별 배분은 따로"]}
    return out
