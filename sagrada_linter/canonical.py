"""Canonical JSON serializer (RFC 8785–compatible).

Rules (see SCHEMA.md §4):
  1. Object keys sorted by UTF-16 code-unit order (== lex order on
     ASCII subset; for non-ASCII keys we use the same code-unit sort
     as JavaScript's default Array.sort()).
  2. No whitespace.
  3. Strings are NFC-normalized; non-ASCII escaped as \\uXXXX (lower
     hex). Surrogate pairs for codepoints > U+FFFF.
  4. Numbers: integers as-is; floats via shortest-roundtrip repr.
  5. null / true / false as bare literals.
  6. No trailing newline.

Mirror implementation: typescript/src/canonical.ts.
"""
from __future__ import annotations

import math
import unicodedata
from typing import Any


def _utf16_codeunits(s: str) -> list[int]:
    """Return the UTF-16 code units of `s` (BMP = 1 unit, supplementary = 2)."""
    out: list[int] = []
    for ch in s:
        cp = ord(ch)
        if cp <= 0xFFFF:
            out.append(cp)
        else:
            cp -= 0x10000
            out.append(0xD800 + (cp >> 10))
            out.append(0xDC00 + (cp & 0x3FF))
    return out


def _utf16_key(s: str) -> tuple[int, ...]:
    return tuple(_utf16_codeunits(s))


def _escape_string(s: str) -> str:
    """RFC 8785 / RFC 8259 string escaping with \\uXXXX for non-ASCII.

    - Always NFC-normalize first.
    - Mandatory escapes: \" \\ and U+0000..U+001F.
    - All other ASCII printable (0x20..0x7E except \" \\) emitted verbatim.
    - All non-ASCII emitted as \\uXXXX (lowercase hex). Supplementary
      planes use surrogate pairs.
    """
    s = unicodedata.normalize("NFC", s)
    out: list[str] = ['"']
    for ch in s:
        cp = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif cp < 0x20:
            out.append(f"\\u{cp:04x}")
        elif cp < 0x7F:
            out.append(ch)
        elif cp <= 0xFFFF:
            out.append(f"\\u{cp:04x}")
        else:
            # Supplementary plane — surrogate pair
            v = cp - 0x10000
            hi = 0xD800 + (v >> 10)
            lo = 0xDC00 + (v & 0x3FF)
            out.append(f"\\u{hi:04x}\\u{lo:04x}")
    out.append('"')
    return "".join(out)


def _format_number(n: int | float) -> str:
    if isinstance(n, bool):  # bool is a subclass of int in Python
        return "true" if n else "false"
    if isinstance(n, int):
        return str(n)
    if isinstance(n, float):
        if math.isnan(n) or math.isinf(n):
            raise ValueError(f"Non-finite number cannot be canonicalized: {n}")
        if n == 0.0:
            # Always emit "0" for both +0.0 and -0.0 to match
            # JSON.stringify(0) and avoid signed-zero divergence.
            return "0"
        if n.is_integer() and abs(n) < 1e16:
            # Integer-valued floats emit as integer literal — matches
            # JSON.stringify(1.0) === "1" in JavaScript.
            return str(int(n))
        # Shortest round-trip float repr.
        s = repr(n)
        # Python's repr gives e.g. "0.1" or "1e-07"; normalize "1e-07" -> "1e-7"
        # to match ECMA ToString.
        if "e" in s or "E" in s:
            mantissa, _, exp = s.partition("e") if "e" in s else s.partition("E")
            sign = ""
            if exp.startswith("+"):
                exp = exp[1:]
            if exp.startswith("-"):
                sign = "-"
                exp = exp[1:]
            exp = exp.lstrip("0") or "0"
            s = f"{mantissa}e{sign}{exp}"
        return s
    raise TypeError(f"Unsupported numeric type: {type(n)}")


def _canonical(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _format_number(value)
    if isinstance(value, str):
        return _escape_string(value)
    if isinstance(value, dict):
        # sort keys by utf-16 code unit order (matches JS Array.sort default)
        keys = sorted(value.keys(), key=_utf16_key)
        parts = []
        for k in keys:
            if not isinstance(k, str):
                raise TypeError(f"Object keys must be strings, got {type(k)}")
            parts.append(_escape_string(k) + ":" + _canonical(value[k]))
        return "{" + ",".join(parts) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    # BaseModel / dataclass — caller should have dumped to dict first.
    raise TypeError(f"Cannot canonicalize value of type {type(value)}")


def canonical_json(value: Any) -> bytes:
    """Return the canonical UTF-8 byte string of `value`.

    `value` is typically a Receipt model dumped via `model.model_dump()`
    or a plain dict. This function does NOT accept Pydantic instances
    directly — callers should `.model_dump(mode='python')` first to
    avoid silent coercions.
    """
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    return _canonical(value).encode("utf-8")
