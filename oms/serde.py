"""직렬화 — 도메인 객체 ↔ 저장 가능한 dict.

이 계층 덕분에 도메인 모델은 datetime/Enum 을 그대로 쓰고,
Repository 는 저장만 신경 쓰면 됩니다.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints


def _encode(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _encode(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_encode(x) for x in v]
    return v


def to_data(obj: Any) -> dict[str, Any]:
    """dataclass → 저장용 dict (id 제외는 호출측에서 처리)."""
    return {f.name: _encode(getattr(obj, f.name)) for f in dataclasses.fields(obj)}


def _decode(typ: Any, v: Any) -> Any:
    if v is None:
        return None
    origin = get_origin(typ)
    if origin is Union:  # Optional[X] 등
        args = [a for a in get_args(typ) if a is not type(None)]
        return _decode(args[0], v) if args else v
    if isinstance(typ, type) and issubclass(typ, Enum):
        return typ(v)
    if typ is datetime:
        return datetime.fromisoformat(v)
    return v


def from_data(cls: type, d: dict[str, Any]) -> Any:
    """저장용 dict → dataclass 인스턴스."""
    hints = get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name in d:
            kwargs[f.name] = _decode(hints.get(f.name, Any), d[f.name])
    return cls(**kwargs)
