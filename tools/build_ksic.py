"""한국표준산업분류(KSIC) 코드표 만들기 — 통계청 고시 제2024-203호(11차, 2024.7.1. 시행) 해설서 PDF에서.

원본: 국가법령정보센터 행정규칙 「한국표준산업분류」 첨부 '한국표준산업분류 제11차 개정 해설서(신구연계표 포함).pdf'
      https://www.law.go.kr/flDownload.do?flSeq=143420091 (961쪽)
사용: python tools/build_ksic.py <해설서.pdf> → korean_tax_calc_mcp/data/ksic.json
검산: 총설 '구·신분류 단계별 분류 항목 수 비교'(11차 열)와 대분류별 중·소·세·세세분류 수가 같아야 통과(다르면 멈춤).
고시는 저작권법 제7조 보호 대상이 아님. Claude 작성(2026-11-17).
"""
import hashlib
import json
import os
import re
import subprocess
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "korean_tax_calc_mcp", "data", "ksic.json")
SRC_URL = "https://www.law.go.kr/flDownload.do?flSeq=143420091"

# 총설 표 '자. 구·신분류 단계별 분류 항목 수 비교'의 11차 열(중·소·세·세세) — 파서 검산용으로 손으로 옮김
EXPECTED_11 = {
    "A": (3, 8, 21, 33), "B": (4, 7, 10, 11), "C": (25, 85, 182, 480), "D": (1, 3, 5, 10), "E": (4, 6, 14, 19),
    "F": (2, 8, 16, 46), "G": (3, 20, 62, 186), "H": (4, 11, 19, 47), "I": (2, 4, 11, 30), "J": (6, 12, 26, 45),
    "K": (3, 8, 14, 29), "L": (1, 2, 4, 12), "M": (4, 14, 20, 50), "N": (3, 11, 22, 32), "O": (1, 6, 10, 28),
    "P": (1, 7, 17, 33), "Q": (2, 6, 9, 25), "R": (2, 4, 17, 43), "S": (3, 8, 18, 41), "T": (2, 3, 3, 3),
    "U": (1, 1, 1, 2),
}
EXPECTED_TOTAL_11 = (21, 77, 234, 501, 1205)   # 같은 표 합계 행(대·중·소·세·세세)
CODE_RE = re.compile(r"^\s*(\d{2,5})\s+(.*)$")
HANGUL = re.compile(r"[가-힣]")


def _ko(part):
    """한 줄에서 한글 이름 칸만 — 영문 칸(대문자 라틴 글자로 시작)이 나오기 전까지."""
    m = re.search(r"\s{2,}[A-Za-z(]|\s+[A-Z][a-z]|(?<=[가-힣;,])\s*[A-Z]?[a-z]{2,}", part)   # 영문 칸: 넓은 띄움 뒤 영문, 또는 대문자+소문자 단어
    s = part[:m.start()] if m else part
    return s.strip() if HANGUL.search(s) else ""


def parse_items(lines):
    items, sec, last = [], None, None
    for ln in lines:
        if re.match(r"^\s*\d+\s*$", ln) or "분류항목표" in ln:
            continue
        ms = re.match(r"^\s*([A-U])\s+([가-힣].*)$", ln)
        if ms:   # 대분류 제목 — 괄호 속 중분류 범위는 떼고, 다음 줄로 넘어간 제목은 아래에서 이어 붙임
            sec = ms.group(1)
            last = {"code": sec, "name": _ko(ms.group(2)), "level": 1, "section": sec}
            items.append(last)
            continue
        mc = CODE_RE.match(ln)
        if mc and sec and len(mc.group(1)) in (2, 3, 4, 5):
            name = _ko(mc.group(2))
            if name:
                last = {"code": mc.group(1), "name": name, "level": len(mc.group(1)), "section": sec}
                items.append(last)
                continue
        # 이름이 다음 줄로 넘어간 경우(한글 칸만 이어 붙임)
        if last is not None and ln.startswith(" "):
            cont = _ko(ln)
            if cont and not CODE_RE.match(ln):
                last["name"] = (last["name"] + " " + cont).strip()
                continue
        if not ln.strip():
            continue
    for it in items:
        it["name"] = re.sub(r"\s+", " ", it["name"]).replace(" ,", ",")
        if it["level"] == 1:
            it["name"] = re.sub(r"\s*\(\s*\d{2}\s*(?:[~～]\s*\d{2})?\s*\)\s*$", "", it["name"])
        it["level"] = {1: "대분류", 2: "중분류", 3: "소분류", 4: "세분류", 5: "세세분류"}[it["level"]]
    return items


def check(items):
    cnt = {}
    for it in items:
        if it["level"] == "대분류":
            continue
        k = ("중분류", "소분류", "세분류", "세세분류").index(it["level"])
        cnt.setdefault(it["section"], [0, 0, 0, 0])[k] += 1
    bad = {s: (tuple(cnt.get(s, [0] * 4)), e) for s, e in EXPECTED_11.items() if tuple(cnt.get(s, [0] * 4)) != e}
    lv = [sum(1 for it in items if it["level"] == L) for L in ("대분류", "중분류", "소분류", "세분류", "세세분류")]
    if tuple(lv) != EXPECTED_TOTAL_11:
        bad["합계"] = (tuple(lv), EXPECTED_TOTAL_11)
    return cnt, bad


def parse_links(lines):
    """구·신 연계표(10차 → 11차). 줄 맨 앞(들여쓰기 3칸 이하)의 5자리 = 구 코드, 같은 줄·다음 줄 가운데 칸의 5자리 = 신 코드.
    표 뒤 판권면(우편번호·ISBN)을 읽지 않도록 'ISBN'·'발행' 줄에서 멈춤."""
    links, cur = {}, None
    for ln in lines:
        if "ISBN" in ln or ln.strip().startswith("발행"):
            break
        ln = ln.replace("\uf000", " ")
        m = re.match(r"^\s{0,3}(\d{5})(?!\d)", ln)
        if m:
            cur = m.group(1)
            links.setdefault(cur, [])
            rest_from = m.end()
        else:
            rest_from = 0
        for mm in re.finditer(r"(?<!\d)(\d{5})(?!\d)", ln[rest_from:]):
            x = rest_from + mm.start()
            if 12 <= x < 60 and cur and mm.group(1) not in links[cur]:
                links[cur].append(mm.group(1))
    return links


def main(pdf):
    txt = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout.splitlines()
    start = next(i for i, l in enumerate(txt) if l.strip() == "분류항목표" and i > 500)
    end = next(i for i, l in enumerate(txt) if l.strip().startswith("Ⅲ 분류항목 명칭 및 내용 설명"))
    items = parse_items(txt[start:end])
    cnt, bad = check(items)
    if bad:
        for s, (got, exp) in sorted(bad.items()):
            print(f"검산 불일치 {s}: 뽑음 {got} / 고시 {exp}", file=sys.stderr)
        sys.exit(1)
    g0 = next(i for i, l in enumerate(txt) if l.strip() == "구ㆍ신 연계표" and i > end)
    links = parse_links(txt[g0:])
    codes11 = {it["code"] for it in items if it["level"] == "세세분류"}
    news = {c for v in links.values() for c in v}
    if len(links) != 1196 or news != codes11 or any(not v for v in links.values()):
        print(f"연계표 검산 불일치: 구 {len(links)}(고시 1,196) / 신 {len(news)}(11차 세세분류 {len(codes11)}와 같아야)", file=sys.stderr)
        sys.exit(1)
    changed = {o: n for o, n in sorted(links.items()) if n != [o]}
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    data = {"source": {"고시": "통계청 고시 제2024-203호 한국표준산업분류(제11차 개정)", "시행일": "2024-07-01",
                       "문서": "한국표준산업분류 제11차 개정 해설서(신구연계표 포함).pdf", "url": SRC_URL, "sha256": sha,
                       "검산": "총설 '구·신분류 단계별 분류 항목 수 비교' 11차 열과 대분류별 항목 수 일치"},
            "version": "11", "items": items,
            "links_10_to_11": {"설명": "10차 세세분류 코드 → 11차 코드(구·신 연계표). 같은 코드·같은 범위인 코드는 생략 — 여기 없으면 10차와 11차 코드가 같음",
                               "changed": changed}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"연계표: 10차 {len(links)}개 중 바뀐 코드 {len(changed)}개")
    print(f"항목 {len(items)}개 → {os.path.relpath(OUT)} (검산 통과: {len(EXPECTED_11)}개 대분류)")


if __name__ == "__main__":
    main(sys.argv[1])
