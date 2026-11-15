"""수식 칸의 캐시 값(sheet XML의 `<v>`) 채우기.

openpyxl은 수식 칸에 계산 결과를 쓰지 않는다. 데스크톱 Excel·LibreOffice는 열 때 다시 계산하지만, 휴대폰 뷰어·메신저 미리보기·
macOS 훑어보기·웹 미리보기는 다시 계산하지 않아 수식 칸이 0이나 빈칸으로 보인다. 이 모듈은 `export_workbook`이 내보내는 수식 문법
(사칙연산·비교·문자열 연결, 칸·시트·범위 참조, 정의된 이름, 아래 `FUNCTIONS`의 함수)을 직접 계산해, 저장된 파일의 수식 칸에 값을 써 넣는다.
수식은 그대로 남고 `fullCalcOnLoad`가 켜져 있어 Excel은 열 때 다시 계산한다.

원칙: 틀린 값을 쓰느니 쓰지 않는다. 모르는 함수·문법, Excel과 LibreOffice가 다르게 계산하는 입력, 순환 참조를 만나면 그 칸과 그 칸에
의존하는 칸은 값을 쓰지 않고 개수를 돌려준다(호출자가 warnings로 알림). 외부 프로그램(LibreOffice·Excel)은 쓰지 않는다.

숫자 처리는 LibreOffice Calc를 따른다(전수 대조 기준): 덧셈·뺄셈의 0 근사, 비교의 근사 같음, ROUND 계열의 유효숫자 15자리 보정,
SUM의 보정 합산. 도구 수식은 나눗셈·곱셈 결과를 `ROUND(...,4)`로 감싸므로 Excel과도 같은 값이 나온다.
"""
from __future__ import annotations

import datetime as _dt
import math
import os
import re
import tempfile
import zipfile
from decimal import ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, ROUND_UP, Context, Decimal, localcontext
from xml.etree import ElementTree as _ET
from xml.sax.saxutils import escape as _xml_escape

from openpyxl.formula import Tokenizer
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.datetime import time_to_days, timedelta_to_days, to_excel

__all__ = ["FUNCTIONS", "evaluate_workbook", "fill_cached_values", "uncached_warning"]


class _Unsupported(Exception):
    """계산하지 않기로 한 수식(모르는 함수·문법, 프로그램마다 결과가 다른 입력)."""


class _Cycle(_Unsupported):
    """순환 참조."""


class _Need(Exception):
    """참조가 깊어 먼저 계산해야 하는 칸(재귀 깊이를 막기 위한 신호)."""

    def __init__(self, key):
        super().__init__(key)
        self.key = key


class XlError:
    """Excel 오류 값(#DIV/0! 등)."""
    __slots__ = ("code",)

    def __init__(self, code: str):
        self.code = code

    def __eq__(self, other):
        return isinstance(other, XlError) and other.code == self.code

    def __hash__(self):
        return hash(("XlError", self.code))

    def __repr__(self):
        return self.code


class _Blank:
    __slots__ = ()

    def __repr__(self):
        return "BLANK"


BLANK = _Blank()
_DIV0, _VALUE, _NUM, _NAME, _REF, _NA = (XlError(c) for c in ("#DIV/0!", "#VALUE!", "#NUM!", "#NAME?", "#REF!", "#N/A"))
_MAX_DEPTH = 40          # 칸에서 칸으로 이어지는 재귀 깊이 한도 — 넘으면 깊은 칸부터 따로 계산
_E48 = 1.0 / (16777216.0 * 16777216.0)
_E40 = _E48 * 256.0
_EPOCH = _dt.date(1899, 12, 30)
_CTX = Context(prec=400)


class _Ref:
    """칸·범위 참조(시트 객체 + 1부터 세는 행·열)."""
    __slots__ = ("ws", "r1", "c1", "r2", "c2")

    def __init__(self, ws, r1, c1, r2, c2):
        self.ws, self.r1, self.c1, self.r2, self.c2 = ws, r1, c1, r2, c2

    @property
    def single(self):
        return self.r1 == self.r2 and self.c1 == self.c2

    @property
    def shape(self):
        return self.r2 - self.r1 + 1, self.c2 - self.c1 + 1


# ───────────────────────── 수식 → 구문 트리 ─────────────────────────

_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})(?::\$?([A-Za-z]{1,3})\$?(\d{1,7}))?$")
_COLS = re.compile(r"^\$?([A-Za-z]{1,3}):\$?([A-Za-z]{1,3})$")
_ROWS = re.compile(r"^\$?(\d{1,7}):\$?(\d{1,7})$")
_QUOTED = re.compile(r"^'((?:[^']|'')*)'!(.*)$", re.S)
_PREC = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1, "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}


def _parse_operand(text: str):
    sheet = None
    m = _QUOTED.match(text)
    if m:
        sheet, text = m.group(1).replace("''", "'"), m.group(2)
    elif "!" in text:
        sheet, text = text.rsplit("!", 1)
    if sheet is not None and ("[" in sheet or ":" in sheet):
        raise _Unsupported("다른 파일·3차원 참조")
    m = _CELL.match(text)
    if m:
        c1, r1 = column_index_from_string(m.group(1).upper()), int(m.group(2))
        c2 = column_index_from_string(m.group(3).upper()) if m.group(3) else c1
        r2 = int(m.group(4)) if m.group(4) else r1
        return ("ref", sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))
    m = _COLS.match(text)
    if m:
        c1, c2 = sorted(column_index_from_string(g.upper()) for g in m.groups())
        return ("ref", sheet, None, c1, None, c2)
    m = _ROWS.match(text)
    if m:
        r1, r2 = sorted(int(g) for g in m.groups())
        return ("ref", sheet, r1, None, r2, None)
    if not text or re.search(r"[\s:\[\]{}#]", text):
        raise _Unsupported(f"참조 '{text}'")
    return ("name", sheet, text)


class _Parser:
    def __init__(self, formula: str):
        try:
            items = Tokenizer(formula).items
        except Exception as e:      # 토큰으로 나누지 못한 수식
            raise _Unsupported(f"수식 문법({e})")
        self.toks = [t for t in items if t.type != "WHITE-SPACE"]
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def parse(self):
        node = self.expr(0)
        if self.peek() is not None:
            raise _Unsupported("수식 문법")
        return node

    def expr(self, min_prec):
        left = self.unary()
        while True:
            t = self.peek()
            if t is None or t.type != "OPERATOR-INFIX":
                return left
            prec = _PREC.get(t.value)
            if prec is None:
                raise _Unsupported(f"연산자 '{t.value}'")
            if prec < min_prec:
                return left
            self.take()
            left = ("bin", t.value, left, self.expr(prec + 1))

    def unary(self):
        t = self.peek()
        if t is None:
            raise _Unsupported("수식 문법")
        if t.type == "OPERATOR-PREFIX":
            self.take()
            return ("neg" if t.value == "-" else "pos", self.unary())
        node = self.primary()
        while self.peek() is not None and self.peek().type == "OPERATOR-POSTFIX":
            self.take()
            node = ("pct", node)
        return node

    def primary(self):
        t = self.take()
        if t.type == "OPERAND":
            if t.subtype == "NUMBER":
                return ("num", float(t.value))
            if t.subtype == "TEXT":
                return ("str", t.value[1:-1].replace('""', '"'))
            if t.subtype == "LOGICAL":
                return ("bool", t.value.upper() == "TRUE")
            if t.subtype == "ERROR":
                return ("err", t.value.upper())
            return _parse_operand(t.value)
        if t.type == "PAREN" and t.subtype == "OPEN":
            node = self.expr(0)
            c = self.take() if self.peek() is not None else None
            if c is None or c.type != "PAREN" or c.subtype != "CLOSE":
                raise _Unsupported("수식 문법(괄호)")
            return node
        if t.type == "FUNC" and t.subtype == "OPEN":
            name = t.value[:-1].upper()
            args = []
            nxt = self.peek()
            if nxt is not None and nxt.type == "FUNC" and nxt.subtype == "CLOSE":
                self.take()
                return ("func", name, args)
            while True:
                nxt = self.peek()
                if nxt is None:
                    raise _Unsupported("수식 문법(괄호)")
                if nxt.type == "SEP" or (nxt.type == "FUNC" and nxt.subtype == "CLOSE"):
                    args.append(None)       # 빈 인수
                else:
                    args.append(self.expr(0))
                nxt = self.take() if self.peek() is not None else None
                if nxt is None:
                    raise _Unsupported("수식 문법(괄호)")
                if nxt.type == "FUNC" and nxt.subtype == "CLOSE":
                    return ("func", name, args)
                if nxt.type != "SEP" or nxt.subtype != "ARG":
                    raise _Unsupported("수식 문법(인수 구분)")
        raise _Unsupported(f"수식 문법('{t.value}')")


# ───────────────────────── 숫자 처리(LibreOffice Calc와 같게) ─────────────────────────

def _approx_equal(a: float, b: float) -> bool:
    if a == b:
        return True
    if a == 0.0 or b == 0.0:
        return False
    d = abs(a - b)
    if not math.isfinite(d):
        return False
    return d < abs(a) * _E48 and d < abs(b) * _E48


def _add(a: float, b: float) -> float:
    if ((a < 0.0 and b > 0.0) or (b < 0.0 and a > 0.0)) and _approx_equal(a, -b):
        return 0.0
    return a + b


def _sub(a: float, b: float) -> float:
    if ((a < 0.0 and b < 0.0) or (a > 0.0 and b > 0.0)) and _approx_equal(a, b):
        return 0.0
    return a - b


def _ksum(values) -> float:
    """합계 — 정확한 합을 한 번 반올림한 값(Calc의 보정 합산, Excel의 합과 유효숫자 15자리에서 같음).

    크기가 비슷한 값이 서로 지워져 합이 0 근처의 찌꺼기만 남는 경우는 프로그램·더하는 순서에 따라 0 또는 아주 작은 값으로 갈리므로 계산하지 않는다."""
    values = [v for v in values if v != 0.0]
    if not values:
        return 0.0
    total = math.fsum(values)
    if total != 0.0 and abs(total) < max(abs(v) for v in values) * _E40:
        raise _Unsupported("서로 지워져 0 근처만 남는 합")
    return total


def _dec15(x: float) -> Decimal:
    """유효숫자 15자리로 본 십진수(정수는 그대로)."""
    if x == math.floor(x):
        return Decimal(int(x))
    return Decimal("%.15g" % x)


def _round(x: float, digits: int, mode) -> float:
    if x == 0.0:
        return 0.0
    if digits >= 16:
        return x
    if digits < -20:
        raise _Unsupported("자릿수가 너무 큰 반올림")
    d = _dec15(x)
    if mode == ROUND_UP and len(d.as_tuple().digits) > 12 and d != d.to_integral_value():
        raise _Unsupported("유효숫자 12자리를 넘는 값의 ROUNDUP")     # Calc가 12자리로 줄인 뒤 올려 Excel과 갈린다
    r = float(d.quantize(Decimal(1).scaleb(-digits), rounding=mode, context=_CTX))
    return r + 0.0   # -0.0 → 0.0


def _approx_floor(x: float) -> float:
    return float(_dec15(x).to_integral_value(rounding=ROUND_FLOOR))


def _finite(x: float):
    return x if math.isfinite(x) else _NUM


_NUMERIC = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _text_to_number(s: str):
    """글 → 숫자. Excel과 Calc가 같은 답을 내는 꼴만 바꾼다."""
    t = s.strip(" ")
    if _NUMERIC.match(t):
        return float(t)
    m = _ISO_DATE.match(t)
    if m:
        try:
            d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return _VALUE
        if d < _dt.date(1900, 3, 1):
            raise _Unsupported("1900-03-01 이전 날짜")
        return float((d - _EPOCH).days)
    if t == "" or re.search(r"[^\d\s.,%+\-/:eE()₩$€£¥]", t):
        return _VALUE
    raise _Unsupported(f"숫자로 바꿀 글 '{s[:20]}'")


def _number_to_text(x: float) -> str:
    if x == math.floor(x) and abs(x) < 1e15:
        return str(int(x))
    t = "%.15g" % x
    if "e" in t or "E" in t:
        raise _Unsupported("지수 표기 숫자의 글 변환")
    with localcontext() as ctx:      # 15자리째가 반올림 경계에 걸리면 프로그램마다 끝자리가 갈린다
        ctx.prec = 15
        ctx.rounding = ROUND_HALF_UP
        if +Decimal(repr(x)) != Decimal(t):
            raise _Unsupported("끝자리가 갈리는 숫자의 글 변환")
    return t


def _serial_to_date(x: float) -> _dt.date:
    n = math.floor(x)
    if n < 61 or n > 2958465:
        raise _Unsupported("1900-03-01 이전·9999년 이후 날짜")
    return _EPOCH + _dt.timedelta(days=n)


# ───────────────────────── 계산기 ─────────────────────────

class _Evaluator:
    def __init__(self, wb):
        self.wb = wb
        self.memo: dict = {}
        self.failed: dict = {}
        self._active: set = set()
        self._depth = 0
        self._ast: dict = {}
        self._names: dict = {}
        self._dims: dict = {}

    # ── 칸 값 ──
    def _dim(self, ws):
        d = self._dims.get(ws.title)
        if d is None:
            d = self._dims[ws.title] = (max(ws.max_row, 1), max(ws.max_column, 1))
        return d

    def cell(self, ws, row, col):
        c = ws._cells.get((row, col))
        if c is None:
            return BLANK
        if c.data_type == "f":
            return self.formula_cell(ws, c)
        v = c.value
        if v is None or v == "":      # openpyxl은 빈 글("")을 빈 칸으로 저장한다
            return BLANK
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            return XlError(v) if c.data_type == "e" else v
        if isinstance(v, (_dt.datetime, _dt.date)):
            return float(to_excel(v, self.wb.epoch))
        if isinstance(v, _dt.time):
            return float(time_to_days(v))
        if isinstance(v, _dt.timedelta):
            return float(timedelta_to_days(v))
        raise _Unsupported(f"칸 값 형식 {type(v).__name__}")

    def formula_cell(self, ws, c):
        key = (ws.title, c.row, c.column)
        if key in self.memo:
            return self.memo[key]
        if key in self.failed:
            raise _Unsupported(self.failed[key])
        if key in self._active:
            raise _Cycle("순환 참조")
        if self._depth >= _MAX_DEPTH:
            raise _Need(key)
        self._active.add(key)
        self._depth += 1
        try:
            f = c.value
            if not isinstance(f, str):
                raise _Unsupported("배열·표 수식")
            ast = self._ast.get(f)
            if ast is None:
                ast = self._ast[f] = _Parser(f).parse()
            v = self.scalar(self.ev(ast, ws))
            if v is BLANK:
                v = 0.0
            elif isinstance(v, float):
                v = _finite(v)
            elif isinstance(v, str) and (len(v) > 32767 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]", v)):
                raise _Unsupported("XML에 쓸 수 없는 글자")
        except _Need:
            raise
        except _Unsupported as e:
            self.failed[key] = str(e) or "계산하지 않음"
            raise
        finally:
            self._active.discard(key)
            self._depth -= 1
        self.memo[key] = v
        return v

    def run(self, ws, c):
        """한 수식 칸을 계산(깊은 참조는 스택으로 풀어 재귀를 얕게)."""
        stack = [(ws, c)]
        while stack:
            w, cc = stack[-1]
            key = (w.title, cc.row, cc.column)
            if key in self.memo or key in self.failed:
                stack.pop()
                continue
            self._active.clear()
            self._depth = 0
            try:
                self.formula_cell(w, cc)
            except _Need as n:
                keys = [(a.title, b.row, b.column) for a, b in stack]
                if n.key in keys:       # 깊은 사슬을 거친 순환
                    i = keys.index(n.key)
                    for k in keys[i:]:
                        self.failed[k] = "순환 참조"
                    del stack[i:]
                else:
                    stack.append((self.wb[n.key[0]], self.wb[n.key[0]]._cells[(n.key[1], n.key[2])]))
            except _Unsupported:
                pass
            except RecursionError:
                self.failed[key] = "수식이 너무 깊음"
            except Exception as e:      # 예상하지 못한 값·수식 — 그 칸만 건너뜀
                self.failed[key] = f"계산하지 못함({type(e).__name__})"

    # ── 참조 ──
    def _sheet(self, name, ws):
        if name is None:
            return ws
        if name in self.wb.sheetnames:
            return self.wb[name]
        low = name.lower()
        for n in self.wb.sheetnames:
            if n.lower() == low:
                return self.wb[n]
        return None

    def _name(self, sheet, name, ws):
        scope = self._sheet(sheet, ws)
        if scope is None:
            return _REF
        low = name.lower()
        dn = None
        for holder in (scope.defined_names, self.wb.defined_names):
            for k, d in holder.items():
                if k.lower() == low:
                    dn = d
                    break
            if dn is not None:
                break
        if dn is None:
            return _NAME
        text = dn.attr_text
        if text is None:
            return _NAME
        ast = self._names.get(text)
        if ast is None:
            ast = self._names[text] = _Parser("=" + text).parse()
        if ast[0] == "ref" and ast[1] is None:
            raise _Unsupported("시트 이름 없는 정의된 이름")
        return self.ev(ast, ws)

    def cells(self, ref: _Ref):
        """범위의 값을 행 우선으로(빈 칸은 BLANK)."""
        ws = ref.ws
        for r in range(ref.r1, ref.r2 + 1):
            for c in range(ref.c1, ref.c2 + 1):
                yield self.cell(ws, r, c)

    def scalar(self, v):
        if isinstance(v, _Ref):
            if v.single:
                return self.cell(v.ws, v.r1, v.c1)
            raise _Unsupported("범위를 값 하나로 쓰는 수식")
        return v

    # ── 값 변환 ──
    def num(self, v):
        """→ float 또는 XlError."""
        v = self.scalar(v)
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        if isinstance(v, float):
            return v
        if v is BLANK:
            return 0.0
        if isinstance(v, XlError):
            return v
        return _text_to_number(v)

    def text(self, v):
        v = self.scalar(v)
        if isinstance(v, str) or isinstance(v, XlError):
            return v
        if v is BLANK:
            return ""
        if isinstance(v, bool):
            raise _Unsupported("논리값의 글 변환")
        return _number_to_text(v)

    def truth(self, v):
        """→ bool 또는 XlError."""
        v = self.scalar(v)
        if isinstance(v, bool):
            return v
        if isinstance(v, float):
            return v != 0.0
        if v is BLANK:
            return False
        if isinstance(v, XlError):
            return v
        raise _Unsupported("글을 참·거짓으로 쓰는 수식")

    def compare(self, a, b) -> int:
        """-1·0·1. 숫자 < 글 < 논리값."""
        if a is BLANK and b is BLANK:
            return 0
        if a is BLANK:
            a = "" if isinstance(b, str) else (False if isinstance(b, bool) else 0.0)
        if b is BLANK:
            b = "" if isinstance(a, str) else (False if isinstance(a, bool) else 0.0)
        ra = 2 if isinstance(a, bool) else (1 if isinstance(a, str) else 0)
        rb = 2 if isinstance(b, bool) else (1 if isinstance(b, str) else 0)
        if ra != rb:
            if ra == 2 or rb == 2:      # Excel은 논리값을 숫자·글보다 크게, Calc는 논리값을 숫자 1·0으로 본다
                raise _Unsupported("논리값과 숫자·글의 비교")
            return -1 if ra < rb else 1
        if ra == 0:
            if _approx_equal(a, b):
                return 0
            return -1 if a < b else 1
        if ra == 1:
            if a.lower() == b.lower():
                return 0
            if a.casefold() == b.casefold():
                raise _Unsupported("대소문자 규칙이 갈리는 글 비교")
            return None     # 다름 — 크기 순서는 정렬 규칙에 따라 달라 따로 판단
        return (a > b) - (a < b)

    # ── 구문 트리 계산 ──
    def ev(self, node, ws):
        kind = node[0]
        if kind == "num" or kind == "str" or kind == "bool":
            return node[1]
        if kind == "err":
            return XlError(node[1])
        if kind == "ref":
            target = self._sheet(node[1], ws)
            if target is None:
                return _REF
            r1, c1, r2, c2 = node[2:]
            if r1 is None:
                r1, r2 = 1, self._dim(target)[0]
            if c1 is None:
                c1, c2 = 1, self._dim(target)[1]
            return _Ref(target, r1, c1, r2, c2)
        if kind == "name":
            return self._name(node[1], node[2], ws)
        if kind == "func":
            fn = _FUNCS.get(node[1])
            if fn is None:
                raise _Unsupported(f"함수 {node[1]}")
            return fn(self, node[2], ws)
        if kind == "neg" or kind == "pos":
            v = self.num(self.ev(node[1], ws))
            if isinstance(v, XlError):
                return v
            return -v + 0.0 if kind == "neg" else v
        if kind == "pct":
            v = self.num(self.ev(node[1], ws))
            return v if isinstance(v, XlError) else v / 100.0
        op = node[1]
        a = self.scalar(self.ev(node[2], ws))
        b = self.scalar(self.ev(node[3], ws))
        if op == "&":
            a, b = self.text(a), self.text(b)
            if isinstance(a, XlError):
                return a
            if isinstance(b, XlError):
                return b
            return a + b
        if op in ("=", "<>", "<", ">", "<=", ">="):
            if isinstance(a, XlError):
                return a
            if isinstance(b, XlError):
                return b
            c = self.compare(a, b)
            if c is None:
                if op == "=":
                    return False
                if op == "<>":
                    return True
                raise _Unsupported("글의 크기 비교")
            return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]
        a, b = self.num(a), self.num(b)
        if isinstance(a, XlError):
            return a
        if isinstance(b, XlError):
            return b
        if op == "+":
            return _finite(_add(a, b))
        if op == "-":
            return _finite(_sub(a, b))
        if op == "*":
            return _finite(a * b)
        if op == "/":
            return _DIV0 if b == 0.0 else _finite(a / b)
        if op == "^":
            if a == 0.0 and b == 0.0:
                raise _Unsupported("0^0")
            if a < 0.0 and b != math.floor(b):      # Excel은 #NUM!, Calc는 홀수 근을 계산
                raise _Unsupported("음수의 분수 거듭제곱")
            try:
                r = math.pow(a, b)
            except (ValueError, OverflowError, ZeroDivisionError):
                return _NUM if a != 0.0 else _DIV0
            return _finite(r)
        raise _Unsupported(f"연산자 '{op}'")

    # ── 함수 도우미 ──
    def arg(self, args, i, ws, default=BLANK):
        if i >= len(args) or args[i] is None:
            return default
        return self.ev(args[i], ws)

    def numbers(self, args, ws, *, skip_errors=False, count=False):
        """SUM·MIN·MAX·COUNT 식 숫자 모으기: 범위 안에서는 숫자만, 직접 준 값은 논리값·숫자 글도 숫자로."""
        out = []
        for a in args:
            v = BLANK if a is None else self.ev(a, ws)
            if isinstance(v, _Ref):
                for x in self.cells(v):
                    if isinstance(x, float):
                        out.append(x)
                    elif isinstance(x, bool):      # Excel은 범위 안 논리값을 건너뛰고 Calc는 1·0으로 센다
                        raise _Unsupported("범위 안 논리값의 집계")
                    elif isinstance(x, XlError) and not skip_errors:
                        return x
                continue
            if isinstance(v, XlError):
                if skip_errors:
                    continue
                return v
            if isinstance(v, str):      # Excel은 숫자 글을 숫자로 세고 Calc는 오류로 본다
                raise _Unsupported("집계 함수에 직접 준 글")
            elif v is BLANK:
                if count:
                    raise _Unsupported("COUNT의 빈 인수")
                out.append(0.0)
            else:
                out.append(1.0 if v is True else (0.0 if v is False else v))
        return out


def _need_args(name, args, lo, hi=None):
    hi = lo if hi is None else hi
    if not lo <= len(args) <= hi:
        raise _Unsupported(f"{name} 인수 개수")


def _f_if(ev, args, ws):
    _need_args("IF", args, 2, 3)
    c = ev.truth(ev.arg(args, 0, ws))
    if isinstance(c, XlError):
        return c
    if c:
        return ev.arg(args, 1, ws, 0.0)
    if len(args) < 3:
        return False
    return ev.arg(args, 2, ws, 0.0)


def _logical(ev, args, ws, name):
    if not args:
        raise _Unsupported(f"{name} 인수 개수")
    vals = []
    for a in args:
        v = BLANK if a is None else ev.ev(a, ws)
        if isinstance(v, _Ref) and not v.single:
            for x in ev.cells(v):
                if isinstance(x, XlError):
                    return x
                if isinstance(x, bool) or isinstance(x, float):
                    vals.append(bool(x))
            continue
        ref = isinstance(v, _Ref)
        v = ev.scalar(v)
        if isinstance(v, XlError):
            return v
        if isinstance(v, str) or v is BLANK:
            if ref and v is BLANK:
                continue
            raise _Unsupported(f"{name}에 준 글·빈 값")
        vals.append(bool(v))
    if not vals:
        return _VALUE
    return vals


def _f_and(ev, args, ws):
    v = _logical(ev, args, ws, "AND")
    return v if isinstance(v, XlError) else all(v)


def _f_or(ev, args, ws):
    v = _logical(ev, args, ws, "OR")
    return v if isinstance(v, XlError) else any(v)


def _f_not(ev, args, ws):
    _need_args("NOT", args, 1)
    v = ev.truth(ev.arg(args, 0, ws))
    return v if isinstance(v, XlError) else not v


def _f_iferror(ev, args, ws):
    _need_args("IFERROR", args, 2)
    v = ev.scalar(ev.arg(args, 0, ws))
    if isinstance(v, XlError):
        return ev.arg(args, 1, ws, 0.0)
    return v


def _f_sum(ev, args, ws):
    _need_args("SUM", args, 1, 255)
    v = ev.numbers(args, ws)
    return v if isinstance(v, XlError) else _finite(_ksum(v))


def _f_min(ev, args, ws):
    _need_args("MIN", args, 1, 255)
    v = ev.numbers(args, ws)
    return v if isinstance(v, XlError) else (min(v) if v else 0.0)


def _f_max(ev, args, ws):
    _need_args("MAX", args, 1, 255)
    v = ev.numbers(args, ws)
    return v if isinstance(v, XlError) else (max(v) if v else 0.0)


def _f_average(ev, args, ws):
    v = ev.numbers(args, ws)
    if isinstance(v, XlError):
        return v
    return _DIV0 if not v else _finite(_ksum(v) / len(v))


def _f_count(ev, args, ws):
    return float(len(ev.numbers(args, ws, skip_errors=True, count=True)))


def _f_counta(ev, args, ws):
    n = 0
    for a in args:
        v = BLANK if a is None else ev.ev(a, ws)
        if isinstance(v, _Ref):
            n += sum(1 for x in ev.cells(v) if x is not BLANK)
        else:
            n += 1
    return float(n)


def _one_num(ev, args, ws, name):
    _need_args(name, args, 1)
    return ev.num(ev.arg(args, 0, ws))


def _f_abs(ev, args, ws):
    v = _one_num(ev, args, ws, "ABS")
    return v if isinstance(v, XlError) else abs(v)


def _f_int(ev, args, ws):
    v = _one_num(ev, args, ws, "INT")
    return v if isinstance(v, XlError) else _approx_floor(v)


def _rounder(mode, name):
    def fn(ev, args, ws):
        _need_args(name, args, 1, 2)
        x = ev.num(ev.arg(args, 0, ws))
        if isinstance(x, XlError):
            return x
        d = ev.num(ev.arg(args, 1, ws, 0.0)) if len(args) > 1 else 0.0
        if isinstance(d, XlError):
            return d
        return _finite(_round(x, int(math.floor(d)) if d >= 0 else -int(math.floor(-d)), mode))
    return fn


def _f_mod(ev, args, ws):
    _need_args("MOD", args, 2)
    a, b = ev.num(ev.arg(args, 0, ws)), ev.num(ev.arg(args, 1, ws))
    if isinstance(a, XlError):
        return a
    if isinstance(b, XlError):
        return b
    if b == 0.0:
        return _DIV0
    if a != math.floor(a) or b != math.floor(b) or abs(a) >= 2 ** 53 or abs(b) >= 2 ** 53:
        raise _Unsupported("정수가 아닌 MOD")
    return float(int(a) % int(b))


def _first(ev, v):
    """N·IS* 함수의 인수: 범위면 첫 칸."""
    if isinstance(v, _Ref):
        return ev.cell(v.ws, v.r1, v.c1)
    return v


def _f_n(ev, args, ws):
    _need_args("N", args, 1)
    v = _first(ev, ev.arg(args, 0, ws))
    if isinstance(v, XlError) or isinstance(v, float):
        return v
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    return 0.0


def _is(pred, name):
    def fn(ev, args, ws):
        _need_args(name, args, 1)
        return bool(pred(_first(ev, ev.arg(args, 0, ws))))
    return fn


def _is_number(v):
    if isinstance(v, bool):     # Excel은 FALSE, Calc는 TRUE
        raise _Unsupported("ISNUMBER에 준 논리값")
    return isinstance(v, float)


def _f_value(ev, args, ws):
    _need_args("VALUE", args, 1)
    v = ev.scalar(ev.arg(args, 0, ws))
    if isinstance(v, XlError) or isinstance(v, float):
        return v
    if v is BLANK:
        return 0.0
    if isinstance(v, bool):
        raise _Unsupported("VALUE에 준 논리값")
    return _text_to_number(v)


def _count_arg(ev, args, i, ws, default):
    if i >= len(args):
        return default
    n = ev.num(ev.arg(args, i, ws))
    if isinstance(n, XlError):
        return n
    return math.floor(n)


def _text_arg(ev, args, ws):
    t = ev.text(ev.arg(args, 0, ws))
    if isinstance(t, str) and any(ord(ch) > 0xFFFF for ch in t):
        raise _Unsupported("보조 평면 글자의 길이 계산")
    return t


def _f_left(ev, args, ws):
    _need_args("LEFT", args, 1, 2)
    t, n = _text_arg(ev, args, ws), _count_arg(ev, args, 1, ws, 1)
    if isinstance(t, XlError):
        return t
    if isinstance(n, XlError):
        return n
    return _VALUE if n < 0 else t[:n]


def _f_right(ev, args, ws):
    _need_args("RIGHT", args, 1, 2)
    t, n = _text_arg(ev, args, ws), _count_arg(ev, args, 1, ws, 1)
    if isinstance(t, XlError):
        return t
    if isinstance(n, XlError):
        return n
    if n < 0:
        return _VALUE
    return t[len(t) - n:] if 0 < n < len(t) else ("" if n == 0 else t)


def _f_mid(ev, args, ws):
    _need_args("MID", args, 3)
    t, s, n = _text_arg(ev, args, ws), _count_arg(ev, args, 1, ws, 1), _count_arg(ev, args, 2, ws, 0)
    for x in (t, s, n):
        if isinstance(x, XlError):
            return x
    if s < 1 or n < 0:
        return _VALUE
    return t[s - 1:s - 1 + n]


def _f_len(ev, args, ws):
    _need_args("LEN", args, 1)
    t = _text_arg(ev, args, ws)
    return t if isinstance(t, XlError) else float(len(t))


def _f_date(ev, args, ws):
    _need_args("DATE", args, 3)
    parts = []
    for i in range(3):
        n = ev.num(ev.arg(args, i, ws))
        if isinstance(n, XlError):
            return n
        parts.append(math.floor(n))
    y, m, d = parts
    if not 1900 <= y <= 9999 or abs(m) > 120000 or abs(d) > 3660000:
        raise _Unsupported("DATE 범위")
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    if not 1900 <= y <= 9999:
        raise _Unsupported("DATE 범위")
    day = _dt.date(y, m, 1) + _dt.timedelta(days=d - 1)
    if day < _dt.date(1900, 3, 1) or day.year > 9999:
        raise _Unsupported("DATE 범위")
    return float((day - _EPOCH).days)


def _f_datedif(ev, args, ws):
    _need_args("DATEDIF", args, 3)
    a, b = ev.num(ev.arg(args, 0, ws)), ev.num(ev.arg(args, 1, ws))
    u = ev.scalar(ev.arg(args, 2, ws))
    if isinstance(a, XlError):
        return a
    if isinstance(b, XlError):
        return b
    if not isinstance(u, str):
        raise _Unsupported("DATEDIF 단위")
    if a > b:
        raise _Unsupported("DATEDIF 시작일이 종료일보다 늦음")
    s, e = _serial_to_date(a), _serial_to_date(b)
    u = u.lower()
    if u == "d":
        return float((e - s).days)
    months = (e.year - s.year) * 12 + (e.month - s.month) - (1 if e.day < s.day else 0)
    if u == "m":
        return float(months)
    if u == "y":
        return float(months // 12)
    raise _Unsupported(f"DATEDIF 단위 '{u}'")


# ── SUMIF·SUMIFS·COUNTIF ──
_CRIT_OP = re.compile(r"^(<>|<=|>=|=|<|>)?(.*)$", re.S)


def _criterion(ev, v):
    """조건 → (칸 값 → bool). 프로그램마다 갈리는 꼴은 계산하지 않는다."""
    v = ev.scalar(v)
    if isinstance(v, XlError):
        return v
    if v is BLANK:
        raise _Unsupported("빈 조건")
    if isinstance(v, bool):
        raise _Unsupported("논리값 조건")
    op, rhs = "=", v
    if isinstance(v, str):
        m = _CRIT_OP.match(v)
        op, rhs = m.group(1) or "=", m.group(2)
        if rhs == "":
            raise _Unsupported("빈 조건")
        if _NUMERIC.match(rhs.strip(" ")):
            rhs = float(rhs)
        elif rhs.upper() in ("TRUE", "FALSE") or _ISO_DATE.match(rhs.strip(" ")):
            raise _Unsupported("논리값·날짜 글 조건")
    if isinstance(rhs, float):
        def num_match(x, op=op, rhs=rhs):
            if isinstance(x, bool) or (isinstance(x, str) and _NUMERIC.match(x.strip(" "))):
                raise _Unsupported("논리값·숫자 글 칸과 숫자 조건")
            if not isinstance(x, float):
                return op == "<>"
            eq = _approx_equal(x, rhs)
            return {"=": eq, "<>": not eq, "<": x < rhs and not eq, ">": x > rhs and not eq,
                    "<=": x < rhs or eq, ">=": x > rhs or eq}[op]
        return num_match
    if op not in ("=", "<>"):
        raise _Unsupported("글의 크기 조건")
    if not rhs.isascii() and rhs.casefold() != rhs.lower():
        raise _Unsupported("대소문자 규칙이 갈리는 글 조건")
    if re.search(r"[*?~]", rhs):
        pat, i = "", 0
        while i < len(rhs):
            ch = rhs[i]
            if ch == "~" and i + 1 < len(rhs):
                pat += re.escape(rhs[i + 1])
                i += 2
                continue
            pat += ".*" if ch == "*" else ("." if ch == "?" else re.escape(ch))
            i += 1
        rx = re.compile(pat, re.I | re.S)
        match = lambda s: rx.fullmatch(s) is not None      # noqa: E731
    else:
        low = rhs.lower()
        match = lambda s: s.lower() == low                 # noqa: E731

    def text_match(x, op=op):
        hit = isinstance(x, str) and match(x)
        return hit if op == "=" else not hit
    return text_match


def _range_arg(ev, args, i, ws, name):
    v = ev.arg(args, i, ws)
    if isinstance(v, XlError):
        return v
    if not isinstance(v, _Ref):
        raise _Unsupported(f"{name}의 범위 인수")
    return v


def _sum_matching(ev, sum_ref, tests):
    """tests: [(범위, 판정 함수)] — 모두 맞는 자리의 sum_ref 숫자를 더한다."""
    rows, cols = tests[0][0].shape
    vals = []
    for dr in range(rows):
        for dc in range(cols):
            ok = True
            for ref, pred in tests:
                if not pred(ev.cell(ref.ws, ref.r1 + dr, ref.c1 + dc)):
                    ok = False
                    break
            if not ok:
                continue
            if sum_ref is None:
                vals.append(1.0)
                continue
            x = ev.cell(sum_ref.ws, sum_ref.r1 + dr, sum_ref.c1 + dc)
            if isinstance(x, XlError):
                return x
            if isinstance(x, bool):
                raise _Unsupported("범위 안 논리값의 집계")
            if isinstance(x, float):
                vals.append(x)
    return _finite(_ksum(vals))


def _f_sumif(ev, args, ws):
    _need_args("SUMIF", args, 2, 3)
    rng = _range_arg(ev, args, 0, ws, "SUMIF")
    if isinstance(rng, XlError):
        return rng
    pred = _criterion(ev, ev.arg(args, 1, ws))
    if isinstance(pred, XlError):
        return pred
    sum_ref = rng
    if len(args) == 3 and args[2] is not None:
        sum_ref = _range_arg(ev, args, 2, ws, "SUMIF")
        if isinstance(sum_ref, XlError):
            return sum_ref
    return _sum_matching(ev, sum_ref, [(rng, pred)])


def _pairs(ev, args, ws, name, start):
    if (len(args) - start) % 2 or len(args) - start < 2:
        raise _Unsupported(f"{name} 인수 개수")
    tests = []
    for i in range(start, len(args), 2):
        rng = _range_arg(ev, args, i, ws, name)
        if isinstance(rng, XlError):
            return rng
        pred = _criterion(ev, ev.arg(args, i + 1, ws))
        if isinstance(pred, XlError):
            return pred
        tests.append((rng, pred))
    return tests


def _f_sumifs(ev, args, ws):
    sum_ref = _range_arg(ev, args, 0, ws, "SUMIFS")
    if isinstance(sum_ref, XlError):
        return sum_ref
    tests = _pairs(ev, args, ws, "SUMIFS", 1)
    if isinstance(tests, XlError):
        return tests
    if any(r.shape != sum_ref.shape for r, _ in tests):
        return _VALUE
    return _sum_matching(ev, sum_ref, tests)


def _f_countif(ev, args, ws):
    _need_args("COUNTIF", args, 2)
    tests = _pairs(ev, args, ws, "COUNTIF", 0)
    return tests if isinstance(tests, XlError) else _sum_matching(ev, None, tests)


_FUNCS = {
    "IF": _f_if, "AND": _f_and, "OR": _f_or, "NOT": _f_not, "IFERROR": _f_iferror,
    "SUM": _f_sum, "MIN": _f_min, "MAX": _f_max, "AVERAGE": _f_average, "COUNT": _f_count, "COUNTA": _f_counta,
    "ABS": _f_abs, "INT": _f_int, "MOD": _f_mod,
    "ROUND": _rounder(ROUND_HALF_UP, "ROUND"), "ROUNDDOWN": _rounder(ROUND_DOWN, "ROUNDDOWN"),
    "ROUNDUP": _rounder(ROUND_UP, "ROUNDUP"), "TRUNC": _rounder(ROUND_DOWN, "TRUNC"),
    "N": _f_n, "VALUE": _f_value,
    "ISNUMBER": _is(_is_number, "ISNUMBER"),
    "ISTEXT": _is(lambda v: isinstance(v, str), "ISTEXT"),
    "ISLOGICAL": _is(lambda v: isinstance(v, bool), "ISLOGICAL"),
    "ISBLANK": _is(lambda v: v is BLANK, "ISBLANK"),
    "ISERROR": _is(lambda v: isinstance(v, XlError), "ISERROR"),
    "LEFT": _f_left, "RIGHT": _f_right, "MID": _f_mid, "LEN": _f_len,
    "DATE": _f_date, "DATEDIF": _f_datedif,
    "SUMIF": _f_sumif, "SUMIFS": _f_sumifs, "COUNTIF": _f_countif,
}
FUNCTIONS = tuple(sorted(_FUNCS))     # 캐시 값을 계산하는 함수 목록


# ───────────────────────── 통합 문서 계산 · 파일에 쓰기 ─────────────────────────

def evaluate_workbook(wb):
    """통합 문서의 모든 수식 칸을 계산한다.

    돌려주는 값: (값, 못 쓴 칸) — 값은 {시트 이름: {칸 주소: 숫자·글·논리값·XlError}}, 못 쓴 칸은 [(시트 이름, 칸 주소, 이유)]."""
    ev = _Evaluator(wb)
    values: dict = {}
    skipped: list = []
    for ws in wb.worksheets:
        out = values.setdefault(ws.title, {})
        for (row, col), c in sorted(ws._cells.items()):
            if c.data_type != "f":
                continue
            ev.run(ws, c)
            key = (ws.title, row, col)
            coord = f"{get_column_letter(col)}{row}"
            if key in ev.memo:
                out[coord] = ev.memo[key]
            else:
                skipped.append((ws.title, coord, ev.failed.get(key, "계산하지 않음")))
    return values, skipped


def _v_xml(value):
    """→ (t 속성 또는 None, <v> 안의 글)."""
    if isinstance(value, bool):
        return "b", "1" if value else "0"
    if isinstance(value, XlError):
        return "e", _xml_escape(value.code)
    if isinstance(value, str):
        return "str", _xml_escape(value)
    if value == math.floor(value) and abs(value) < 1e15:
        return None, str(int(value))
    return None, repr(value)


_C_FORMULA = re.compile(
    rb'<c r="([A-Z]{1,3}[0-9]{1,7})"((?: [A-Za-z:]+="[^"]*")*)>(<f(?: [^>]*)?(?:/>|>[^<]*</f>))(?:<v\s*/>|<v></v>)?</c>')
_T_ATTR = re.compile(rb' t="[^"]*"')


def _patch_sheet(xml: bytes, values: dict):
    """sheet XML의 수식 칸(값이 비어 있는 칸)에 `<v>`를 써 넣는다. (새 XML, 쓴 칸 수)."""
    n = 0

    def repl(m):
        nonlocal n
        coord = m.group(1).decode("ascii")
        if coord not in values:
            return m.group(0)
        t, text = _v_xml(values[coord])
        attrs = _T_ATTR.sub(b"", m.group(2))
        if t:
            attrs += b' t="' + t.encode("ascii") + b'"'
        n += 1
        return b'<c r="' + m.group(1) + b'"' + attrs + b">" + m.group(3) + b"<v>" + text.encode("utf-8") + b"</v></c>"

    return _C_FORMULA.sub(repl, xml), n


_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NS_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _sheet_parts(zf) -> dict:
    """{시트 이름: zip 안의 sheet XML 경로}."""
    rels = {}
    for r in _ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")).iter(_NS_PKG + "Relationship"):
        target = r.get("Target", "")
        rels[r.get("Id")] = target.lstrip("/") if target.startswith("/") else "xl/" + target
    parts = {}
    for s in _ET.fromstring(zf.read("xl/workbook.xml")).iter(_NS_MAIN + "sheet"):
        path = rels.get(s.get(_NS_REL + "id"))
        if path:
            parts[s.get("name")] = path
    return parts


def fill_cached_values(wb, path: str) -> dict:
    """`wb`를 `path`에 저장한 뒤 부른다 — 수식 칸의 계산 값을 파일에 써 넣는다(수식은 그대로).

    돌려주는 값: {"수식_칸": n, "값_쓴_칸": n, "못_쓴_칸": [(시트, 칸, 이유)…]}. 파일은 임시 파일에 쓴 뒤 바꿔치기한다."""
    values, skipped = evaluate_workbook(wb)
    total = sum(len(v) for v in values.values()) + len(skipped)
    if not total:
        return {"수식_칸": 0, "값_쓴_칸": 0, "못_쓴_칸": []}
    written = 0
    fd, tmp = tempfile.mkstemp(suffix=".xlsx.tmp", dir=os.path.dirname(os.path.abspath(path)))
    os.close(fd)
    try:
        with zipfile.ZipFile(path) as src:
            by_part = {part: values.get(name) or {} for name, part in _sheet_parts(src).items()}
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
                for info in src.infolist():
                    data = src.read(info.filename)
                    vals = by_part.get(info.filename)
                    if vals:
                        data, n = _patch_sheet(data, vals)
                        written += n
                    dst.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return {"수식_칸": total, "값_쓴_칸": written, "못_쓴_칸": skipped}


def uncached_warning(info: dict, lang: str = "ko"):
    """캐시 값을 쓰지 못한 칸이 있으면 warnings에 넣을 한 줄, 없으면 None."""
    n = info["수식_칸"] - info["값_쓴_칸"]
    if n <= 0:
        return None
    ex = "; ".join(f"'{s}'!{c} — {why}" for s, c, why in info["못_쓴_칸"][:3])
    if lang == "en":
        return (f"{n} formula cell(s) carry no stored value and may show blank or 0 in phone viewers and previews "
                f"(desktop Excel recalculates them on open)" + (f": {ex}" if ex else ""))
    return f"미리보기에서 값이 안 보일 수 있는 칸 {n}개(휴대폰 뷰어·미리보기는 수식을 다시 계산하지 않음 — 데스크톱 Excel에서는 열 때 계산됨)" + (f": {ex}" if ex else "")
