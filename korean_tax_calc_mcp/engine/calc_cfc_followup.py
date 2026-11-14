"""특정외국법인 배당간주 후속 처리 — 실제 배당 때 익금불산입, 주식 양도 때 익금불산입. Claude 작성(2026-11-14).

대조한 원문(국세법령정보시스템 연혁본 — 법제처 Open API 점검 중이라 이쪽으로 받음):
- 국제조세조정에 관한 법률 2016.1.1.·2019.1.1. 시행본 제19조·제20조, 2020.1.1. 시행본 제19조의2·제20조, 2021.1.1.·현행 제32조·제33조
- 시행령 2016.2.5. 시행본 제36조의6, 2020.2.11. 시행본 제35조, 현행 제68조
- 법인세법 제18조의4(2023.1.1. 시행본·현행) ③④

문언 요지(세 시기 효과 같음):
- 실제 배당: 배당간주금액이 익금에 산입된 뒤 그 유보소득을 실제로 배당하면 법인세법 제18조제2호의 이월익금(2019까지 문언)·
  익금에 산입하지 아니하는 소득(2020부터)으로 본다. 배당 가능한 유보소득이 발생한 순서대로 배당한 것으로 본다(영 제36조의6①·제35조①·제68조①).
- 중간외국법인 경유: 한도 = Σ(특정외국법인이 중간외국법인에 실제 배당한 금액 × 그 당시 내국인의 중간외국법인 보유비율) − 과거에 이미 익금불산입한 금액
  (영 제36조의6②·제35조②. 현행 제68조②는 같은 문언이고 계산식이 그림이라 2020 시행본의 글자 계산식을 씀).
- 주식 양도: (양도한 주식에 대한 배당간주금액 합계 − 그 주식에 실제로 배당한 금액), 0 이하는 0, 양도차익 한도
  (2016~2019 제20조② 후단 "초과하는 금액은 없는 것으로 본다", 2020 제19조의2②·현행 제32조② "양도차익을 한도로").
- 법인세법 제18조의4③(2023.1.1. 시행): 배당간주금액과 그 유보소득의 실제 배당 수입배당금액에는 외국자회사 수입배당금 95% 익금불산입을 적용하지 않음.
"""
from fractions import Fraction

from .exact import trunc_won as _trunc_won


def _basis(year):
    if year <= 2019:
        return {"배당": "구 국제조세조정에 관한 법률 제20조①(법인세법 제18조제2호의 이월익금으로 봄), 구 시행령 제36조의6①",
                "중간": "구 시행령 제36조의6②③", "양도": "구 국제조세조정에 관한 법률 제20조②(양도차익 초과분은 없는 것으로 봄)",
                "외납": "구 법 제19조②④(실제 배당 과세연도 신고기한부터 1년 이내 경정청구 '할 수 있다'), 구 시행령 제36조의5"}
    if year == 2020:
        return {"배당": "구 국제조세조정에 관한 법률 제19조의2①(법인세법 제18조제2호에 따라 익금에 산입하지 아니하는 소득으로 봄), 구 시행령 제35조①",
                "중간": "구 시행령 제35조②③", "양도": "구 국제조세조정에 관한 법률 제19조의2②(양도차익 한도)",
                "외납": "구 법 제20조①②(1년 이내 경정청구 '할 수 있다'), 구 시행령 제36조"}
    return {"배당": "국제조세조정에 관한 법률 제32조①(법인세법 제18조제2호에 따라 익금에 산입하지 아니하는 소득으로 봄), 시행령 제68조①",
            "중간": "시행령 제68조②③(계산식은 2020.2.11. 시행본 제35조②의 글자 계산식과 같은 문언으로 봄)",
            "양도": "국제조세조정에 관한 법률 제32조②(양도차익 한도)",
            "외납": "법 제33조①②(1년 이내 경정청구 '하여야 한다'), 시행령 제69조"}


def _int(x, name, 문제, allow_none=False):
    if x is None and allow_none:
        return None
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0:
        문제.append(f"{name} — 0 이상의 금액(원)")
        return None
    return int(x)


def actual_dividend(year, actual_dividend, ledger, intermediate=None, entity="법인", cfc_name=None):
    """year = 실제 배당을 받은 과세연도. ledger = [{year: 배당간주 사업연도(익금 귀속), amount: 배당간주금액, used: 이미 실제 배당으로 소진한 금액}]."""
    문제 = []
    if not isinstance(year, int) or not (2016 <= year <= 2026):
        문제.append("year — 실제 배당을 받은 과세연도(2016~2026)")
    d = _int(actual_dividend, "actual_dividend", 문제)
    if entity not in ("법인", "개인"):
        문제.append("entity — '법인' 또는 '개인'")
    rows = []
    if not isinstance(ledger, list) or not ledger:
        문제.append("ledger — 이미 익금에 넣은 배당간주금액 목록 [{year, amount, used}] (cfc_deemed_dividend 결과의 배당간주금액·익금귀속_과세연도)")
    else:
        for i, r in enumerate(ledger):
            if not isinstance(r, dict) or not isinstance(r.get("year"), int):
                문제.append(f"ledger[{i}] — {{year, amount, used}}"); continue
            a = _int(r.get("amount"), f"ledger[{i}].amount", 문제)
            u = _int(r.get("used", 0) or 0, f"ledger[{i}].used", 문제)
            if a is not None and u is not None:
                if u > a:
                    문제.append(f"ledger[{i}] — used({u:,})가 amount({a:,})보다 큼")
                rows.append({"year": r["year"], "amount": a, "used": u})
    lim_mid = None
    if intermediate is not None:
        if not isinstance(intermediate, dict) or not isinstance(intermediate.get("cfc_to_intermediate"), list):
            문제.append("intermediate — {cfc_to_intermediate: [{amount: 특정외국법인→중간외국법인 실제 배당액, ratio: 그 당시 내국인의 중간외국법인 보유비율}], prior_excluded: 과거 익금불산입액}")
        else:
            s = Fraction(0)
            for i, x in enumerate(intermediate["cfc_to_intermediate"]):
                a = _int(x.get("amount") if isinstance(x, dict) else None, f"cfc_to_intermediate[{i}].amount", 문제)
                try:
                    rt = Fraction(str(x.get("ratio")))
                    if not (0 <= rt <= 1):
                        raise ValueError
                except (ValueError, TypeError, ArithmeticError):
                    문제.append(f"cfc_to_intermediate[{i}].ratio — 0~1 사이 비율"); continue
                if a is not None:
                    s += a * rt
            prior = _int(intermediate.get("prior_excluded", 0) or 0, "prior_excluded", 문제)
            if prior is not None:
                lim_mid = max(0, _trunc_won(s) - prior)
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    b = _basis(year)
    rows.sort(key=lambda r: r["year"])
    남은 = sum(r["amount"] - r["used"] for r in rows)
    대상 = min(d, 남은)
    if lim_mid is not None:
        대상 = min(대상, lim_mid)
    소진, rest = [], 대상
    for r in rows:
        take = min(rest, r["amount"] - r["used"])
        if take:
            소진.append({"배당간주_사업연도": r["year"], "소진": take, "소진후_남은": r["amount"] - r["used"] - take})
            rest -= take
    원장 = [{"year": r["year"], "amount": r["amount"], "used": r["used"] + next((s["소진"] for s in 소진 if s["배당간주_사업연도"] == r["year"]), 0)} for r in rows]
    일반배당 = d - 대상
    표현 = "이월익금" if year <= 2019 else "익금에 산입하지 아니하는 소득"
    판단 = [{"항목": "실제 배당", "결론": f"실제 배당 {d:,}원 중 {대상:,}원은 이미 배당간주로 과세된 유보소득에서 나온 것 — {표현}으로 봄"
                                      + ("(개인은 배당소득에 해당하지 않음)" if entity == "개인" else ""), "근거": b["배당"]},
           {"항목": "배당 순서", "결론": "배당 가능한 유보소득이 발생한 순서대로 배당한 것으로 봄 — 오래된 배당간주분부터 소진", "근거": b["배당"].split(", ")[-1]}]
    if lim_mid is not None:
        판단.append({"항목": "중간외국법인 한도", "결론": f"한도 {lim_mid:,}원 = Σ(특정외국법인→중간외국법인 실제 배당 × 당시 보유비율) − 과거 익금불산입액", "근거": b["중간"]})
    if 일반배당:
        if year >= 2023 and entity == "법인":
            판단.append({"항목": "나머지 배당", "결론": f"나머지 {일반배당:,}원은 이번 익금불산입 대상이 아님. 배당간주로 과세된 유보소득에서 나온 부분이 아니라면 일반 수입배당금 — "
                                                  "다만 국제조세조정에 관한 법률 제27조제1항 각 호의 요건을 모두 갖춘 특정외국법인에서 받은 배당 중 대통령령으로 정하는 것은 법인세법 제18조의4④1호로 익금산입, "
                                                  "배당간주 대상 유보소득의 실제 배당분은 제18조의4③로 95% 익금불산입을 적용하지 않음", "근거": "법인세법 제18조의4③④"})
        else:
            판단.append({"항목": "나머지 배당", "결론": f"나머지 {일반배당:,}원은 이번 익금불산입 대상이 아님 — 일반 수입배당금으로 과세(외국납부세액공제 등은 따로)", "근거": "법인세법 제15조"})
    결과 = {"실제배당액": d, "배당간주_미소진_합계": 남은, "익금불산입": 대상, "일반배당": 일반배당, "중간외국법인_한도": lim_mid,
          "소진_내역": 소진, "원장_갱신": 원장, "세무조정": []}
    if 대상 and entity == "법인":
        결과["세무조정"].append({"구분": f"특정외국법인 배당간주금액 실제 배당{f'({cfc_name})' if cfc_name else ''}", "조정": "익금불산입", "금액": 대상,
                             "소득처분": "△유보", "근거": b["배당"]})
    주의 = ["세무조정의 △유보는 배당간주 때 둔 유보를 줄이는 처리(법인세법 시행령 제106조①2호의 유보를 되돌림) — 이 처분을 직접 다룬 해석례는 찾지 못함",
          "실제 배당 원화 금액은 손익 귀속시기의 환율로 환산(서면2팀-2665, 2006.12.27.). 배당간주 때 원화 금액과 다른 환산 차이의 처리는 판정하지 않음",
          "실제 배당 때 외국에 낸 원천세는 배당간주금액을 익금에 넣은 과세연도의 외국납부세액으로 보아 경정청구(" + b["외납"] + ")"]
    return {"결과": 결과, "판단": 판단, "근거": b["배당"] + (", " + b["중간"] if lim_mid is not None else ""), "주의": 주의}


def share_disposal(year, deemed_total, actual_paid, gain, entity="법인", sold_ratio=None, cfc_name=None):
    """양도한 주식에 대한 배당간주금액 합계(deemed_total)와 그 주식에 실제로 배당한 금액(actual_paid), 양도차익(gain, 음수면 차손)."""
    문제 = []
    if not isinstance(year, int) or not (2016 <= year <= 2026):
        문제.append("year — 양도한 과세연도(2016~2026)")
    dt = _int(deemed_total, "deemed_total", 문제)
    ap = _int(actual_paid, "actual_paid", 문제)
    if isinstance(gain, bool) or not isinstance(gain, (int, float)):
        문제.append("gain — 양도차익(원, 차손이면 음수)")
    if entity not in ("법인", "개인"):
        문제.append("entity — '법인' 또는 '개인'")
    r = None
    if sold_ratio is not None:
        try:
            r = Fraction(str(sold_ratio))
            if not (0 < r <= 1):
                raise ValueError
        except (ValueError, TypeError, ArithmeticError):
            문제.append("sold_ratio — 보유 주식 중 양도한 비율(0 초과 1 이하)")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    b = _basis(year)
    단계 = []
    if r is not None and r != 1:
        dt, ap = _trunc_won(dt * r), _trunc_won(ap * r)
        단계.append(f"일부 양도: 배당간주금액·실제 배당액을 양도 비율 {float(r):.4%}로 나눔(조문은 '양도한 주식에 대한' 금액 — 비율 안분은 이 도구의 가정)")
    차 = max(0, dt - ap)
    한도 = max(0, int(gain))
    금액 = min(차, 한도)
    단계.append(f"(양도한 주식에 대한 배당간주금액 {dt:,} − 그 주식에 실제로 배당한 금액 {ap:,}) = {차:,}, 양도차익 {int(gain):,} 한도 → {금액:,}")
    표현 = "이월익금" if year <= 2019 else "익금에 산입하지 아니하는 소득"
    결과 = {"익금불산입": 금액 if entity == "법인" else 0, "양도소득_제외": 금액 if entity == "개인" else 0, "계산전_금액": 차, "양도차익_한도": 한도, "세무조정": []}
    if 금액 and entity == "법인":
        결과["세무조정"].append({"구분": f"특정외국법인 주식 양도 — 배당간주 미배당분{f'({cfc_name})' if cfc_name else ''}", "조정": "익금불산입", "금액": 금액,
                             "소득처분": "△유보", "근거": b["양도"]})
    판단 = [{"항목": "주식 양도", "결론": (f"{금액:,}원을 {표현}으로 봄" if entity == "법인" else
                                       f"{금액:,}원은 양도소득에 해당하지 않는 것으로 봄(" + ("구 소득세법 제118조의2제3호" if year <= 2019 else "소득세법 제94조①3호다목") + ")"),
           "근거": b["양도"]}]
    if 차 > 한도:
        판단.append({"항목": "양도차익 한도", "결론": f"계산 금액 {차:,}원이 양도차익 {한도:,}원을 넘어 넘는 부분은 없는 것으로 봄", "근거": b["양도"]})
    주의 = ["양도한 주식분의 배당간주 유보 잔액 중 익금불산입하지 못한 부분(양도차익 한도 초과분)의 처리는 판정하지 않음",
          "세무조정의 △유보는 배당간주 때 둔 유보를 줄이는 처리 — 이 처분을 직접 다룬 해석례는 찾지 못함"]
    return {"결과": 결과, "판단": 판단, "단계별_계산": 단계, "근거": b["양도"], "주의": 주의}
