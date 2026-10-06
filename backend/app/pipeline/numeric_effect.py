"""Source-literal numeric effect and endpoint framing for extraction output."""

import re
from decimal import Decimal
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field


class NumericEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    status: Literal["parsed", "uncertain"]
    kind: Literal["percent_change", "percentage_points", "fold_change", "risk_ratio", "unknown"]
    value: str | None = None
    unit: str | None = None
    direction: Literal["increase", "decrease"] | None = None
    lower_value: str | None = Field(default=None, exclude_if=lambda value: value is None)
    upper_value: str | None = Field(default=None, exclude_if=lambda value: value is None)


_VALUE = r"\d+(?:\.\d+)?"
_RANGE = rf"(?P<lower>{_VALUE})\s*(?:[-\u2012\u2013\u2014\u2212]|\bto\b)\s*(?P<upper>{_VALUE})"
_FOLD = re.compile(
    rf"\b(?:{_RANGE}|(?P<single>{_VALUE}))\s*[- ]?\s*(?:times?|fold)\b", re.I,
)
_RR_RANGE = re.compile(rf"\b(?:RR|relative risk)\s+(?:of\s+)?{_RANGE}\b", re.I)
_TRAILING = re.compile(
    rf"\s+by\s+(?:(?:about|approximately|roughly)\s+)?"
    rf"(?P<value>{_VALUE})\s*(?:-\s*)?(?P<unit>%|percentage[ -]points?|fold)"
    r"(?=\W|$)\.?$",
    re.I,
)
_RR = re.compile(rf"\b(?:RR|relative risk)\s+(?:of\s+)?(?P<value>{_VALUE})\b", re.I)
_DOUBLE = re.compile(r"\b(?P<value>doubles?|triples?)\b", re.I)
_RELATION = re.compile(
    r"\b(?:increases?|raises?|reduces?|decreases?|lowers?|doubles?|triples?|"
    r"causes?|prevents?|improves?)\b", re.I,
)


def numeric_effect(text: str) -> NumericEffect | None:
    """Record asserted notation; never convert ratios into percentages."""
    ratio_range = _RR_RANGE.search(text)
    fold = _FOLD.search(text)
    if ratio_range or (fold and (fold["lower"] is not None or not _TRAILING.search(text))):
        match = ratio_range or fold
        assert match is not None
        lower, upper = match["lower"], match["upper"]
        single = match.groupdict().get("single")
        # Frequency/count wording is not an effect size. Keep ambiguous 'times
        # higher' wording unresolved rather than choosing an arithmetic convention.
        following = text[match.end():]
        effect_context = bool(ratio_range or re.search(
            r"\b(?:risk|incidence|rate|odds|hazard|increase|decrease|higher|lower|"
            r"reduce|reduces|reduction|change)\b", text, re.I,
        ) or (fold and "fold" in match.group().casefold()))
        ambiguous = bool(fold and re.match(r"\s+(?:higher|lower|more|less)\b", following, re.I))
        ordered = lower is None or (upper is not None and Decimal(lower) <= Decimal(upper))
        return NumericEffect(
            raw_text=match.group(), status="parsed" if effect_context and ordered
            and not ambiguous else "uncertain", kind="risk_ratio" if ratio_range else
            "fold_change", value=single, lower_value=lower, upper_value=upper,
            unit="RR" if ratio_range else "fold",
        )
    rr = _RR.search(text)
    if rr:
        return NumericEffect(raw_text=rr.group(), status="parsed", kind="risk_ratio",
                             value=rr["value"], unit="RR")
    double = _DOUBLE.search(text)
    if double:
        value = "2" if double.group().casefold().startswith("double") else "3"
        return NumericEffect(raw_text=double.group(), status="parsed", kind="fold_change",
                             value=value, unit="fold", direction="increase")
    trailing = _TRAILING.search(text)
    if trailing:
        unit = trailing["unit"].casefold()
        kind = ("percent_change" if unit == "%" else "fold_change" if unit == "fold"
                else "percentage_points")
        preceding = text[:trailing.start()]
        verbs = list(_RELATION.finditer(preceding))
        direction: Literal["increase", "decrease"] | None = None
        if verbs:
            word = verbs[-1].group().casefold()
            if word.startswith(("reduc", "decreas", "lower")):
                direction = "decrease"
            elif word.startswith(("increas", "rais")):
                direction = "increase"
        return NumericEffect(raw_text=trailing.group().strip().rstrip("."),
                             status="parsed" if direction else "uncertain",
                             kind=cast(Literal["percent_change", "fold_change",
                                               "percentage_points"], kind),
                             value=trailing["value"], unit=unit, direction=direction)
    # Malformed quantitative wording stays visible, without guessed magnitude.
    if re.search(r"\b(?:by|RR|relative risk)\b.{0,20}(?:\d|%|fold|percent|\w+ty)",
                 text, re.I):
        tail = re.search(r"\b(?:by|RR|relative risk)\b.{0,30}", text, re.I)
        return NumericEffect(raw_text=tail.group().rstrip(".") if tail else text,
                             status="uncertain", kind="unknown")
    return None


def literal_outcome(text: str, exposure: str | None) -> str | None:
    """Recover only a literal object of an explicit quantitative relation."""
    if exposure is None or numeric_effect(text) is None:
        return None
    start = re.search(re.escape(exposure), text, re.I)
    if start is None:
        return None
    fold = _FOLD.search(text, start.end())
    if fold:
        following = re.match(
            r"\s+(?:the\s+)?(.+?)(?:\s+of\s+|\s+compared\s+(?:to|with)\s+|[.!?]|$)",
                             text[fold.end():], re.I)
        if following and re.search(r"\b(?:risk|incidence|rate|odds|hazard)\b", following[1], re.I):
            return following[1].strip()
    rr = _RR.search(text, start.end())
    if rr:
        following = re.search(r"\bfor\s+(.+?)[.!?]?$", text[rr.end():], re.I)
        return following[1].strip() if following else None
    relation = _RELATION.search(text, start.end())
    if relation is None:
        return None
    tail = text[relation.end():].strip()
    magnitude = _TRAILING.search(tail)
    if magnitude:
        tail = tail[:magnitude.start()].strip()
    else:
        uncertain_tail = re.search(r"\s+by\s+.{1,30}$", tail, re.I)
        if uncertain_tail:
            tail = tail[:uncertain_tail.start()].strip()
    tail = tail.rstrip(".!? ")
    tail = re.sub(r"^the\s+", "", tail, flags=re.I)
    return tail if tail and re.search(r"[A-Za-z\u4e00-\u9fff]", tail) else None


def literal_exposure(text: str) -> str | None:
    """Recover a simple verbatim atomic subject when the model omitted it."""
    if numeric_effect(text) is None:
        return None
    relation = _RELATION.search(text)
    if relation is None:
        relation = re.search(r"\bhas\s+an?\s+(?=RR\b|relative risk\b)", text, re.I)
    if relation is None and _FOLD.search(text):
        relation = re.search(r"\b(?:has|have)\s+(?=\d)", text, re.I)
    if relation is None:
        return None
    head = text[:relation.start()].strip()
    if not head or "," in head or len(head) > 120:
        return None
    return head
