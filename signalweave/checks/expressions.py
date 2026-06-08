"""Safe expression evaluator for SignalWeave rule checks.

Parses and evaluates a natural-language expression string against a data
payload.  No ``eval()`` or ``exec()`` is used — the grammar is handled by a
hand-written recursive-descent / Pratt parser and an AST interpreter.

Grammar overview (loosest → tightest binding)
---------------------------------------------
  expr        ::= ternary
  ternary     ::= 'if' or 'then' or ('else' or)?
                | or
  or          ::= and ('or' and)*
  and         ::= not ('and' not)*
  not         ::= 'not' not | compare
  compare     ::= add ( ( '==' | '!=' | '>' | '>=' | '<' | '<=' ) add
                       | 'not'? 'in' add
                       | 'between' add 'and' add
                       | 'is' 'not'? ('present' | 'empty')
                       )?
  add         ::= mul ( ('+' | '-') mul )*
  mul         ::= unary ( ('*' | '/') unary )*
  unary       ::= '-' unary | primary
  primary     ::= '(' expr ')'
                | NUMBER | STRING | 'true' | 'false' | 'null'
                | '[' (item ',')* item? ']'      -- list literal; bare words → strings
                | PROJECTION                      -- data.list[].field
                | FUNC_NAME '(' ... ')'           -- see function rules below
                | IDENT                           -- field path

  Functions
  ---------
  count / all / any / none:   func '(' field_path ('where' expr)? ')'
  length / len / sum / min / max / avg / present / exists:
                              func '(' ( PROJECTION | IDENT ) ')'

Bare single-word identifiers inside list literals ``[...]`` are treated as
string values, not field references, so ``data.cat in [Operational, Financial]``
works naturally without quoting.

Keywords
--------
  and  or  not  in  between  is  where  if  then  else  true  false  null

Public API
----------
  evaluate_expression(text, data) -> ConditionResult
  parse_expression(text)  -> AST root node  (raises ExpressionError on errors)
  collect_expression_fields(text) -> list[tuple[str, str]]
  ExpressionError

Missing-data propagation
------------------------
* A missing field in a comparison or arithmetic expression → result is *missing*
  (not a clean FALSE), mirroring leaf-condition semantics.  The engine then
  applies the rule's ``on_missing`` policy.
* Presence predicates (``is present`` / ``is empty``) never report missing.
* ``and`` / ``or`` / ``not`` propagate missing exactly like ``all`` / ``any`` /
  ``not`` in the structured form.
* Ternary propagates missing from the antecedent; a false antecedent with no
  ``else`` passes vacuously (same as structured ``if/then``).
* Quantifiers (``all`` / ``any`` / ``none`` / ``count``) over a missing or
  non-list field report missing; element-level missing follows structured rules.

Security
--------
  Whitelisted function names only.  Bounded recursion depth.
  No ``eval`` / ``exec`` / arbitrary attribute access.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .operators import _as_number, _compare  # type: ignore[reportPrivateUsage]
from .paths import MISSING, is_empty, resolve_path

_MAX_DEPTH = 64  # maximum AST recursion depth


# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------

class ExpressionError(ValueError):
    """Raised when an expression cannot be parsed or evaluated."""

    def __init__(self, message: str, pos: int = -1) -> None:
        self.message = message
        self.pos = pos
        if pos >= 0:
            super().__init__(f"{message} (at position {pos})")
        else:
            super().__init__(message)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class _TT(str, Enum):
    NUMBER    = "NUMBER"
    STRING    = "STRING"
    IDENT     = "IDENT"       # dotted field path, e.g. data.amount
    PROJECTION = "PROJECTION" # list projection, e.g. data.items[].field
    PLUS      = "PLUS"
    MINUS     = "MINUS"
    STAR      = "STAR"
    SLASH     = "SLASH"
    EQ        = "EQ"          # ==
    NEQ       = "NEQ"         # !=
    GT        = "GT"          # >
    GTE       = "GTE"         # >=
    LT        = "LT"          # <
    LTE       = "LTE"         # <=
    LPAREN    = "LPAREN"
    RPAREN    = "RPAREN"
    LBRACKET  = "LBRACKET"
    RBRACKET  = "RBRACKET"
    COMMA     = "COMMA"
    # Keywords
    KW_AND     = "KW_AND"
    KW_OR      = "KW_OR"
    KW_NOT     = "KW_NOT"
    KW_IN      = "KW_IN"
    KW_BETWEEN = "KW_BETWEEN"
    KW_IS      = "KW_IS"
    KW_WHERE   = "KW_WHERE"
    KW_IF      = "KW_IF"
    KW_THEN    = "KW_THEN"
    KW_ELSE    = "KW_ELSE"
    KW_TRUE    = "KW_TRUE"
    KW_FALSE   = "KW_FALSE"
    KW_NULL    = "KW_NULL"
    EOF       = "EOF"


_KEYWORDS: dict[str, _TT] = {
    "and":     _TT.KW_AND,
    "or":      _TT.KW_OR,
    "not":     _TT.KW_NOT,
    "in":      _TT.KW_IN,
    "between": _TT.KW_BETWEEN,
    "is":      _TT.KW_IS,
    "where":   _TT.KW_WHERE,
    "if":      _TT.KW_IF,
    "then":    _TT.KW_THEN,
    "else":    _TT.KW_ELSE,
    "true":    _TT.KW_TRUE,
    "false":   _TT.KW_FALSE,
    "null":    _TT.KW_NULL,
}

# Identifiers that become function calls when immediately followed by '('
_FUNC_NAMES = frozenset({
    "count", "all", "any", "none",
    "length", "len", "sum", "min", "max", "avg",
    "present", "exists",
})


@dataclass(frozen=True)
class _Token:
    tt: _TT
    value: str
    pos: int


def _tokenize(text: str) -> list[_Token]:  # noqa: C901  (complex by necessity)
    tokens: list[_Token] = []
    i = 0
    n = len(text)

    while i < n:
        # Skip whitespace
        if text[i].isspace():
            i += 1
            continue

        # Number literal
        if text[i].isdigit():
            j = i
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] == "." and j + 1 < n and text[j + 1].isdigit():
                j += 1
                while j < n and text[j].isdigit():
                    j += 1
            tokens.append(_Token(_TT.NUMBER, text[i:j], i))
            i = j
            continue

        # String literal (single or double quoted)
        if text[i] in ('"', "'"):
            quote = text[i]
            j = i + 1
            while j < n and text[j] != quote:
                if text[j] == "\\" and j + 1 < n:
                    j += 1  # skip escaped char
                j += 1
            if j >= n:
                raise ExpressionError("Unterminated string literal", pos=i)
            tokens.append(_Token(_TT.STRING, text[i + 1 : j], i))
            i = j + 1
            continue

        # Identifier, keyword, or dotted field path (possibly with projection)
        if text[i].isalpha() or text[i] == "_":
            start = i
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            path = text[i:j]
            i = j

            # Extend path along '.' segments (supports dotted paths & numeric indices)
            while i < n and text[i] == ".":
                k = i + 1
                if k < n and (text[k].isalpha() or text[k] == "_" or text[k].isdigit()):
                    m = k
                    while m < n and (text[m].isalnum() or text[m] == "_"):
                        m += 1
                    path = path + "." + text[k:m]
                    i = m
                else:
                    break  # '.' not followed by valid segment

            # Check for list projection: path[].subfield
            if (
                i < n
                and text[i] == "["
                and i + 1 < n
                and text[i + 1] == "]"
                and i + 2 < n
                and text[i + 2] == "."
            ):
                k = i + 3
                if k < n and (text[k].isalpha() or text[k] == "_"):
                    m = k
                    # Allow dotted subfield after [], e.g. data.items[].addr.city
                    while m < n and (text[m].isalnum() or text[m] == "_" or text[m] == "."):
                        m += 1
                    # Trim trailing dot if any
                    subfield = text[k:m].rstrip(".")
                    tokens.append(_Token(_TT.PROJECTION, f"{path}[].{subfield}", start))
                    i = m
                    continue

            # Map single-word tokens to keywords; multi-segment paths stay IDENT
            if "." not in path:
                tt = _KEYWORDS.get(path, _TT.IDENT)
            else:
                tt = _TT.IDENT
            tokens.append(_Token(tt, path, start))
            continue

        # Two-char operators (must be checked before single-char)
        two = text[i : i + 2]
        if two == "==":
            tokens.append(_Token(_TT.EQ,  "==", i)); i += 2; continue
        if two == "!=":
            tokens.append(_Token(_TT.NEQ, "!=", i)); i += 2; continue
        if two == ">=":
            tokens.append(_Token(_TT.GTE, ">=", i)); i += 2; continue
        if two == "<=":
            tokens.append(_Token(_TT.LTE, "<=", i)); i += 2; continue

        # Single-char operators / punctuation
        _SINGLE: dict[str, _TT] = {
            ">": _TT.GT, "<": _TT.LT,
            "+": _TT.PLUS, "-": _TT.MINUS,
            "*": _TT.STAR, "/": _TT.SLASH,
            "(": _TT.LPAREN, ")": _TT.RPAREN,
            "[": _TT.LBRACKET, "]": _TT.RBRACKET,
            ",": _TT.COMMA,
        }
        c = text[i]
        if c in _SINGLE:
            tokens.append(_Token(_SINGLE[c], c, i))
            i += 1
            continue

        raise ExpressionError(f"Unexpected character '{c}'", pos=i)

    tokens.append(_Token(_TT.EOF, "", n))
    return tokens


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

@dataclass
class _NumberLit:
    value: float

@dataclass
class _StringLit:
    value: str

@dataclass
class _BoolLit:
    value: bool

@dataclass
class _NullLit:
    pass

@dataclass
class _ListLit:
    items: list[Any]

@dataclass
class _FieldRef:
    path: str

@dataclass
class _ProjectionRef:
    array_path: str
    element_field: str

@dataclass
class _BinOp:
    op: str        # +, -, *, /
    left: Any
    right: Any

@dataclass
class _UnaryMinus:
    operand: Any

@dataclass
class _Compare:
    op: str        # ==, !=, >, >=, <, <=
    left: Any
    right: Any

@dataclass
class _InOp:
    value: Any
    collection: Any
    negated: bool = False

@dataclass
class _BetweenOp:
    value: Any
    low: Any
    high: Any

@dataclass
class _IsPresent:
    field_ref: Any     # _FieldRef expected
    negated: bool = False

@dataclass
class _IsEmpty:
    field_ref: Any     # _FieldRef expected
    negated: bool = False

@dataclass
class _BoolAnd:
    left: Any
    right: Any

@dataclass
class _BoolOr:
    left: Any
    right: Any

@dataclass
class _BoolNot:
    operand: Any

@dataclass
class _FuncCall:
    name: str          # length, len, sum, min, max, avg, present, exists
    arg: Any           # _FieldRef or _ProjectionRef

@dataclass
class _QuantExpr:
    kind: str          # all, any, none, count
    array_path: str
    predicate: Any     # element-relative boolean expr, or None

@dataclass
class _Ternary:
    condition: Any
    then_expr: Any
    else_expr: Any     # None → vacuous pass when antecedent is false


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _peek2(self) -> _Token:
        idx = self._pos + 1
        return self._tokens[idx] if idx < len(self._tokens) else self._tokens[-1]

    def _consume(self, expected: _TT | None = None) -> _Token:
        tok = self._tokens[self._pos]
        if expected is not None and tok.tt != expected:
            raise ExpressionError(
                f"Expected '{expected.value}' but got '{tok.value}'", pos=tok.pos
            )
        self._pos += 1
        return tok

    def parse(self) -> Any:
        node = self._expr()
        tok = self._peek()
        if tok.tt != _TT.EOF:
            raise ExpressionError(
                f"Unexpected '{tok.value}' after expression", pos=tok.pos
            )
        return node

    # ---- grammar productions (loosest to tightest) -------------------------

    def _expr(self) -> Any:
        return self._ternary()

    def _ternary(self) -> Any:
        if self._peek().tt == _TT.KW_IF:
            self._consume()
            cond = self._or()
            if self._peek().tt != _TT.KW_THEN:
                raise ExpressionError(
                    "'if' requires 'then'", pos=self._peek().pos
                )
            self._consume()  # 'then'
            then_expr = self._or()
            else_expr: Any = None
            if self._peek().tt == _TT.KW_ELSE:
                self._consume()
                else_expr = self._or()
            return _Ternary(cond, then_expr, else_expr)
        return self._or()

    def _or(self) -> Any:
        left = self._and()
        while self._peek().tt == _TT.KW_OR:
            self._consume()
            right = self._and()
            left = _BoolOr(left, right)
        return left

    def _and(self) -> Any:
        left = self._not()
        while self._peek().tt == _TT.KW_AND:
            self._consume()
            right = self._not()
            left = _BoolAnd(left, right)
        return left

    def _not(self) -> Any:
        if self._peek().tt == _TT.KW_NOT:
            self._consume()
            operand = self._not()
            return _BoolNot(operand)
        return self._compare()

    def _compare(self) -> Any:  # noqa: C901
        left = self._add()
        tok = self._peek()

        _OP_MAP: dict[_TT, str] = {
            _TT.EQ: "==", _TT.NEQ: "!=",
            _TT.GT: ">",  _TT.GTE: ">=",
            _TT.LT: "<",  _TT.LTE: "<=",
        }
        if tok.tt in _OP_MAP:
            self._consume()
            right = self._add()
            return _Compare(_OP_MAP[tok.tt], left, right)

        # 'not in' — 'not' token appears AFTER the left-hand value
        if tok.tt == _TT.KW_NOT and self._peek2().tt == _TT.KW_IN:
            self._consume()  # not
            self._consume()  # in
            right = self._add()
            return _InOp(left, right, negated=True)

        if tok.tt == _TT.KW_IN:
            self._consume()
            right = self._add()
            return _InOp(left, right)

        if tok.tt == _TT.KW_BETWEEN:
            self._consume()
            low = self._add()
            if self._peek().tt != _TT.KW_AND:
                raise ExpressionError(
                    "'between' requires 'and' to separate the bounds",
                    pos=self._peek().pos,
                )
            self._consume()  # 'and' for between
            high = self._add()
            return _BetweenOp(left, low, high)

        if tok.tt == _TT.KW_IS:
            self._consume()
            negated = False
            if self._peek().tt == _TT.KW_NOT:
                self._consume()
                negated = True
            nxt = self._peek()
            # 'present' may arrive as IDENT (not a keyword)
            if nxt.tt == _TT.IDENT and nxt.value.lower() == "present":
                self._consume()
                return _IsPresent(left, negated)
            # 'empty' may arrive as IDENT (not a keyword)
            if nxt.tt == _TT.IDENT and nxt.value.lower() == "empty":
                self._consume()
                return _IsEmpty(left, negated)
            raise ExpressionError(
                "'is' must be followed by 'present' or 'empty'", pos=nxt.pos
            )

        return left

    def _add(self) -> Any:
        left = self._mul()
        while self._peek().tt in (_TT.PLUS, _TT.MINUS):
            op = self._consume().value
            right = self._mul()
            left = _BinOp(op, left, right)
        return left

    def _mul(self) -> Any:
        left = self._unary()
        while self._peek().tt in (_TT.STAR, _TT.SLASH):
            op = self._consume().value
            right = self._unary()
            left = _BinOp(op, left, right)
        return left

    def _unary(self) -> Any:
        if self._peek().tt == _TT.MINUS:
            self._consume()
            return _UnaryMinus(self._unary())
        return self._primary()

    def _primary(self) -> Any:  # noqa: C901
        tok = self._peek()

        if tok.tt == _TT.LPAREN:
            self._consume()
            expr = self._expr()
            if self._peek().tt != _TT.RPAREN:
                raise ExpressionError(
                    "Expected ')' to close '('", pos=self._peek().pos
                )
            self._consume()
            return expr

        if tok.tt == _TT.NUMBER:
            self._consume()
            return _NumberLit(float(tok.value))

        if tok.tt == _TT.STRING:
            self._consume()
            return _StringLit(tok.value)

        if tok.tt == _TT.KW_TRUE:
            self._consume(); return _BoolLit(True)

        if tok.tt == _TT.KW_FALSE:
            self._consume(); return _BoolLit(False)

        if tok.tt == _TT.KW_NULL:
            self._consume(); return _NullLit()

        if tok.tt == _TT.LBRACKET:
            return self._list_literal()

        if tok.tt == _TT.PROJECTION:
            self._consume()
            bracket_idx = tok.value.index("[].")
            return _ProjectionRef(
                tok.value[:bracket_idx],
                tok.value[bracket_idx + 3 :],
            )

        if tok.tt == _TT.IDENT:
            name = tok.value
            # Function call: IDENT immediately followed by '('
            if self._peek2().tt == _TT.LPAREN and name.lower() in _FUNC_NAMES:
                return self._func_call(name.lower())
            self._consume()
            return _FieldRef(name)

        raise ExpressionError(
            f"Unexpected '{tok.value}' — expected a value, field, or '('",
            pos=tok.pos,
        )

    def _list_literal(self) -> Any:
        self._consume(_TT.LBRACKET)
        items: list[Any] = []
        while self._peek().tt != _TT.RBRACKET:
            if self._peek().tt == _TT.EOF:
                raise ExpressionError("Unterminated list '[...]'")
            # Bare single-word IDENTs in lists are treated as string values so
            # authors can write  data.cat in [Operational, Financial]  naturally.
            if (
                self._peek().tt == _TT.IDENT
                and "." not in self._peek().value
                and self._peek2().tt in (_TT.COMMA, _TT.RBRACKET)
            ):
                t = self._consume()
                items.append(_StringLit(t.value))
            else:
                items.append(self._expr())
            if self._peek().tt == _TT.COMMA:
                self._consume()
            elif self._peek().tt != _TT.RBRACKET:
                raise ExpressionError(
                    "Expected ',' or ']' in list literal", pos=self._peek().pos
                )
        self._consume(_TT.RBRACKET)
        return _ListLit(items)

    def _func_call(self, func_name: str) -> Any:
        self._consume()              # consume the function name IDENT
        self._consume(_TT.LPAREN)

        # Quantifiers: count / all / any / none
        if func_name in ("count", "all", "any", "none"):
            if self._peek().tt != _TT.IDENT:
                raise ExpressionError(
                    f"'{func_name}' expects a field path for the array",
                    pos=self._peek().pos,
                )
            array_path = self._consume().value
            predicate: Any = None
            if self._peek().tt == _TT.KW_WHERE:
                self._consume()
                predicate = self._expr()
            self._consume(_TT.RPAREN)
            return _QuantExpr(func_name, array_path, predicate)

        # Presence functions: present / exists
        if func_name in ("present", "exists"):
            arg = self._primary()
            self._consume(_TT.RPAREN)
            return _IsPresent(arg, negated=False)

        # Aggregate / length functions: length / len / sum / min / max / avg
        tok = self._peek()
        if tok.tt == _TT.PROJECTION:
            agg_arg: Any = self._primary()
        elif tok.tt == _TT.IDENT:
            self._consume()
            agg_arg = _FieldRef(tok.value)
        else:
            raise ExpressionError(
                f"'{func_name}' expects a field path or projection "
                f"(e.g. data.list[].field)",
                pos=tok.pos,
            )
        self._consume(_TT.RPAREN)
        return _FuncCall(func_name, agg_arg)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

@dataclass
class _EvalResult:
    value: Any
    missing: bool = False
    reason: str = ""


def _eval_node(node: Any, data: Any, depth: int = 0) -> _EvalResult:  # noqa: C901
    if depth > _MAX_DEPTH:
        raise ExpressionError("Expression is too deeply nested (possible loop)")

    if isinstance(node, _NumberLit):
        return _EvalResult(node.value, reason=str(node.value))

    if isinstance(node, _StringLit):
        return _EvalResult(node.value, reason=f"'{node.value}'")

    if isinstance(node, _BoolLit):
        return _EvalResult(node.value, reason=str(node.value).lower())

    if isinstance(node, _NullLit):
        return _EvalResult(None, reason="null")

    if isinstance(node, _ListLit):
        values: list[Any] = []
        for item in node.items:
            r = _eval_node(item, data, depth + 1)
            if r.missing:
                return r
            values.append(r.value)
        return _EvalResult(values, reason=repr(values))

    if isinstance(node, _FieldRef):
        value = resolve_path(data, node.path)
        if value is MISSING:
            return _EvalResult(
                None, missing=True, reason=f"field '{node.path}' is missing"
            )
        return _EvalResult(value, reason=f"{node.path} ({_fmt_val(value)})")

    if isinstance(node, _ProjectionRef):
        array = resolve_path(data, node.array_path)
        if array is MISSING:
            return _EvalResult(
                None, missing=True,
                reason=f"array '{node.array_path}' is missing",
            )
        if not isinstance(array, list):
            return _EvalResult(
                None, missing=True,
                reason=f"'{node.array_path}' is not a list",
            )
        projected: list[Any] = []
        for idx, elem in enumerate(array):
            v = resolve_path(elem, node.element_field)
            if v is MISSING:
                return _EvalResult(
                    None, missing=True,
                    reason=(
                        f"{node.array_path}[{idx}].{node.element_field} is missing"
                    ),
                )
            projected.append(v)
        return _EvalResult(
            projected,
            reason=f"{node.array_path}[].{node.element_field}",
        )

    if isinstance(node, _IsPresent):
        if not isinstance(node.field_ref, _FieldRef):
            raise ExpressionError(
                "'is present' requires a direct field path, not an expression"
            )
        present = resolve_path(data, node.field_ref.path) is not MISSING
        result = present if not node.negated else not present
        adj = "present" if present else "absent"
        return _EvalResult(result, reason=f"field '{node.field_ref.path}' is {adj}")

    if isinstance(node, _IsEmpty):
        if not isinstance(node.field_ref, _FieldRef):
            raise ExpressionError(
                "'is empty' requires a direct field path, not an expression"
            )
        value = resolve_path(data, node.field_ref.path)
        empty = is_empty(value)
        result = empty if not node.negated else not empty
        adj = "empty" if empty else "non-empty"
        return _EvalResult(result, reason=f"field '{node.field_ref.path}' is {adj}")

    if isinstance(node, _UnaryMinus):
        r = _eval_node(node.operand, data, depth + 1)
        if r.missing:
            return r
        n = _as_number(r.value)
        if n is None:
            return _EvalResult(
                None, missing=True,
                reason=f"unary minus requires a number, got {r.value!r}",
            )
        return _EvalResult(-n, reason=f"-({r.reason})")

    if isinstance(node, _BinOp):
        lr = _eval_node(node.left,  data, depth + 1)
        if lr.missing:
            return lr
        rr = _eval_node(node.right, data, depth + 1)
        if rr.missing:
            return rr
        ln, rn = _as_number(lr.value), _as_number(rr.value)
        if ln is None or rn is None:
            return _EvalResult(
                None, missing=True,
                reason=(
                    f"'{node.op}' requires numeric values, "
                    f"got {lr.value!r} and {rr.value!r}"
                ),
            )
        try:
            if node.op == "+":
                result_val: float = ln + rn
            elif node.op == "-":
                result_val = ln - rn
            elif node.op == "*":
                result_val = ln * rn
            else:  # "/"
                if rn == 0.0:
                    return _EvalResult(
                        None, missing=True, reason="division by zero"
                    )
                result_val = ln / rn
        except (ArithmeticError, OverflowError) as exc:
            return _EvalResult(None, missing=True, reason=str(exc))
        return _EvalResult(
            result_val, reason=f"({lr.reason} {node.op} {rr.reason})"
        )

    if isinstance(node, _Compare):
        lr = _eval_node(node.left,  data, depth + 1)
        if lr.missing:
            return lr
        rr = _eval_node(node.right, data, depth + 1)
        if rr.missing:
            return rr
        cmp = _compare(lr.value, rr.value)
        if cmp is None:
            if node.op == "==":
                passed = lr.value == rr.value
            elif node.op == "!=":
                passed = lr.value != rr.value
            else:
                return _EvalResult(
                    False,
                    reason=f"cannot compare {lr.value!r} {node.op} {rr.value!r}",
                )
        else:
            _CMP: dict[str, bool] = {
                "==": cmp == 0, "!=": cmp != 0,
                ">":  cmp > 0,  ">=": cmp >= 0,
                "<":  cmp < 0,  "<=": cmp <= 0,
            }
            passed = _CMP[node.op]
        verb = "satisfies" if passed else "does not satisfy"
        return _EvalResult(
            passed, reason=f"{lr.reason} {verb} {node.op} {rr.reason}"
        )

    if isinstance(node, _InOp):
        lr = _eval_node(node.value,      data, depth + 1)
        if lr.missing:
            return lr
        rr = _eval_node(node.collection, data, depth + 1)
        if rr.missing:
            return rr
        col = rr.value
        found = lr.value in col if isinstance(col, (list, tuple, set, str)) else False
        result = (not found) if node.negated else found
        op_str = "not in" if node.negated else "in"
        return _EvalResult(result, reason=f"{lr.reason} {op_str} {rr.reason}")

    if isinstance(node, _BetweenOp):
        vr = _eval_node(node.value, data, depth + 1)
        if vr.missing:
            return vr
        lr = _eval_node(node.low,   data, depth + 1)
        if lr.missing:
            return lr
        hr = _eval_node(node.high,  data, depth + 1)
        if hr.missing:
            return hr
        low_cmp  = _compare(vr.value, lr.value)
        high_cmp = _compare(vr.value, hr.value)
        passed = (
            low_cmp  is not None and low_cmp  >= 0
            and high_cmp is not None and high_cmp <= 0
        )
        return _EvalResult(
            passed,
            reason=f"{vr.reason} between {lr.reason} and {hr.reason}",
        )

    if isinstance(node, _BoolAnd):
        lr = _eval_node(node.left, data, depth + 1)
        # Short-circuit: definite FALSE without missing terminates immediately
        if not lr.missing and not lr.value:
            return _EvalResult(False, reason=lr.reason)
        rr = _eval_node(node.right, data, depth + 1)
        if lr.missing or rr.missing:
            return _EvalResult(
                False, missing=True,
                reason="one or more conditions could not be evaluated (missing data)",
            )
        passed = bool(lr.value) and bool(rr.value)
        return _EvalResult(passed, reason=lr.reason if passed else rr.reason)

    if isinstance(node, _BoolOr):
        lr = _eval_node(node.left, data, depth + 1)
        # Short-circuit: definite TRUE without missing terminates immediately
        if not lr.missing and lr.value:
            return _EvalResult(True, reason=lr.reason)
        rr = _eval_node(node.right, data, depth + 1)
        if not lr.missing and lr.value:
            return _EvalResult(True, reason=lr.reason)
        if not rr.missing and rr.value:
            return _EvalResult(True, reason=rr.reason)
        if lr.missing or rr.missing:
            return _EvalResult(
                False, missing=True,
                reason="no condition satisfied and data was missing",
            )
        return _EvalResult(False, reason="neither condition was satisfied")

    if isinstance(node, _BoolNot):
        r = _eval_node(node.operand, data, depth + 1)
        if r.missing:
            return r
        return _EvalResult(not bool(r.value), reason=f"NOT ({r.reason})")

    if isinstance(node, _Ternary):
        cr = _eval_node(node.condition, data, depth + 1)
        if cr.missing:
            return cr
        if cr.value:
            return _eval_node(node.then_expr, data, depth + 1)
        if node.else_expr is not None:
            return _eval_node(node.else_expr, data, depth + 1)
        return _EvalResult(True, reason="precondition not met; rule not applicable")

    if isinstance(node, _FuncCall):
        arg_result = _eval_node(node.arg, data, depth + 1)
        if arg_result.missing:
            return arg_result
        val = arg_result.value
        name = node.name

        if name in ("length", "len"):
            try:
                length = len(val)  # type: ignore[arg-type]
                return _EvalResult(float(length), reason=f"length = {length}")
            except TypeError:
                return _EvalResult(
                    None, missing=True,
                    reason=f"length() requires a string or list, got {type(val).__name__}",
                )

        if name in ("sum", "min", "max", "avg"):
            if not isinstance(val, list):
                return _EvalResult(
                    None, missing=True,
                    reason=(
                        f"{name}() requires a list projection "
                        f"(e.g. data.items[].field), got {type(val).__name__}"
                    ),
                )
            nums = [_as_number(v) for v in val]
            if any(n is None for n in nums):
                bad = [v for v, nv in zip(val, nums) if nv is None]
                return _EvalResult(
                    None, missing=True,
                    reason=f"{name}() requires all numeric values; non-numeric: {bad!r}",
                )
            float_nums = [float(nv) for nv in nums if nv is not None]
            if not float_nums:
                if name in ("min", "max"):
                    return _EvalResult(
                        None, missing=True,
                        reason=f"{name}() cannot operate on an empty list",
                    )
                return _EvalResult(0.0, reason=f"{name}([]) = 0")
            if name == "sum":
                s = sum(float_nums)
                return _EvalResult(s, reason=f"sum = {s}")
            if name == "min":
                m = min(float_nums)
                return _EvalResult(m, reason=f"min = {m}")
            if name == "max":
                m = max(float_nums)
                return _EvalResult(m, reason=f"max = {m}")
            # avg
            avg = sum(float_nums) / len(float_nums)
            return _EvalResult(avg, reason=f"avg = {avg}")

        raise ExpressionError(f"Unknown function '{node.name}'")

    if isinstance(node, _QuantExpr):
        array = resolve_path(data, node.array_path)
        if array is MISSING:
            return _EvalResult(
                None, missing=True,
                reason=f"array '{node.array_path}' is missing",
            )
        if not isinstance(array, list):
            return _EvalResult(
                None, missing=True,
                reason=f"'{node.array_path}' is not a list",
            )

        # count() with no predicate = raw length
        if node.kind == "count" and node.predicate is None:
            cnt = len(array)
            return _EvalResult(float(cnt), reason=f"count({node.array_path}) = {cnt}")

        matched = 0
        any_missing = False
        failing_reason = ""
        for idx, element in enumerate(array):
            if node.predicate is None:
                # all / any / none without predicate: truthy element test
                truthy = bool(element) if element is not None else False
                if truthy:
                    matched += 1
                elif not failing_reason:
                    failing_reason = f"element {idx} is falsy"
            else:
                res = _eval_node(node.predicate, element, depth + 1)
                if res.missing:
                    any_missing = True
                elif bool(res.value):
                    matched += 1
                elif not failing_reason:
                    failing_reason = f"element {idx}: {res.reason}"

        total = len(array)

        if node.kind == "count":
            return _EvalResult(
                float(matched),
                reason=f"count({node.array_path} where ...) = {matched}",
            )

        if node.kind == "all":
            if any_missing:
                return _EvalResult(
                    None, missing=True,
                    reason=f"'{node.array_path}' has elements with missing data",
                )
            if matched == total:
                return _EvalResult(
                    True,
                    reason=(
                        f"all {total} element(s) of '{node.array_path}' "
                        f"satisfy the condition"
                    ),
                )
            return _EvalResult(
                False, reason=f"'{node.array_path}': {failing_reason}"
            )

        if node.kind == "any":
            if matched > 0:
                return _EvalResult(
                    True,
                    reason=(
                        f"{matched} element(s) of '{node.array_path}' "
                        f"satisfy the condition"
                    ),
                )
            if any_missing:
                return _EvalResult(
                    None, missing=True,
                    reason=(
                        f"no element of '{node.array_path}' matched "
                        f"and some had missing data"
                    ),
                )
            return _EvalResult(
                False,
                reason=f"no element of '{node.array_path}' satisfies the condition",
            )

        if node.kind == "none":
            if matched > 0:
                return _EvalResult(
                    False,
                    reason=(
                        f"{matched} element(s) of '{node.array_path}' "
                        f"unexpectedly satisfy the condition"
                    ),
                )
            if any_missing:
                return _EvalResult(
                    None, missing=True,
                    reason=f"'{node.array_path}' had elements with missing data",
                )
            return _EvalResult(
                True,
                reason=f"no element of '{node.array_path}' satisfies the condition",
            )

        raise ExpressionError(f"Unknown quantifier kind '{node.kind}'")

    raise ExpressionError(f"Unknown AST node type: {type(node).__name__}")


def _fmt_val(value: Any) -> str:
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


# ---------------------------------------------------------------------------
# Field-path collector (for --fields / field discovery)
# ---------------------------------------------------------------------------

def _collect_ast_fields(
    node: Any, result: list[tuple[str, str]]
) -> None:
    if isinstance(node, _FieldRef):
        result.append((node.path, "ref"))

    elif isinstance(node, _ProjectionRef):
        result.append((f"{node.array_path}[].{node.element_field}", "projection"))

    elif isinstance(node, _IsPresent):
        if isinstance(node.field_ref, _FieldRef):
            result.append((node.field_ref.path, "present"))

    elif isinstance(node, _IsEmpty):
        if isinstance(node.field_ref, _FieldRef):
            result.append((node.field_ref.path, "empty"))

    elif isinstance(node, _FuncCall):
        _collect_ast_fields(node.arg, result)

    elif isinstance(node, _QuantExpr):
        result.append((node.array_path, node.kind))
        if node.predicate is not None:
            inner: list[tuple[str, str]] = []
            _collect_ast_fields(node.predicate, inner)
            for path, op in inner:
                result.append((f"{node.array_path}[].{path}", op))

    elif isinstance(node, _BinOp):
        _collect_ast_fields(node.left,  result)
        _collect_ast_fields(node.right, result)

    elif isinstance(node, _Compare):
        _collect_ast_fields(node.left,  result)
        _collect_ast_fields(node.right, result)

    elif isinstance(node, _InOp):
        _collect_ast_fields(node.value,      result)
        _collect_ast_fields(node.collection, result)

    elif isinstance(node, _BetweenOp):
        _collect_ast_fields(node.value, result)
        _collect_ast_fields(node.low,   result)
        _collect_ast_fields(node.high,  result)

    elif isinstance(node, (_BoolAnd, _BoolOr)):
        _collect_ast_fields(node.left,  result)
        _collect_ast_fields(node.right, result)

    elif isinstance(node, (_BoolNot, _UnaryMinus)):
        _collect_ast_fields(node.operand, result)

    elif isinstance(node, _Ternary):
        _collect_ast_fields(node.condition, result)
        _collect_ast_fields(node.then_expr, result)
        if node.else_expr is not None:
            _collect_ast_fields(node.else_expr, result)

    elif isinstance(node, _ListLit):
        for item in node.items:
            _collect_ast_fields(item, result)

    # Literals (_NumberLit, _StringLit, _BoolLit, _NullLit) have no field refs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_expression(text: str) -> Any:
    """Parse *text* and return the AST root.

    Raises :exc:`ExpressionError` on syntax errors.  Used by the validator to
    catch problems without evaluating against real data.
    """
    return _Parser(_tokenize(text)).parse()


def evaluate_expression(text: str, data: Any) -> "ConditionResult":  # type: ignore[name-defined]
    """Evaluate *text* as a boolean predicate against *data*.

    Returns a :class:`~checks.conditions.ConditionResult` including ``missing``
    propagation so the engine's ``on_missing`` policy applies correctly.

    Raises :exc:`~checks.conditions.RuleFormatError` when the expression is
    syntactically or structurally invalid (not a boolean predicate).
    """
    # Lazy import avoids a circular dependency (conditions imports expressions lazily)
    from .conditions import ConditionResult, RuleFormatError  # noqa: PLC0415

    try:
        ast = parse_expression(text)
    except ExpressionError as exc:
        raise RuleFormatError(f"Expression syntax error: {exc}") from exc

    try:
        result = _eval_node(ast, data)
    except ExpressionError as exc:
        raise RuleFormatError(f"Expression evaluation error: {exc}") from exc

    if result.missing:
        return ConditionResult(
            False,
            result.reason or "missing data in expression",
            missing=True,
        )

    if not isinstance(result.value, bool):
        raise RuleFormatError(
            f"Expression must produce a boolean (true/false) result but evaluated "
            f"to {type(result.value).__name__} ({result.value!r}). "
            f"Hint: add a comparison, e.g. '> 0' or '== 100'."
        )

    reason = result.reason or (
        "expression is true" if result.value else "expression is false"
    )
    return ConditionResult(result.value, reason)


def collect_expression_fields(text: str) -> list[tuple[str, str]]:
    """Return ``(field_path, operation)`` pairs referenced in *text*.

    Used by the ``--fields`` command to discover required input fields without
    running the engine.  Field paths inside quantifier predicates are prefixed
    with the array path and ``[]``, e.g.
    ``data.beneficiaries[].share_percentage``.

    Returns an empty list if the expression cannot be parsed (the validator
    will surface the parse error separately).
    """
    try:
        ast = parse_expression(text)
    except ExpressionError:
        return []
    result: list[tuple[str, str]] = []
    _collect_ast_fields(ast, result)
    return result
