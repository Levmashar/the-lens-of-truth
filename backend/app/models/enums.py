"""Shared database/domain enumerations."""

from enum import StrEnum


class InputType(StrEnum):
    TEXT = "text"
    SCREENSHOT = "screenshot"
    URL = "url"


class VerdictLabel(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"
