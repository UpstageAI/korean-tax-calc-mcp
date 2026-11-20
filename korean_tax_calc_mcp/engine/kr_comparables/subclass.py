"""등록 업종 코드가 입력보다 짧은 후보의 세분류 가르기 — 한국표준산업분류(KSIC) 형제 항목 중 주된 사업이 어디에 드는지.

왜: OpenDART 기업개황의 업종 코드는 회사마다 자릿수가 다르다(상장사는 3자리가 많음). 입력이 '2042'인데 등록이 '204'면
같은 소분류의 다른 세분류 회사도 들어온다. 낱말 일치(short_code_keywords)는 낱말이 넓으면 가르지 못한다.

어떻게: 등록 코드 아래의 KSIC 항목(입력과 같은 자릿수)을 선택지로 놓고, 이미 뽑아 둔 사업 설명·매출 행 이름(비중)만
Solar에 보내 하나를 고르게 한다. 근거 인용이 보낸 글에 글자 그대로 있는지 기계로 확인하고, 없으면 판정을 버린다.
- '입력 세분류' = 고른 항목이 입력 코드에 듦 → 후보 유지
- '다른 세분류' = 고른 항목이 입력 코드 밖 → 후보에서 빼고 목록에 남김(사람이 되살릴 수 있음)
- '확인 필요' = 키 없음·설명 없음·모델이 못 가름·하위 항목 어디에도 안 듦·인용 불일치·호출 실패 → 빼지 않고 표시만(추정으로 넣거나 빼지 않음)
분류표는 통계 분류(통계청 고시)이고 세법 판정 기준이 아니다. 다수결 없음, temperature 0, 같은 입력은 캐시에서 같은 답. Claude 작성(2026-11-20).
"""
import json
import re

from . import ksic as KS
from .revenue_mix import SOLAR_MODEL, solar_cached

IN, OTHER, UNSURE = "입력 세분류", "다른 세분류", "확인 필요"
QUOTE_MIN = 8          # 확인된 인용 조각의 최소 길이(공백 뺀 글자 수) — 이보다 짧으면 근거로 보지 않음
DESC_MAX, ROWS_MAX = 1500, 12

PROMPT = """다음은 한국 회사 공시에서 옮긴 사업 설명과 매출 행(이름·매출 비중)이다. 이 회사의 주된 사업(매출 비중이 가장 큰 사업)이 아래 한국표준산업분류 항목 중 어디에 드는지 하나만 골라라.
- 사업 설명과 매출 행에 적힌 내용만 근거로 삼는다. 회사 이름이나 일반 지식으로 짐작하지 않는다.
- 적힌 내용만으로 가를 수 없으면 code에 "불명"을 적는다. 주된 사업이 아래 항목 어디에도 들지 않으면 "해당없음"을 적는다.
- quote에는 근거가 된 부분을 사업 설명 또는 매출 행 이름에서 글자 그대로 옮겨 적는다(한 문장 또는 행 이름 하나, 고치거나 줄이지 않는다. 비중 숫자는 붙이지 않는다).
JSON만 출력: {"code":"항목 코드 | 불명 | 해당없음","quote":"원문 그대로","reason":"30자 이내"}
항목(괄호 안은 그 항목에 드는 하위 분류):
{options}
사업 설명: {desc}
매출 행:
{rows}
"""


def _norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def verified_quote(quote, sources):
    """인용 가운데 보낸 글에 글자 그대로(공백만 무시) 있는 조각만 남긴다 — 문장·줄·표 칸 단위. 하나도 없으면 None."""
    quote = re.sub(r"\s*\(\s*\d+\s*%\s*\)\s*$", "", str(quote or "").strip())
    src = [_norm(x) for x in sources]
    whole = _norm(quote)
    if len(whole) >= QUOTE_MIN and any(whole in x for x in src):
        return quote
    keep = [pc.strip() for pc in re.split(r"(?<=[.다])\s+|\n+|\s\|\s", quote)
            if len(_norm(pc)) >= QUOTE_MIN and any(_norm(pc) in x for x in src)]
    return " … ".join(keep) if keep else None


def options(registered, prefixes):
    """선택지 — 등록 코드 아래 KSIC 항목 중, 등록 코드에 드는 입력 코드들 가운데 가장 짧은 것과 같은 자릿수."""
    rel = [p for p in prefixes if p.startswith(registered) and len(p) > len(registered)]
    if not rel:
        return [], rel
    n = min(len(p) for p in rel)
    opts = [k for k in KS.children(registered) if len(k["code"]) == n]
    for o in opts:
        o["하위"] = [k["name"] for k in KS.children(o["code"]) if len(k["code"]) == len(o["code"]) + 1][:12]
    return opts, rel


def evidence_text(prof):
    """판정에 보내는 글 — 사업 설명(앞 1,500자)과 매출 행 이름·비중(금액은 보내지 않음)."""
    desc = str((prof.get("business_desc") or {}).get("value") or "")[:DESC_MAX]
    rows = [r for r in (((prof.get("mix_coverage") or {}).get("evidence") or {}).get("rows") or [])
            if isinstance(r.get("amount"), (int, float)) and r["amount"] > 0 and r.get("label")]
    tot = sum(r["amount"] for r in rows)
    rows = sorted(rows, key=lambda r: -r["amount"])[:ROWS_MAX]
    labels = [(str(r["label"]), round(100 * r["amount"] / tot) if tot else None) for r in rows]
    return desc, labels


def judge(prof, registered, prefixes, key, http=None, stat=None):
    """반환 {'판정': IN|OTHER|UNSURE, '세분류': {code,name}|None, '근거_문장': str|None, '사유': str}."""
    opts, rel = options(registered, prefixes)
    if not opts:
        return {"판정": UNSURE, "세분류": None, "근거_문장": None, "사유": "분류표에 등록 코드의 하위 항목이 없음"}
    desc, labels = evidence_text(prof)
    if not _norm(desc) and not labels:
        return {"판정": UNSURE, "세분류": None, "근거_문장": None, "사유": "사업 설명·매출 행을 못 찾음"}
    if not key:
        return {"판정": UNSURE, "세분류": None, "근거_문장": None, "사유": "UPSTAGE_API_KEY 없음 — 세분류를 가르지 않음"}
    opt_txt = "\n".join(f"{o['code']} {o['name']}" + (f" ({', '.join(o['하위'])})" if o["하위"] else "") for o in opts)
    row_txt = "\n".join(f"- {l}" + (f" ({s}%)" if s is not None else "") for l, s in labels) or "(없음)"
    body = {"model": SOLAR_MODEL, "temperature": 0,
            "messages": [{"role": "user", "content": PROMPT.replace("{options}", opt_txt).replace("{desc}", desc or "(없음)").replace("{rows}", row_txt)}]}
    d = solar_cached(body, key, http, stat)
    if d is None:
        return {"판정": UNSURE, "세분류": None, "근거_문장": None, "사유": "Solar 호출 실패"}
    try:
        j = json.loads(re.search(r"\{.*\}", d["choices"][0]["message"]["content"], re.S).group(0))
    except Exception:
        return {"판정": UNSURE, "세분류": None, "근거_문장": None, "사유": "Solar 답을 읽지 못함"}
    code, raw_quote = str(j.get("code") or "").strip(), str(j.get("quote") or "").strip()
    by = {o["code"]: o for o in opts}
    if code not in by:
        why = "주된 사업이 등록 코드의 하위 항목 어디에도 들지 않는다고 답함 — 등록 코드와 사업 설명이 어긋남" if code == "해당없음" else "적힌 내용만으로 가를 수 없음"
        return {"판정": UNSURE, "세분류": None, "근거_문장": None, "사유": why + "(모델 답: " + (code[:20] or "없음") + ")"}
    pick = {"code": code, "name": by[code]["name"]}
    quote = verified_quote(raw_quote, [desc] + [l for l, _ in labels])
    if not quote:
        return {"판정": UNSURE, "세분류": pick, "근거_문장": None, "사유": "근거 인용이 보낸 글에 그대로 없음 — 판정을 쓰지 않음", "확인_안_된_인용": raw_quote[:120]}
    if any(code.startswith(p) for p in rel):
        return {"판정": IN, "세분류": pick, "근거_문장": quote, "사유": (j.get("reason") or "")[:60]}
    if any(p.startswith(code) for p in rel):
        return {"판정": UNSURE, "세분류": pick, "근거_문장": quote, "사유": "입력 코드가 판정한 항목보다 더 세분됨 — 그 아래 어느 분류인지 확인 필요"}
    return {"판정": OTHER, "세분류": pick, "근거_문장": quote, "사유": (j.get("reason") or "")[:60]}
