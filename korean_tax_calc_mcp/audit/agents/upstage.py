"""Upstage 호출: Solar Pro 4(추론), Document Parse(문서→텍스트), Studio 에이전트(v2/responses). 작성 Mia(윤승미)

패키지(korean-tax-audit-mcp)에서는 .env 자동 읽기를 하지 않는다 — 환경변수(UPSTAGE_API_KEY)만 읽는다.
"""
import json, os, ssl, time, uuid, urllib.request
from pathlib import Path

CTX = ssl.create_default_context()  # 기본 TLS 검증 유지
BASE = "https://api.upstage.ai"


def _key():
    k = os.environ.get("UPSTAGE_API_KEY")
    if not k: raise RuntimeError("UPSTAGE_API_KEY 환경변수가 설정되지 않았습니다 (console.upstage.ai)")
    return k


def _req(method, url, body=None, headers=None, timeout=120, raw=None):
    h = {"Authorization": "Bearer " + _key()}
    if body is not None: h["Content-Type"] = "application/json"; raw = json.dumps(body).encode()
    h.update(headers or {})
    r = urllib.request.Request(url, method=method, headers=h, data=raw)
    with urllib.request.urlopen(r, context=CTX, timeout=timeout) as res:
        return json.loads(res.read())


def chat(prompt, system=None, max_tokens=2000, model="solar-pro4", json_mode=False):
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens, "messages": msgs}
    if json_mode: body["response_format"] = {"type": "json_object"}
    for i in range(3):
        try:
            return _req("POST", BASE + "/v1/chat/completions", body)["choices"][0]["message"]["content"].strip()
        except Exception:
            if i == 2: raise
            time.sleep(2 * (i + 1))


def repair_json(t):
    """끊기거나 조금 틀린 JSON을 마지막 완결 지점까지 살린다."""
    t = t[t.find("{"):] if "{" in t else t
    try: return json.loads(t)
    except Exception: pass
    for cut in range(len(t), 0, -1):
        if t[cut - 1] not in "}]\"0123456789el": continue
        s = t[:cut]; stack, q, esc = [], False, False
        for ch in s:
            if q:
                esc = (ch == "\\" and not esc)
                if ch == '"' and not esc: q = False
                continue
            if ch == '"': q = True
            elif ch in "{[": stack.append("}" if ch == "{" else "]")
            elif ch in "}]" and stack: stack.pop()
        if q: continue
        try: return json.loads(s.rstrip(", \n") + "".join(reversed(stack)))
        except Exception: continue
    raise ValueError("JSON 복구 실패")


def chat_json(prompt, system=None, max_tokens=2000):
    t = chat(prompt + "\n\n출력은 들여쓰기 없는 한 줄 JSON.", system, max_tokens, json_mode=True)
    try: return json.loads(t)
    except Exception: return repair_json(t)


def _multipart(fields, files):
    b = uuid.uuid4().hex; out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, p in files.items():
        p = Path(p)
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{p.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + p.read_bytes() + b"\r\n"
    return out + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def parse(path):
    """Document Parse로 PDF·이미지·오피스 문서를 마크다운 텍스트로.

    UPSTAGE_API_KEY가 필요하다(console.upstage.ai에서 발급). 결과는 '사람 확인 필요'.
    """
    raw, ct = _multipart({"model": "document-parse", "output_formats": '["markdown"]', "ocr": "auto"}, {"document": path})
    d = _req("POST", BASE + "/v1/document-digitization", headers={"Content-Type": ct}, raw=raw, timeout=300)
    return d.get("content", {}).get("markdown") or d.get("content", {}).get("text", "")


def extract_text_local(path, max_chars=20000):
    """pypdf로 PDF에서 텍스트를 로컬 추출한다(key 없이 host_ai 모드에서 사용).

    추출 텍스트는 max_chars(기본 20,000자)로 자른다. 스캔 이미지 PDF 등 텍스트가
    거의 없는 경우 빈 문자열 또는 극소량만 반환한다 — 이 경우 호출 측에서 스캔 PDF
    안내를 내보낸다.
    """
    from pypdf import PdfReader
    raw_chars = []
    try:
        reader = PdfReader(path)
        for page in reader.pages:
            t = page.extract_text()
            if t: raw_chars.append(t)
    except Exception:
        return ""
    joined = "\n".join(raw_chars)
    return joined if len(joined) <= max_chars else joined[:max_chars]
