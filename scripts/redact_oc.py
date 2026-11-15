#!/usr/bin/env python3
"""원자료를 저장하기 전에 법제처 OC 키를 가리는 필터(표준 라이브러리만 사용).

법제처 DRF 응답에는 요청 주소가 링크로 되돌아와 OC=<키>가 들어 있다. 저장하기 전에 반드시 이 필터를 거친다.

    curl -s "$URL" | python scripts/redact_oc.py > raw/law_xxx.json     # 주소는 변수로만 — echo·set -x 금지
    python scripts/redact_oc.py raw/a.json raw/b.json                    # 이미 받은 파일을 제자리에서 가림

파이썬에서는: from scripts.redact_oc import redact; path.write_text(redact(text))
환경변수 LAW_OC가 있으면(4자 이상) 그 값이 OC= 없이 홀로 적힌 곳도 가린다.
"""
import os
import re
import sys

# OC=, oc=, LAW_OC=, 그리고 = 의 URL 인코딩(%3D)·JSON 이스케이프(=) 뒤의 값
_OC_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(OC(?:=|%3D|\\u003d))(?!\*{3})[^&\s\"'<>\\#;,)\]}|`]+")
# 설정 JSON 꼴 "LAW_OC": "<값>"
_ENV_JSON_RE = re.compile(r"(\"LAW_OC\"\s*:\s*\")[^\"]+(\")")


def redact(text: str, secret: str = "") -> str:
    """text 안의 OC 값을 ***로 바꾼다. secret(기본: 환경변수 LAW_OC)이 4자 이상이면 그 문자열 자체도 가린다."""
    text = _OC_RE.sub(r"\1***", text)
    text = _ENV_JSON_RE.sub(r"\1***\2", text)
    secret = secret or os.environ.get("LAW_OC", "").strip()
    if len(secret) >= 4: text = text.replace(secret, "***")
    return text


def main(argv):
    if not argv:
        sys.stdout.write(redact(sys.stdin.read()))
        return 0
    for name in argv:
        with open(name, encoding="utf-8") as f: before = f.read()
        after = redact(before)
        if after != before:
            with open(name, "w", encoding="utf-8") as f: f.write(after)
        print(f"{name}: {'가림' if after != before else '변경 없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
