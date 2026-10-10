"""법제처 국가법령정보 공동활용(DRF) — 시점별 조문 원문 조회.

인증키(OC)는 사용자 본인 것: https://open.law.go.kr 에서 무료 신청 후 환경변수 LAW_OC.
제3자 서버로 키를 전송하지 않으며, 오류 메시지의 OC 값은 OC=***로 가린다.
"""
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from functools import lru_cache

DRF = "https://www.law.go.kr/DRF"
CTX = ssl.create_default_context()  # 기본 TLS 검증 유지


def _mask_oc(msg):
    """오류 메시지 내 OC 값을 OC=***로 가린다."""
    return re.sub(r"OC=[^&\s\"]+", "OC=***", msg)


class NoKey(RuntimeError):
    pass


def _oc():
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        raise NoKey("법제처 OC 키가 없습니다 — https://open.law.go.kr 에서 무료 신청 후 환경변수 LAW_OC로 설정")
    return oc


def _get(path, query):
    """법제처 DRF API 호출. 타임아웃 20초."""
    u = f"{DRF}/{path}?OC={_oc()}&type=JSON&{query}"
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "korean-tax-audit-mcp"}),
                                    context=CTX, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        raise RuntimeError(_mask_oc(str(e))) from e


def _list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def jo6(article):
    """'제52조' → '005200', '제28조의2' → '002802'."""
    m = re.fullmatch(r"제?(\d+)조(?:의(\d+))?", (article or "").strip())
    if not m:
        raise ValueError("조문은 '제52조' 형식")
    return f"{int(m.group(1)):04d}{int(m.group(2) or 0):02d}"


@lru_cache(maxsize=128)
def _versions(law):
    d = _get("lawSearch.do", "target=eflaw&display=100&query=" + urllib.parse.quote(law))
    return [v for v in _list(d.get("LawSearch", {}).get("law")) if v.get("법령명한글") == law]


def version(law, as_of=""):
    """기준일(YYYYMMDD, 없으면 오늘)에 시행 중이던 연혁본 → (MST, 시행일자)."""
    import time
    day = as_of or time.strftime("%Y%m%d")
    vs = [v for v in _versions(law) if v.get("시행일자", "99999999") <= day]
    if not vs:
        return None, None
    v = max(vs, key=lambda x: x["시행일자"])
    return v["법령일련번호"], v["시행일자"]


def _texts(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k.endswith("내용") and k != "개정문내용" and isinstance(v, str):
                yield v
            elif isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                yield "\n".join(v)
            elif isinstance(v, list) and v and all(isinstance(x, list) for x in v):
                for row in v:
                    yield "\n".join(x for x in row if isinstance(x, str))
            else:
                yield from _texts(v)
    elif isinstance(o, list):
        for v in o:
            yield from _texts(v)


def article(law, article_no, as_of=""):
    """조문 본문(문자열). as_of(YYYYMMDD)를 주면 그날 시행 중이던 버전.
    기준일 시행본 조문 원문을 반환한다."""
    mst, ef = version(law, as_of)
    if not mst:
        return ""
    d = _get("lawService.do", f"target=eflaw&MST={mst}&efYd={ef}&JO={jo6(article_no)}")
    body = "\n".join(t.strip() for t in _texts(d.get("법령", d)) if t.strip())
    return body or "조문 없음 — 조번호 확인"
