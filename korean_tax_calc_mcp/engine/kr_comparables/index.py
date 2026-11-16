"""회사 색인 — 기업개황(회사코드 → 업종코드·결산월·법인구분)을 캐시 폴더에 영구 파일로 쌓는다. Claude 작성(2026-11-17).

- 파일: <캐시 폴더>/corp_index_v1.json  {version, created, updated, corps: {회사코드: {n 회사명, i 업종코드, a 결산월, c 법인구분, d 확인일}},
  days: {YYYYMMDD: [그날 외부감사 공시(감사보고서)를 낸 비상장 회사코드…]}}
- 비상장 모집단: 공시검색(list.json)을 하루 단위로 쪼개 그날 모든 쪽을 넘긴다 — 한 기간에 50쪽(5,000건)이 넘어도 빠지는 회사가 없다.
  하루를 끝까지 받은 날만 days에 적으므로, 중간에 멈추면 다음 실행이 그날부터 다시 받는다(받은 쪽은 캐시).
- 다음 실행부터는 색인으로 업종을 먼저 걸러 업종이 맞는 회사만 재무를 부른다.
"""
import datetime as _dt
import json
import os

from .dart import cache_dir

VERSION = 1
MAX_WINDOW_DAYS = 92
MAX_PAGES_PER_DAY = 300


class CorpIndex:
    def __init__(self, path=None):
        self.path = path or os.path.join(cache_dir(), f"corp_index_v{VERSION}.json")
        self.data = {"version": VERSION, "created": _dt.date.today().isoformat(), "updated": None, "corps": {}, "days": {}}
        if os.path.exists(self.path):
            try:
                d = json.load(open(self.path, encoding="utf-8"))
                if d.get("version") == VERSION:
                    self.data = d
            except (OSError, ValueError):
                pass
        self._dirty = 0
        self._names = {}            # 공시 목록에서 본 회사명(기업개황 전)

    # 회사
    def get(self, code):
        return self.data["corps"].get(code)

    def put(self, code, info):
        self.data["corps"][code] = {"n": info.get("corp_name", ""), "i": info.get("induty_code", ""), "a": info.get("acc_mt", ""),
                                    "c": info.get("corp_cls", ""), "d": _dt.date.today().isoformat()}
        self._dirty += 1
        if self._dirty >= 50:
            self.save()

    def save(self):
        self.data["updated"] = _dt.datetime.now().isoformat(timespec="seconds")
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
        os.replace(tmp, self.path)
        self._dirty = 0

    # 비상장 모집단
    def pool(self, dc, bgn, end):
        """bgn~end(YYYYMMDD)에 감사보고서를 낸 비상장(기타법인 E) 회사 [{corp_code, corp_name, stock_code: ''}] — 하루씩, 그날 모든 쪽."""
        d0, d1 = _dt.datetime.strptime(bgn, "%Y%m%d").date(), _dt.datetime.strptime(end, "%Y%m%d").date()
        if d1 < d0 or (d1 - d0).days >= MAX_WINDOW_DAYS:
            raise ValueError(f"unlisted_window는 시작 ≤ 끝, {MAX_WINDOW_DAYS}일 이내")
        seen, out = set(), []
        day = d0
        while day <= d1:
            key = day.strftime("%Y%m%d")
            codes = self.data["days"].get(key)
            if codes is None:
                codes, names, page, total = [], {}, 1, 1
                complete = True
                while page <= total and page <= MAX_PAGES_PER_DAY:
                    r = dc.get("list.json", {"bgn_de": key, "end_de": key, "pblntf_ty": "F", "corp_cls": "E", "page_no": str(page), "page_count": "100"})
                    st = r.get("status")
                    if st == "013":            # 그날 공시 없음
                        break
                    if st != "000":
                        complete = False
                        break
                    total = int(r.get("total_page") or 1)
                    for x in r.get("list", []):
                        if "감사보고서" in x.get("report_nm", "") and x["corp_code"] not in names:
                            names[x["corp_code"]] = x.get("corp_name", "")
                            codes.append(x["corp_code"])
                    page += 1
                if page <= total:
                    complete = False
                self._names.update(names)
                if complete:
                    self.data["days"][key] = codes
                    self._dirty += 1
            for c in codes:
                if c not in seen:
                    seen.add(c)
                    nm = (self.data["corps"].get(c) or {}).get("n") or self._names.get(c, "")
                    out.append({"corp_code": c, "corp_name": nm, "stock_code": ""})
            day += _dt.timedelta(days=1)
        return out

    def progress(self, pool):
        n = sum(1 for c in pool if c["corp_code"] in self.data["corps"])
        return n, len(pool)
