"""Centralized validation for untrusted tool arguments."""

import re


class InputValidationError(ValueError):
    """A safe, user-facing validation error."""


_REPOSITORY_PART = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_repository_part(value: str, field_name: str) -> str:
    """Allow only a single GitHub owner/repository path segment."""
    candidate = value.strip()
    if not _REPOSITORY_PART.fullmatch(candidate):
        raise InputValidationError(
            f"{field_name} must be 1-100 letters, numbers, dots, underscores, or hyphens."
        )
    return candidate


def validate_search_query(value: str) -> str:
    """Validate a plain search phrase before adding trusted qualifiers."""
    candidate = value.strip()
    if not candidate or len(candidate) > 200:
        raise InputValidationError("query must contain 1-200 characters.")
    if _CONTROL_CHARACTERS.search(candidate) or "\r" in candidate or "\n" in candidate:
        raise InputValidationError("query cannot contain control characters or newlines.")
    # Prevent callers from escaping the selected repository with GitHub qualifiers.
    if re.search(r"(^|\s)(repo|org|user):", candidate, flags=re.IGNORECASE):
        raise InputValidationError(
            "query cannot contain repo:, org:, or user: qualifiers; use owner and repository."
        )
    return candidate


def validate_issue_text(value: str, field_name: str, maximum: int) -> str:
    """Validate text while preserving ordinary Markdown and body newlines."""
    candidate = value.strip()
    if not candidate or len(candidate) > maximum:
        raise InputValidationError(
            f"{field_name} must contain 1-{maximum} characters."
        )
    if "\x00" in candidate or "\r" in candidate:
        raise InputValidationError(f"{field_name} contains a forbidden control character.")
    return candidate


def validate_limit(value: int) -> int:
    if not 1 <= value <= 20:
        raise InputValidationError("limit must be between 1 and 20.")
    return value

