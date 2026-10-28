"""부가가치세 공급시기 판정 — 거래별 공급시기와 예정신고기간·과세기간 귀속 금액 (2016~2026 공급분).

조문(법제처 시행본 원문 대조, 2026-10-28 Claude):
- 법 제15조(재화: 인도·이용가능·공급 확정), 제16조(용역: 역무 제공 완료) — 2016~2026 문구 변경 없음.
- 영 제28조①표1(현금·외상·할부판매 → 인도·이용가능), ②(조건부·기한부 → 판매 확정), ③(대가의 각 부분을 받기로 한 때:
  1호 장기할부, 2호 완성도기준지급, 3호 중간지급조건부, 4호 전력 등 계속 공급; 단서: 2호·3호는 인도·이용가능일 이후
  받기로 한 부분은 인도·이용가능일), ⑥(수출: 내국물품 외국 반출 → 선적일).
  ③ 단서는 2014.1.1 시행본부터 같은 문구 — 2016~2026 변경 없음(2025.12.30 개정은 '기획재정부령'→'재정경제부령' 부처명뿐).
- 영 제29조①(용역: 같은 4가지, 단서는 역무 제공 완료일) — 2016~2026 변경 없음(부처명만).
- 영 제30조(법 제17조④ 대상: 1호 장기할부, 2호 전력 등 계속 공급, 3호 구획 불가 용역 계속 공급, 4호 외국항행용역 —
  4호는 2024 개정, 이 도구는 지원 안 함).
- 시행규칙 제17조(장기할부판매: 2회 이상 분할 + 인도일 다음 날부터 최종 할부금 지급기일까지 1년 이상),
  제18조(중간지급조건부 재화: 1호 계약금 받기로 한 날의 다음 날부터 인도·이용가능일까지 6개월 이상 + 그 기간 이내에 계약금 외
  대가를 분할, 2호 국고금 관리법 제26조 경비 선급, 3호 지방회계법 제35조 선금급(2019.7.1 전 지방재정법 제73조)),
  제19조·제20조(용역의 장기할부·중간지급조건부 — 기준일이 '역무 제공 완료일'). 2016~2026 요건 문구 변경 없음.
- 기간 계산: 국세기본법 제4조 → 민법 제157조(초일 불산입)·제160조(역에 의한 계산: 기산일에 해당한 날의 전일 만료,
  해당일이 없으면 그 월의 말일 만료). 규칙이 '다음 날부터'로 기산일을 정해 두었으므로 기산일 = 인도일(계약금일) + 1일.

법 제17조(세금계산서 선발급 특례) 연도표 — 적용 기준: 각 개정 부칙 '이 법 시행 이후 재화나 용역을 공급하는 분부터'(본래 공급시기 기준).
- ~2017.12.31 공급분: ① 대가를 받고 '이와 동시에' 발급 / ② 발급일부터 7일 이내 수령 / ③ 계약서에 청구시기·지급시기 따로 적고
  그 사이 30일 이내(두 요건 모두).
- 2018.1.1~2018.12.31: ① '동시에' 삭제(법률 제15223호 2017.12.19, 부칙 제2조 시행 이후 공급분부터) / ③ 따로 적을 것 + (30일 이내
  또는 발급일이 속하는 과세기간(조기환급이면 발급일부터 30일)에 대금 지급 확인).
- 2019.1.1~2021.12.31: ③ 어느 하나(법률 제16101호 2018.12.31, 부칙 제2조 시행 이후 공급분부터): 1호 청구시기(발급일)·지급시기 따로
  적고 30일 이내, 2호 발급일이 속하는 과세기간(조기환급 30일)에 공급시기 도래 + 대금 지급 확인.
- 2022.1.1~: ③2호에서 대금 지급 확인 요건 삭제(법률 제18577호 2021.12.8, 부칙 제6조 '이 법 시행 전에 공급한 경우의 공급시기에
  관하여는 제17조제3항제2호의 개정규정에도 불구하고 종전의 규정에 따른다').
- ④(영 제30조 1~3호): 공급시기 전 발급하면 발급한 때 — 2016~2026 같음.

지원하지 않는 것(입력 확인 필요로 멈춤): 상품권·가공·무인판매기·보세구역·임치물·위탁판매·간주공급(법 제10조), 중계무역·위탁판매수출·
외국인도수출 등 선적일 외 수출, 부동산 임대(간주임대료)·선불 연회비 등 영 제29조②, 외국항행용역(영 제30조4호), 폐업일 의제(영 제28조⑨·제29조③),
시설물·권리 사용 용역(법 제16조①2호), 2016년 이전·2026년 이후 공급분.
"""

import calendar
from datetime import date, timedelta

FIRST, LAST = date(2016, 1, 1), date(2026, 12, 31)

# 종류 → (구분, 형태). 별칭은 사용자가 흔히 쓰는 말.
_KIND = {
    "일반": ("재화", "일반"), "일반판매": ("재화", "일반"), "현금판매": ("재화", "일반"), "외상판매": ("재화", "일반"),
    "인도": ("재화", "일반"), "단기할부": ("재화", "할부"), "할부": ("재화", "할부"), "할부판매": ("재화", "할부"),
    "장기할부": ("재화", "할부"), "장기할부판매": ("재화", "할부"),
    "중간지급조건부": ("재화", "중간지급"), "중간지급": ("재화", "중간지급"),
    "완성도기준지급": ("재화", "완성도"), "완성도기준": ("재화", "완성도"), "완성도기준지급조건부": ("재화", "완성도"),
    "계속적공급": ("재화", "계속"), "전력": ("재화", "계속"), "계속공급": ("재화", "계속"),
    "조건부판매": ("재화", "조건부"), "기한부판매": ("재화", "조건부"), "반환조건부판매": ("재화", "조건부"), "동의조건부판매": ("재화", "조건부"),
    "수출": ("재화", "수출"), "직수출": ("재화", "수출"),
    "용역": ("용역", "일반"), "용역_일반": ("용역", "일반"),
    "용역_할부": ("용역", "할부"), "용역_장기할부": ("용역", "할부"), "장기할부조건부용역": ("용역", "할부"),
    "용역_중간지급조건부": ("용역", "중간지급"), "용역_중간지급": ("용역", "중간지급"),
    "용역_완성도기준지급": ("용역", "완성도"), "용역_완성도기준": ("용역", "완성도"),
    "용역_계속적공급": ("용역", "계속"), "용역_계속공급": ("용역", "계속"),
}
KINDS = sorted(_KIND)


class InputError(ValueError):
    pass


def _d(v, what):
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise InputError(f"{what} '{v}' — YYYY-MM-DD 형식 필요")


def _civil_end(start: date, years: int = 0, months: int = 0) -> date:
    """민법 제160조: 기산일 start부터 n년·n개월 기간의 만료일(기산일에 해당한 날의 전일, 해당일이 없으면 그 월의 말일)."""
    m = start.month - 1 + months + years * 12
    y, mo = start.year + m // 12, m % 12 + 1
    last = calendar.monthrange(y, mo)[1]
    if start.day > last:
        return date(y, mo, last)
    return date(y, mo, start.day) - timedelta(days=1)


def _rule17_era(d: date) -> str:
    if d < date(2018, 1, 1):
        return "2016~2017"
    if d < date(2019, 1, 1):
        return "2018"
    if d < date(2022, 1, 1):
        return "2019~2021"
    return "2022~"


def _half(d: date):
    return (d.year, 1 if d.month <= 6 else 2)


def period_of(d: date, 간이: bool) -> dict:
    """공급시기 → 과세기간·예정신고(부과)기간 (법 제5조①, 제48조①, 제66조①)."""
    if 간이:
        return {"과세기간": f"{d.year}", "예정구분": "예정부과기간" if d.month <= 6 else "예정부과기간 후",
                "기간키": f"{d.year} {'예정부과기간(1.1~6.30)' if d.month <= 6 else '7.1~12.31'}"}
    y, h = _half(d)
    pre = d.month in (1, 2, 3, 7, 8, 9)
    rng = {(1, True): "1.1~3.31", (1, False): "4.1~6.30", (2, True): "7.1~9.30", (2, False): "10.1~12.31"}[(h, pre)]
    return {"과세기간": f"{y}-{h}기", "예정구분": "예정" if pre else "확정",
            "기간키": f"{y}-{h}기 {'예정' if pre else '확정'}({rng})"}


def _tax_period_end(d: date, 간이: bool) -> date:
    if 간이:
        return date(d.year, 12, 31)
    return date(d.year, 6, 30) if d.month <= 6 else date(d.year, 12, 31)


def parse_query(period: str | None, 간이: bool):
    """조회 기간 → (시작일, 종료일, 표시). 일반: 'YYYY-1기 예정|확정' 또는 'YYYY-1기'(과세기간 전체). 간이: 'YYYY' 또는 'YYYY 예정부과'."""
    if not period:
        return None
    s = str(period).replace(" ", "").replace("제", "")
    import re
    if 간이:
        m = re.fullmatch(r"(\d{4})(예정부과(기간)?)?", s)
        if not m:
            raise InputError(f"조회 기간 '{period}' — 간이과세자는 'YYYY'(과세기간 1.1~12.31) 또는 'YYYY 예정부과'(1.1~6.30)")
        y = int(m.group(1))
        if m.group(2):
            return date(y, 1, 1), date(y, 6, 30), f"{y} 예정부과기간(1.1~6.30)"
        return date(y, 1, 1), date(y, 12, 31), f"{y} 과세기간(1.1~12.31)"
    m = re.fullmatch(r"(\d{4})-?([12])기?(예정|확정)?(신고)?", s)
    if not m:
        raise InputError(f"조회 기간 '{period}' — 'YYYY-1기 예정'·'YYYY-1기 확정'·'YYYY-2기'처럼 입력")
    y, h, kind = int(m.group(1)), int(m.group(2)), m.group(3)
    a, b = (date(y, 1, 1), date(y, 6, 30)) if h == 1 else (date(y, 7, 1), date(y, 12, 31))
    if kind == "예정":
        return a, (date(y, 3, 31) if h == 1 else date(y, 9, 30)), f"{y}-{h}기 예정신고기간"
    if kind == "확정":
        return (date(y, 4, 1) if h == 1 else date(y, 10, 1)), b, f"{y}-{h}기 확정신고 대상(예정신고기간 후 {'4.1~6.30' if h == 1 else '10.1~12.31'})"
    return a, b, f"{y}-{h}기 과세기간 전체"


# ── 거래 1건의 본래 공급시기(대가 부분별) ────────────────────────────────────
def _schedule(tx, i):
    pays = tx.get("대가") or tx.get("대가_지급_약정") or []
    out = []
    for j, p in enumerate(pays):
        if not isinstance(p, dict):
            raise InputError(f"거래{i}: 대가는 [{{약정일, 금액, 구분?}}] 목록")
        d = _d(p.get("약정일"), f"거래{i} 대가{j + 1} 약정일")
        amt = p.get("금액")
        if d is None or amt is None:
            raise InputError(f"거래{i} 대가{j + 1}: 약정일·금액 필요")
        out.append({"약정일": d, "금액": int(amt), "구분": str(p.get("구분") or "")})
    return sorted(out, key=lambda x: x["약정일"])


def _base_parts(tx, i):
    """→ (판정 형태, [ {공급시기, 금액, 사유, 근거} ], 판단 목록, 영30조_대상)."""
    kind = str(tx.get("종류") or "").replace(" ", "")
    if kind not in _KIND:
        raise InputError(f"거래{i}: 종류 '{tx.get('종류')}' — 지원 종류: {', '.join(KINDS)} (그 밖의 거래 형태는 입력 확인 필요)")
    구분, 형태 = _KIND[kind]
    if str(tx.get("구분") or 구분) != 구분:
        raise InputError(f"거래{i}: 구분 '{tx.get('구분')}'과 종류 '{kind}'가 맞지 않음")
    pays = _schedule(tx, i)
    total = tx.get("공급가액")
    total = int(total) if total is not None else sum(p["금액"] for p in pays)
    if pays and tx.get("공급가액") is not None and sum(p["금액"] for p in pays) != total:
        raise InputError(f"거래{i}: 대가 약정 합계 {sum(p['금액'] for p in pays):,}원 ≠ 공급가액 {total:,}원")
    재화 = 구분 == "재화"
    기준명 = "인도일(이용가능일)" if 재화 else "역무 제공 완료일"
    기준 = _d(tx.get("인도일") or tx.get("이용가능일") or tx.get("완료일"), f"거래{i} {기준명}")
    판단 = []
    법 = "부가가치세법 제15조①" if 재화 else "부가가치세법 제16조①1호"
    영 = "부가가치세법 시행령 제28조③" if 재화 else "부가가치세법 시행령 제29조①"

    def whole(d, why, basis):
        if d is None:
            raise InputError(f"거래{i}: {why} — 날짜 필요")
        return [{"공급시기": d, "금액": total, "사유": why, "근거": basis}]

    if 형태 == "일반":
        why = "재화가 인도되거나 이용가능하게 되는 때" if 재화 else "역무의 제공이 완료되는 때"
        if 기준 is None:
            raise InputError(f"거래{i}: {기준명} 필요")
        return ("현금·외상판매(인도)" if 재화 else "용역(역무 제공 완료)"), whole(기준, why, 법 + (", 시행령 제28조①표1" if 재화 else "")), 판단, False
    if 형태 == "수출":
        d = _d(tx.get("선적일"), f"거래{i} 선적일")
        if d is None:
            raise InputError(f"거래{i}: 수출(내국물품 외국 반출)은 선적일(기적일) 필요")
        return "수출(내국물품 외국 반출)", whole(d, "수출재화의 선(기)적일", "부가가치세법 시행령 제28조⑥표1"), 판단, False
    if 형태 == "조건부":
        d = _d(tx.get("확정일"), f"거래{i} 확정일")
        if d is None:
            raise InputError(f"거래{i}: 조건부·기한부 판매는 확정일(조건 성취·기한 경과로 판매가 확정되는 날) 필요")
        return "조건부·기한부 판매", whole(d, "조건이 성취되거나 기한이 지나 판매가 확정되는 때", "부가가치세법 시행령 제28조②"), 판단, False
    if not pays:
        raise InputError(f"거래{i}: '{kind}'는 대가 지급 약정 [{{약정일, 금액}}] 필요")

    each = lambda why, basis: [{"공급시기": p["약정일"], "금액": p["금액"], "사유": why, "근거": basis} for p in pays]

    if 형태 == "계속":
        basis = f"{영}4호"
        return ("전력 등 계속적 공급" if 재화 else "구획할 수 없는 용역의 계속적 공급"), each("대가의 각 부분을 받기로 한 때", basis), 판단, True

    if 기준 is None:
        raise InputError(f"거래{i}: '{kind}' 판정에 {기준명} 필요")

    if 형태 == "할부":
        규칙 = "시행규칙 제17조" if 재화 else "시행규칙 제19조"
        last = pays[-1]["약정일"]
        start = 기준 + timedelta(days=1)
        end1y = _civil_end(start, years=1)
        ok_n = len(pays) >= 2
        ok_t = last >= end1y
        판단.append({"항목": "장기할부 요건", "결론": (
            f"분할 {len(pays)}회({'2회 이상' if ok_n else '2회 미만'}), {기준명} 다음 날 {start} 기산 1년 만료일 {end1y} — "
            f"최종 할부금 지급기일 {last} {'≥ 만료일 → 1년 이상' if ok_t else '< 만료일 → 1년 미만'} → "
            + ("장기할부" if ok_n and ok_t else "장기할부 아님(단기할부 — " + ("인도일" if 재화 else "완료일") + " 일괄)")),
            "근거": f"부가가치세법 {규칙}, 국세기본법 제4조·민법 제157조·제160조"})
        if ok_n and ok_t:
            return ("장기할부판매" if 재화 else "장기할부조건부 용역"), each("대가의 각 부분을 받기로 한 때(장기할부)", f"{영}1호, {규칙}"), 판단, True
        why = "재화가 인도되거나 이용가능하게 되는 때(할부판매)" if 재화 else "역무의 제공이 완료되는 때"
        return ("할부판매(장기할부 아님)" if 재화 else "용역(장기할부 아님)"), whole(기준, why, (법 + ", 시행령 제28조①표1") if 재화 else 법), 판단, False

    if 형태 == "중간지급":
        규칙 = "시행규칙 제18조" if 재화 else "시행규칙 제20조"
        if tx.get("국고_선금급"):
            판단.append({"항목": "중간지급조건부 요건", "결론": "국고금 관리법 제26조 경비 선급·지방회계법 제35조(2019.7.1 전 지방재정법 제73조) 선금급 → 중간지급조건부",
                       "근거": f"부가가치세법 {규칙} 2호·3호"})
            ok = True
        else:
            dep = [p for p in pays if p["구분"] == "계약금"]
            if len(dep) > 1:
                raise InputError(f"거래{i}: 계약금이 2건 — 계약금 약정은 1건만 '구분':'계약금'으로")
            c = dep[0] if dep else pays[0]
            start = c["약정일"] + timedelta(days=1)
            end6 = _civil_end(start, months=6)
            ok_t = 기준 >= end6
            rest = [p for p in pays if p is not c]
            in_period = [p for p in rest if start <= p["약정일"] < 기준]
            ok_split = len(rest) >= 2 and len(in_period) >= 1
            판단.append({"항목": "중간지급조건부 요건", "결론": (
                f"계약금 약정일 {c['약정일']}{'' if dep else '(구분 없음 — 첫 약정을 계약금으로 봄)'} 다음 날 {start} 기산 6개월 만료일 {end6} — "
                f"{기준명} {기준} {'≥ 만료일 → 6개월 이상' if ok_t else '< 만료일 → 6개월 미만'}; "
                f"계약금 외 대가 {len(rest)}회 분할, {기준명} 전 기간 안 약정 {len(in_period)}회 "
                f"{'→ 분할 수령 충족' if ok_split else '→ 분할 수령 아님(계약금 외 대가가 2회 이상이고 그중 1회 이상이 기간 안이어야 함)'} → "
                + ("중간지급조건부" if ok_t and ok_split else "중간지급조건부 아님(" + ("인도일" if 재화 else "완료일") + " 일괄)")),
                "근거": f"부가가치세법 {규칙} 1호, 국세기본법 제4조·민법 제157조·제160조"})
            ok = ok_t and ok_split
        if not ok:
            why = "재화가 인도되거나 이용가능하게 되는 때" if 재화 else "역무의 제공이 완료되는 때"
            return ("인도 기준(중간지급조건부 아님)" if 재화 else "용역 완료 기준(중간지급조건부 아님)"), whole(기준, why, 법), 판단, False
        parts = []
        for p in pays:
            if p["약정일"] >= 기준:
                parts.append({"공급시기": 기준, "금액": p["금액"], "사유": f"{기준명} 이후({p['약정일']}) 받기로 한 대가 → {기준명}", "근거": f"{영} 단서"})
            else:
                parts.append({"공급시기": p["약정일"], "금액": p["금액"], "사유": "대가의 각 부분을 받기로 한 때(중간지급조건부)", "근거": f"{영}3호, {규칙}"})
        return ("중간지급조건부 재화" if 재화 else "중간지급조건부 용역"), parts, 판단, False

    if 형태 == "완성도":
        parts = []
        for p in pays:
            if p["약정일"] >= 기준:
                parts.append({"공급시기": 기준, "금액": p["금액"], "사유": f"{기준명} 이후({p['약정일']}) 받기로 한 대가 → {기준명}", "근거": f"{영} 단서"})
            else:
                parts.append({"공급시기": p["약정일"], "금액": p["금액"], "사유": "대가의 각 부분을 받기로 한 때(완성도기준지급)", "근거": f"{영}2호"})
        return ("완성도기준지급조건부 재화" if 재화 else "완성도기준지급조건부 용역"), parts, 판단, False
    raise InputError(f"거래{i}: 종류 '{kind}' 미지원")


# ── 법 제17조 선발급 특례 ──────────────────────────────────────────────────
def _special_ok(inv, piece_date, 영30, 간이):
    """세금계산서 1장이 본래 공급시기 piece_date인 부분에 대해 제17조 특례를 충족하는지 → (충족, 설명, 근거)."""
    발급 = inv["발급일"]
    era = _rule17_era(piece_date)
    if 영30:
        return True, "영 제30조 대상(장기할부·계속적 공급) — 공급시기 전 발급하면 발급한 때", "부가가치세법 제17조④, 시행령 제30조"
    수령 = inv["수령일"]
    if 수령 is not None:
        if era == "2016~2017":
            if 수령 == 발급:
                return True, "대가를 받고 동시에 발급(2017년까지 공급분은 '동시에' 요건)", "부가가치세법 제17조①(2017.12.19 개정 전)"
        elif 수령 <= 발급:
            return True, f"대가를 받고({수령}) 그 받은 대가에 대해 발급", "부가가치세법 제17조①"
        if 발급 < 수령 <= 발급 + timedelta(days=7):
            return True, f"발급일부터 7일 이내({발급 + timedelta(days=7)}까지) 대가 수령({수령})", "부가가치세법 제17조②, 민법 제157조"
    # ③ (7일 경과 후 수령 등)
    별도, 지급 = inv["별도기재"], inv["지급시기"]
    within30 = bool(별도 and 지급 is not None and 지급 <= 발급 + timedelta(days=30))
    if inv["조기환급"]:
        win_end, win_txt = 발급 + timedelta(days=30), f"발급일부터 30일 이내({발급 + timedelta(days=30)}까지, 공급받는 자 조기환급)"
    else:
        win_end, win_txt = _tax_period_end(발급, 간이), f"발급일이 속하는 과세기간({_tax_period_end(발급, 간이)}까지)"
    paid_in = 수령 is not None and 수령 <= win_end
    due_in = piece_date <= win_end
    if era == "2016~2017":
        if within30:
            return True, "계약서에 청구시기·지급시기를 따로 적고 그 사이 30일 이내(요건 모두)", "부가가치세법 제17조③(2017년까지 공급분)"
        return False, "7일 이내 수령 아님 — 2017년까지 공급분은 계약서 청구·지급시기 별도 기재 + 30일 이내 요건 모두 필요", "부가가치세법 제17조②③(2017.12.19 개정 전)"
    if era == "2018":
        if 별도 and (within30 or paid_in):
            return True, "계약서에 청구·지급시기 별도 기재 + " + ("30일 이내" if within30 else f"{win_txt}에 대금 지급 확인"), "부가가치세법 제17조③(2018년 공급분, 법률 제15223호)"
        return False, "2018년 공급분 ③: 청구·지급시기 별도 기재가 필수이고 30일 이내 또는 과세기간 내 대금 지급 확인 필요", "부가가치세법 제17조③(법률 제15223호)"
    if within30:
        return True, "계약서에 청구시기(발급일)·지급시기를 따로 적고 그 사이 30일 이내", "부가가치세법 제17조③1호"
    if era == "2019~2021":
        if due_in and paid_in:
            return True, f"{win_txt}에 공급시기({piece_date}) 도래 + 대금 지급({수령}) 확인", "부가가치세법 제17조③2호(2018.12.31 개정, 2021년까지 공급분)"
        return False, f"③2호(2019~2021 공급분): {win_txt}에 공급시기 도래와 대금 지급 확인이 모두 필요 — 공급시기 {piece_date}, 수령일 {수령 or '없음'}", "부가가치세법 제17조③2호(법률 제16101호)"
    if due_in:
        return True, f"{win_txt}에 공급시기({piece_date}) 도래", "부가가치세법 제17조③2호(2021.12.8 개정, 2022년 공급분부터)"
    return False, f"7일 이내 수령·30일 약정·{win_txt} 내 공급시기 도래 어느 것에도 해당 안 함", "부가가치세법 제17조②③"


def _apply_invoices(tx, i, parts, 영30, 간이, 판단):
    invs = tx.get("세금계산서") or []
    if isinstance(invs, dict):
        invs = [invs]
    if tx.get("세금계산서_발급일"):
        invs = list(invs) + [{"발급일": tx["세금계산서_발급일"], "금액": tx.get("세금계산서_금액"), "수령일": tx.get("수령일"),
                              "청구지급시기_별도기재": tx.get("청구지급시기_별도기재"), "지급시기": tx.get("지급시기"),
                              "공급받는자_조기환급": tx.get("공급받는자_조기환급")}]
    if not invs:
        return parts
    total = sum(p["금액"] for p in parts)
    norm = []
    for k, v in enumerate(invs):
        if not isinstance(v, dict):
            raise InputError(f"거래{i}: 세금계산서는 [{{발급일, 금액, 수령일?, ...}}] 목록")
        발급 = _d(v.get("발급일"), f"거래{i} 세금계산서{k + 1} 발급일")
        if 발급 is None:
            raise InputError(f"거래{i} 세금계산서{k + 1}: 발급일 필요")
        norm.append({"발급일": 발급, "금액": int(v["금액"]) if v.get("금액") is not None else (total if len(invs) == 1 else None),
                     "수령일": _d(v.get("수령일"), f"거래{i} 세금계산서{k + 1} 수령일"),
                     "별도기재": bool(v.get("청구지급시기_별도기재")), "지급시기": _d(v.get("지급시기"), f"거래{i} 세금계산서{k + 1} 지급시기"),
                     "조기환급": bool(v.get("공급받는자_조기환급"))})
        if norm[-1]["금액"] is None:
            raise InputError(f"거래{i} 세금계산서{k + 1}: 세금계산서가 여러 장이면 장마다 금액 필요")
    pool = sorted([dict(p) for p in parts], key=lambda x: x["공급시기"])
    out = []
    for inv in sorted(norm, key=lambda x: x["발급일"]):
        left = inv["금액"]
        cand = [p for p in pool if p["공급시기"] > inv["발급일"] and p["금액"] > 0]
        뒤 = sum(p["금액"] for p in cand)
        if 뒤 < left:
            판단.append({"항목": f"세금계산서 {inv['발급일']} {left:,}원 중 {left - 뒤:,}원",
                       "결론": "본래 공급시기 당일·이후 발급분 — 선발급 특례 대상 아님, 공급시기는 본래대로(발급 시기·가산세는 제34조·제60조로 별도 확인)",
                       "근거": "부가가치세법 제17조(공급시기 '전' 발급만 해당)"})
        for p in cand:
            if left <= 0:
                break
            take = min(left, p["금액"])
            ok, why, basis = _special_ok(inv, p["공급시기"], 영30, 간이)
            판단.append({"항목": f"선발급 세금계산서 {inv['발급일']} → 본래 공급시기 {p['공급시기']} 부분 {take:,}원",
                       "결론": ("특례 적용 — 발급일을 공급시기로 봄: " if ok else "특례 미적용 — 본래 공급시기 유지(세금계산서 발급 시기 가산세는 별도 확인): ") + why,
                       "근거": basis + (f" [{_rule17_era(p['공급시기'])} 공급분 문구]" if not 영30 else "")})
            if ok:
                out.append({"공급시기": inv["발급일"], "금액": take, "사유": "공급시기 전 세금계산서 발급 특례 — " + why, "근거": basis})
                p["금액"] -= take
            left -= take
    return out + [p for p in pool if p["금액"] > 0]


def judge(transactions, 사업자="일반", period=None):
    if 사업자 not in ("일반", "간이", "일반과세자", "간이과세자"):
        raise InputError("사업자 — '일반' 또는 '간이'")
    간이 = 사업자.startswith("간이")
    if not transactions or not isinstance(transactions, list):
        raise InputError("transactions — 거래 목록 [{종류, 인도일?, 대가: [{약정일, 금액}], ...}] 필요")
    q = parse_query(period, 간이)
    rows, 판단전체, 기간합 = [], [], {}
    for n, tx in enumerate(transactions, 1):
        if not isinstance(tx, dict):
            raise InputError(f"거래{n}: 객체(dict)로 입력")
        name = tx.get("이름") or f"거래{n}"
        형태, parts, 판단, 영30 = _base_parts(tx, n)
        parts = _apply_invoices(tx, n, parts, 영30, 간이, 판단)
        merged = {}
        for p in parts:
            if p["공급시기"] < FIRST:
                raise InputError(f"{name}: 공급시기 {p['공급시기']} — 2016-01-01 전 공급분은 지원하지 않음")
            if p["공급시기"] > LAST and not any(j.get("항목") == "2027년 이후 공급시기" for j in 판단):
                판단.append({"항목": "2027년 이후 공급시기", "결론": "2026-10-28 현재 시행본 기준으로 기간만 배정(제15~17조·영 제28~30조 시행 예정 개정 없음 확인) — 그 해 조문 재확인 필요",
                           "근거": "법제처 연혁(article_history) 2026-10-28 확인"})
            key = (p["공급시기"], p["사유"], p["근거"])
            merged[key] = merged.get(key, 0) + p["금액"]
        items = []
        for (d, why, basis), amt in sorted(merged.items()):
            per = period_of(d, 간이)
            items.append({"공급시기": d.isoformat(), "금액": amt, "과세기간": per["과세기간"], "신고기간": per["기간키"], "사유": why, "근거": basis})
            기간합[per["기간키"]] = 기간합.get(per["기간키"], 0) + amt
        row = {"거래": name, "판정": 형태, "공급시기별": items, "합계": sum(x["금액"] for x in items)}
        if q:
            row["조회기간_귀속"] = sum(x["금액"] for x in items if q[0] <= date.fromisoformat(x["공급시기"]) <= q[1])
        rows.append(row)
        판단전체 += [{"거래": name, **j} for j in 판단]
    result = {"기간별_과세표준": dict(sorted(기간합.items())), "거래_합계": sum(r["합계"] for r in rows)}
    if q:
        result["조회기간"] = f"{q[2]} {q[0]}~{q[1]}"
        result["조회기간_과세표준"] = sum(r["조회기간_귀속"] for r in rows)
    return result, rows, 판단전체
