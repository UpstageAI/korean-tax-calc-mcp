"""건물 기준시가 — 국세청 「건물 기준시가 계산방법 고시」(2026년 적용: 제2025-39호). 소득세법 제99조①1호나목(양도세 기준시가)·상증법 제61조①2호(보충적 평가).
㎡당 금액 = 건물신축가격기준액 × 구조지수 × 용도지수 × 위치지수 × 경과연수별잔가율 (× 개별건물특성조정률: 상속·증여세만), 1,000원 미만 버림; 기준시가 = 면적 × ㎡당 금액.
지수표는 2026년 적용분(원문). 다른 연도는 신축가격기준액만 그 해 값이고 지수는 2026표로 근사(결과에 표시). 작성 Claude 2026-10-30."""
from __future__ import annotations

import json
import os
import re
from typing import Any

_RULES: dict | None = None


def _rules() -> dict:
    global _RULES
    if _RULES is None:
        p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "building_std_price_rules.json")
        with open(p, encoding="utf-8") as f:
            _RULES = json.load(f)
    return _RULES


_STRUCT_SYN = [   # (표현들, 고시 구조명)
    (("철골철근", "src", "철골·철근"), "철골(철골철근)콘크리트조"),
    (("철근콘크리트", "철콘", "rc", "콘크리트조", "콘크리트"), "철근콘크리트조"),
    (("경량철골", "경철"), "경량철골조"),
    (("조립식패널", "샌드위치패널", "판넬", "패널조"), "조립식패널조"),
    (("철골", "철골조", "steel"), "철골조"),
    (("통나무",), "통나무조"), (("목구조", "중목", "경골목"), "목구조"), (("목조", "한옥"), "목조"),
    (("연와", "적벽돌", "벽돌조", "조적"), "연와조"), (("시멘트벽돌",), "시멘트벽돌조"),
    (("보강블록", "블록조", "블럭조"), "보강블록조"), (("시멘트블록",), "시멘트블록조"),
    (("석조", "돌"), "석조"), (("프리캐스트", "pc조"), "프리캐스트 콘크리트조"), (("라멘",), "라멘조"), (("alc",), "ALC조"), (("스틸하우스",), "스틸하우스조"),
    (("황토",), "황토조"), (("와이어패널",), "와이어패널조"), (("흙벽돌", "석회"), "석회 및 흙벽돌조"), (("토담", "돌담"), "돌담 및 토담조"),
    (("철파이프", "파이프"), "철파이프조"), (("컨테이너",), "컨테이너건물"),
]
_USE_SYN = [   # (표현들, 용도 라벨에 들어 있는 핵심어)
    (("사무실", "사무소", "오피스", "업무시설", "금융", "은행", "출판"), "사무소"),
    (("근린생활", "근생", "상가", "점포", "음식점", "식당", "카페", "편의점", "소매점", "미용실", "의원"), "제1종·제2종 근린생활시설"),
    (("반도체", "디스플레이", "냉동공장"), "냉동공장"), (("공장", "제조"), "기타 공장"),
    (("냉동창고", "냉장창고", "냉동·냉장"), "냉동·냉장창고"), (("창고", "물류", "하역"), "기타 창고"),
    (("지식산업센터", "아파트형공장"), "지식산업센터"), (("데이터센터", "방송국", "통신"), "방송국"),
    (("종합병원",), "종합병원"), (("병원", "요양병원", "한방병원"), "일반·치과"), (("학원", "교습소"), "학원"), (("학교", "연구소", "도서관", "교육원"), "학교"),
    (("관광호텔", "5성", "4성"), "관광호텔(5·4성급)"), (("호텔", "콘도", "펜션", "생활숙박"), "호텔(일반숙박)"), (("모텔", "여관"), "여관"), (("여인숙",), "여인숙"),
    (("백화점",), "백화점"), (("쇼핑", "대형마트", "대형점", "대규모점포"), "대형점"), (("상점", "판매"), "일반상점"), (("시장", "도매"), "도매시장"),
    (("예식장", "공연장", "집회장"), "예식장"), (("종교", "교회", "성당", "사찰"), "종교시설"), (("골프", "스키", "수영장", "볼링"), "골프장"), (("체육", "헬스"), "기타 체육시설"),
    (("주유소", "충전소", "위험물"), "주유소"), (("주차장",), "주차장(자주식"), (("세차", "정비", "차고"), "세차장"), (("축사", "도축", "작물"), "축사"), (("온실", "비닐하우스"), "온실"),
    (("장례식장",), "장례식장"), (("목욕", "찜질", "사우나"), "목욕장 1,000㎡↓"), (("유흥", "카지노"), "유흥주점"), (("단란",), "단란주점"), (("노인", "복지", "아동"), "아동·노인복지"),
    (("발전소",), "발전소"), (("원자력",), "원자력"), (("하수", "고물상", "폐기물"), "하수처리"), (("터미널", "공항", "항만"), "여객터미널"),
]
_HOUSING = ("아파트", "주택", "다세대", "연립", "다가구", "빌라", "기숙사")
_BULK = ("오피스텔",)


def _flat_use() -> dict[str, int]:
    out = {}
    for g, items in _rules()["use_index_2026"].items():
        if g.startswith("_") or g.startswith("diff") or not isinstance(items, dict):
            continue
        for k, v in items.items():
            if isinstance(v, (int, float)):
                out[k] = int(v)
    return out


def match_structure(text: str) -> tuple[str | None, int | None]:
    low = (text or "").lower().replace(" ", "")
    table = _rules()["structure_index_2026"]
    best = None
    for keys, name in _STRUCT_SYN:
        for k in keys:
            if k in low and (best is None or len(k) > len(best[0])):
                best = (k, name)
    if best is None:
        for name in table:
            if name.startswith("_"):
                continue
            if name.replace(" ", "") in low:
                best = (name, name)
    if best is None:
        return None, None
    name = best[1]
    return name, table.get(name)


def match_use(text: str) -> tuple[str | None, int | None, str | None]:
    low = (text or "").lower().replace(" ", "")
    if any(h in low for h in _HOUSING) and "오피스텔" not in low:
        return None, None, "주택(단독·공동)은 이 고시 대상이 아님 — 개별주택가격·공동주택가격(official_property_price)을 씀(상증법 제61조①4호, 소득세법 제99조①1호라목)"
    if any(b in low for b in _BULK):
        return None, None, "오피스텔(및 일괄고시 지역 상업용 건물)은 국세청이 호별 기준시가를 고시(상증법 제61조①3호, 소득세법 제99조①1호다목) — 고시가격을 쓰고, 고시 안 된 호만 이 산식"
    flat = _flat_use()
    best = None
    for keys, core in _USE_SYN:
        for k in keys:
            if k.replace(" ", "") in low and (best is None or len(k) > len(best[0])):
                best = (k, core)
    if best is None:
        for label in flat:
            toks = [t for t in re.split(r"[ ·()（）,/]", label) if len(t) >= 2 and not t[0].isdigit()]
            if any(t.replace(" ", "") in low for t in toks):
                best = (label, label); break
    if best is None:
        return None, None, None
    core = best[1]
    for label, v in flat.items():
        if core in label:
            return label, v, None
    return None, None, None


def location_index(land_price_per_m2: float) -> int:
    for lo, hi, idx in _rules()["location_index_2026"]["bands"]:
        if lo <= land_price_per_m2 < (hi if hi is not None else float("inf")):
            return idx
    return _rules()["location_index_2026"]["bands"][-1][2]


def residual_rate(structure: str, built_year: int, year: int) -> tuple[float, str, int]:
    g = _rules()["durability_group"]
    grp = next((k for k, v in g.items() if not k.startswith("_") and structure in v["structures"]), "III")
    rate = g[grp]["annual_rate"]; n = max(0, year - built_year)
    r = max(1.0 - rate * n, g[grp]["final_residual"])
    return r, grp, n


def building_standard_price(year: int, area_m2: float, structure: str, use: str, land_price_per_m2: float | None, built_year: int | None,
                            purpose: str = "양도세", floors: int | None = None, total_area_m2: float | None = None, roof: str = "",
                            floor_use: str = "", safety_grade: str = "", remodel_count: int = 0) -> dict[str, Any]:
    R = _rules(); 판단: list[dict] = []
    base = R["base_price_by_year"].get(str(year))
    if not base:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"year={year} — 2007~2026 적용연도만"], "허용값": [k for k in R["base_price_by_year"] if not k.startswith("_")]}
    sname, sidx = match_structure(structure)
    if sname is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"structure='{structure}'을(를) 고시 구조로 못 읽음"], "허용값": [k for k in R["structure_index_2026"] if not k.startswith("_")]}
    ulabel, uidx, uwarn = match_use(use)
    if uwarn:
        return {"error": "이 고시 대상 아님", "안내": uwarn, "근거": "국세청 건물 기준시가 계산방법 고시 제3조①"}
    if ulabel is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"use='{use}'을(를) 고시 용도로 못 읽음"], "허용값": list(_flat_use())[:30] + ["…(고시 제8조 61개 번호)"]}
    if land_price_per_m2 is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["land_price_per_m2(부속토지 ㎡당 개별공시지가, official_property_price 토지로 조회)가 필요 — 위치지수"], "필요 입력": {"land_price_per_m2": "원/㎡"}}
    if built_year is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["built_year(신축연도: 사용승인일 기준, 그 전 가사용·사실상 사용일이 있으면 그 연도)가 필요 — 잔가율"], "필요 입력": {"built_year": "YYYY"}}
    lidx = location_index(float(land_price_per_m2))
    rr, grp, n = residual_rate(sname, int(built_year), int(year))
    approx = year != 2026
    adj = 1.0; adj_lines = []
    if purpose in ("상증세", "상속", "증여", "상속증여"):
        A = R["adjustment_rate_2026_상증세만"]
        if sidx < 100 and roof:
            low = roof.replace(" ", "")
            if any(k in low for k in ("패널", "유리", "슬레이트")):
                adj *= 0.8; adj_lines.append("지붕 패널·유리·슬레이트 80")
            elif any(k in low for k in ("함석", "천막", "초가", "너와")):
                adj *= 0.6; adj_lines.append("지붕 함석·천막·초가·너와 60")
            else:
                adj_lines.append("지붕 슬래브·기와 등 100")
        if sname != "통나무조":
            cands = []
            if floors is not None:
                cands.append(90 if floors <= 5 else 100 if floors <= 10 else 110 if floors <= 15 else 120 if floors <= 20 else 130)
            ta = total_area_m2 if total_area_m2 is not None else area_m2
            if ta is not None:
                cands.append(90 if ta < 1000 else 100 if ta < 5000 else 110 if ta < 10000 else 120 if ta < 50000 else 130)
            if cands:
                m = max(cands); adj *= m / 100; adj_lines.append(f"규모(층수·연면적 중 큰 것) {m}")
        if floor_use:
            low = floor_use.replace(" ", "")
            fv = None
            if "지하2" in low or "지하3" in low: fv = 70
            elif "지하" in low: fv = 80
            elif "1층" in low: fv = 120
            elif "2층" in low: fv = 105
            elif any(k in low for k in ("주차장", "기계실", "보일러", "대피소", "옥탑", "부속")): fv = 60
            if fv:
                adj *= fv / 100; adj_lines.append(f"층별·부속 {fv}")
        if safety_grade:
            sv = {"B": 90, "C": 80, "D": 60, "E": 30}.get(safety_grade.strip().upper()[:1])
            if sv:
                adj *= sv / 100; adj_lines.append(f"안전진단 {safety_grade} {sv}")
        if remodel_count:
            rv = 110 if remodel_count == 1 else 120
            adj *= rv / 100; adj_lines.append(f"일부개축 {remodel_count}회 {rv}(개축 부분만 — 전체에 적용했으니 면적 비례 조정 필요)")
        판단.append({"항목": "개별건물 특성 조정률", "결론": (f"{adj:.4f} = " + " × ".join(adj_lines)) if adj_lines else "입력 없음 → 1.0 (지붕·규모·층별·안전진단·개축 자료를 주면 반영)", "근거": "고시 제11조 (상속·증여세 평가에만 적용, 항목별 곱 — 2024 해설서 기준, 확인 필요)"})
    per_m2_raw = base["amount"] * sidx / 100 * uidx / 100 * lidx / 100 * rr * adj
    per_m2 = int(per_m2_raw // 1000 * 1000)
    total = per_m2 * float(area_m2)
    판단.insert(0, {"항목": "산식", "결론": f"{base['amount']:,} × 구조 {sidx}/100 × 용도 {uidx}/100 × 위치 {lidx}/100 × 잔가율 {rr:.4f}" + (f" × 조정률 {adj:.4f}" if adj != 1.0 else "") + f" = {per_m2_raw:,.0f} → 1,000원 미만 버림 {per_m2:,}원/㎡ × {float(area_m2):,.2f}㎡ = {total:,.0f}원", "근거": "고시 제5조·제6조"})
    판단.append({"항목": "구조·용도·위치", "결론": f"구조 '{structure}' → {sname}({sidx}), 용도 '{use}' → {ulabel}({uidx}), 부속토지 공시지가 {float(land_price_per_m2):,.0f}원/㎡ → 위치지수 {lidx}", "근거": "고시 제7조·제8조·제9조"})
    판단.append({"항목": "잔가율", "결론": f"{sname}는 {grp}그룹(내용연수 {R['durability_group'][grp]['years']}년, 연 {R['durability_group'][grp]['annual_rate']}) — 경과 {n}년 → max(1 − {R['durability_group'][grp]['annual_rate']}×{n}, 0.10) = {rr:.4f}. 신축연도는 사용승인일 기준(가사용·사실상 사용이 앞서면 그 해), 증축은 증축연도", "근거": "고시 제10조"})
    if approx:
        판단.append({"항목": "확인 필요", "결론": f"{year}년 적용 신축가격기준액 {base['amount']:,}원({base.get('notice', base.get('source'))})은 그 해 고시값이지만, 구조·용도·위치지수는 2026년 표로 계산한 근사치 — {year}년 고시 지수표로 다시 확인", "근거": "고시는 매년 개정"})
    판단.append({"항목": "시가 우선·감정", "결론": "상속·증여는 평가기간 내 매매·감정·수용·경매 가액(시가)이 있으면 그것이 우선(상증법 제60조). 비주거용 건물은 국세청이 평가심의위원회를 거쳐 감정평가로 과세할 수 있어(영 제49조① 단서·제49조의2) 기준시가 신고가 뒤집힐 수 있음. 양도세는 실지거래가액이 원칙이고 이 기준시가는 환산·안분용", "근거": "상속세 및 증여세법 제60조·제61조, 소득세법 제99조·제100조"})
    판단.append({"항목": "범위", "결론": "건물 가액만(부속토지는 개별공시지가 × 면적 별도, 영업권 제외). 임대차 있으면 임대료환산가액[(연 임대료 ÷ 기재부령 율) + 보증금]과 비교해 큰 금액(상증법 제61조⑤)", "근거": "고시 제3조②, 상증법 제61조⑤"})
    return {"결과": {"기준시가_원": round(total), "㎡당_원": per_m2, "면적_㎡": float(area_m2), "적용연도": year, "구조지수": sidx, "용도지수": uidx, "위치지수": lidx, "잔가율": round(rr, 4), "조정률": round(adj, 4), "근사": approx},
            "판단": 판단, "근거": f"국세청 건물 기준시가 계산방법 고시({base.get('notice', '')}) 제5~11조; 소득세법 제99조①1호나목; 상속세 및 증여세법 제61조①2호",
            "출처": R["_meta"]["primary_source_urls"][0]}
