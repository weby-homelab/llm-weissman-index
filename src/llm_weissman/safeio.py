"""Safe bounded data loaders with duplicate-key rejection."""

from __future__ import annotations

import json
from typing import Any

import yaml

MAX_NODES = 100_000
MAX_DEPTH = 50
MAX_STRING_LENGTH = 1_000_000
MAX_TEXT_LENGTH = 5 * 1024 * 1024


class DuplicateKeyError(ValueError):
    """Raised when an object contains ambiguous duplicate keys."""


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise DuplicateKeyError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def unique_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")


def load_json(text: str) -> Any:
    if len(text.encode("utf-8")) > MAX_TEXT_LENGTH:
        raise ValueError("input text is too large")
    return enforce_bounds(
        json.loads(
            text,
            object_pairs_hook=unique_json_pairs,
            parse_constant=reject_json_constant,
        )
    )


def load_yaml(text: str) -> Any:
    if len(text.encode("utf-8")) > MAX_TEXT_LENGTH:
        raise ValueError("input text is too large")
    return enforce_bounds(yaml.load(text, Loader=_UniqueSafeLoader))


def enforce_bounds(value: Any) -> Any:
    """Reject pathological nesting, node counts, strings, and recursive aliases."""

    active: set[int] = set()
    nodes = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            raise ValueError("input contains too many nodes")
        if depth > MAX_DEPTH:
            raise ValueError("input nesting is too deep")
        if isinstance(item, str):
            if len(item) > MAX_STRING_LENGTH:
                raise ValueError("input string is too long")
            return
        if isinstance(item, float) or not isinstance(
            item, (type(None), bool, int, dict, list, tuple)
        ):
            raise ValueError(f"unsupported scalar type: {type(item).__name__}")
        if not isinstance(item, (dict, list, tuple)):
            return
        identity = id(item)
        if identity in active:
            raise ValueError("recursive input aliases are not supported")
        active.add(identity)
        children = item.items() if isinstance(item, dict) else enumerate(item)
        for key, child in children:
            if isinstance(item, dict):
                if not isinstance(key, str):
                    raise ValueError("object keys must be strings")
                visit(key, depth + 1)
            visit(child, depth + 1)
        active.remove(identity)

    visit(value, 0)
    return value
