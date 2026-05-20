from __future__ import annotations


def normalize_version(value: str) -> str:
    return value.strip().lstrip("v")


def version_tuple(value: str) -> tuple[int, ...]:
    sanitized = normalize_version(value)
    if not sanitized:
        return (0,)
    parts: list[int] = []
    for chunk in sanitized.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def is_newer_version(candidate: str, current: str) -> bool:
    candidate_tuple = version_tuple(candidate)
    current_tuple = version_tuple(current)
    width = max(len(candidate_tuple), len(current_tuple))
    candidate_tuple += (0,) * (width - len(candidate_tuple))
    current_tuple += (0,) * (width - len(current_tuple))
    return candidate_tuple > current_tuple
