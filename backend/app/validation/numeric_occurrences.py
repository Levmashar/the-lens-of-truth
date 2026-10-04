"""Occurrence-local roles and reference links; no source or inference verdicts."""

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.pipeline.numeric_effect import numeric_effect

NUMBER = r"\d+(?:\.\d+)?"
IDENTIFIER = r"\b(?:S\d+|E\d+(?:\.U\d+)?)\b"
OCCURRENCE = re.compile(
    rf"{IDENTIFIER}|\b{NUMBER}(?:\s*%?\s*(?:[-–—−]|to)\s*{NUMBER})?"
    r"\s*(?:%|[x×](?!\w)|times?\b|fold\b|percentage[ -]points?\b)?", re.I,
)


class NumericOccurrence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    start: int
    end: int
    literal: str
    values: tuple[str, ...]
    role: Literal["source_assertion", "claim_reference", "derived_assertion",
                  "identifier", "ambiguous"]
    measure_hint: str
    direction: Literal["increase", "decrease"] | None = None
    reference_status: Literal["matched", "mismatch", "uncertain"] | None = None
    linked_statement_id: str | None = None


def clause_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Decimals and source-unit dots are not sentence boundaries."""
    boundaries = [0, *(m.end() for m in re.finditer(r"[;!?]|\.(?=\s|$)", text)), len(text)]
    left = max(p for p in boundaries if p <= start)
    right = min(p for p in boundaries if p >= end)
    return left, right


def linked_statement(text: str, start: int, end: int) -> str | None:
    left, right = clause_span(text, start, end)
    # Parenthetical links immediately following a result take precedence.
    after = re.match(r"[^;.!?]{0,45}?\((S\d+)\)", text[end:right], re.I)
    if after:
        return after[1].upper()
    before = list(re.finditer(r"\b(S\d+)\s+(?:reports?|states?|found|shows?)\b",
                             text[left:start], re.I))
    return before[-1][1].upper() if before else None


def occurrences(text: str, claim: str) -> tuple[NumericOccurrence, ...]:
    """References need wording plus matching value/measure; source assertions win."""
    submitted = numeric_effect(claim)
    result = []
    for match in OCCURRENCE.finditer(text):
        start, end = match.span()
        end = start + len(match.group().rstrip())
        raw = text[start:end]
        if re.fullmatch(IDENTIFIER, raw, re.I):
            result.append(NumericOccurrence(start=start, end=end, literal=raw, values=(),
                                            role="identifier", measure_hint="identifier"))
            continue
        values = tuple(str(Decimal(v)) for v in re.findall(NUMBER, raw))
        left, right = clause_span(text, start, end)
        before, after = text[left:start], text[end:right]
        before = re.split(r",\s+(?=(?:but|and|however|not|rather than|far above)\b)"
                          r"|\bbut\b", before, flags=re.I)[-1]
        change = bool(re.match(r"\s*(?:relative\s+|risk\s+)?"
                              r"(?:increase|decrease|reduction|higher|lower)\b", after, re.I))
        direction: Literal["increase", "decrease"] | None = (
            "decrease" if change and re.match(r"\s*(?:relative\s+|risk\s+)?"
                                              r"(?:decrease|reduction|lower)\b", after, re.I)
            else "increase" if change else None)
        points = bool(re.search(r"percentage[ -]points?", raw, re.I))
        hint = ("percentage_points" if points else "percent_change" if change else
                "fold_change" if re.search(r"[x×]|times?|fold", raw, re.I) else "unknown")
        explicit = bool(re.search(r"\b(?:claimed|claim's|user's|submitted)\s+"
                                  r"(?:(?:exact|specific|reported)\s+)?$", before, re.I))
        if hint == "unknown" and explicit:
            local = re.match(r"\s*(attributable fraction|prevalence|absolute risk)\b", after, re.I)
            if local:
                hint = {"attributable fraction": "population_attributable_fraction",
                        "prevalence": "prevalence", "absolute risk": "absolute_risk"}[
                            local[1].casefold()]
        if hint == "unknown" and not explicit:
            ratio = re.search(r"\b(HR|OR|RR)\s*(?:=|of|:)?\s*$", before, re.I)
            if ratio:
                hint = {"hr": "hazard_ratio", "or": "odds_ratio",
                        "rr": "risk_ratio"}[ratio[1].casefold()]
            elif re.search(r"\battribut(?:able|ed)\b|\bmain cause of\b",
                           before + after, re.I):
                hint = "population_attributable_fraction"
        comparison = bool(re.search(r"\b(?:above|below|than|rather than|not)\s+(?:an?\s+)?$",
                                    before, re.I))
        absence = bool(re.search(r"\b(?:no|without)\s+(?:an?\s+|specific\s+)?$", before, re.I)
                       or re.search(r"\bdoes not (?:establish|give|support)\s+(?:an?\s+)?$", before,
                                    re.I))
        absence = absence and bool(change or re.match(r"\s*(?:figure|magnitude)\b", after,
                                                      re.I))
        source = bool(re.search(
            r"\b(?:study|source|trial|paper|review|evidence)\b[^;.!?]{0,85}"
            r"\b(?:reports?|reported|confirms?|confirmed|found|find|shows?|showed|supports?)\b"
            r"[^;.!?]{0,45}$", before, re.I))
        confirms = bool(re.match(r"\s*(?:increase(?:\s+in\s+risk)?\s+)?(?:is\s+)?"
                                r"(?:confirmed|verified|supported)\s+by\b", after, re.I))
        derived = bool(re.search(r"\b(?:calculat\w*|convert\w*|equivalent|correspond\w*)\b",
                                 before, re.I))
        role: Literal["source_assertion", "claim_reference", "derived_assertion",
                      "identifier", "ambiguous"] = "source_assertion"
        status: Literal["matched", "mismatch", "uncertain"] | None = None
        if derived:
            role = "derived_assertion"
        elif not source and not confirms and (explicit or comparison or absence):
            role = "claim_reference"
            if hint == "unknown" and "%" in raw and submitted and submitted.unit == "%":
                hint = submitted.kind
            if submitted is None or submitted.status != "parsed" or hint != submitted.kind:
                status = "uncertain"
            elif direction is not None and direction != submitted.direction:
                status = "mismatch"
            else:
                status = ("matched" if submitted.value is not None and
                          tuple(Decimal(v) for v in values) == (Decimal(submitted.value),)
                          else "mismatch")
        elif re.search(r"\bno (?:source|evidence)\s+(?:supports?|establishes?)\s*$",
                       before, re.I):
            role = "ambiguous"
        result.append(NumericOccurrence(
            start=start, end=end, literal=raw, values=values, role=role,
            measure_hint=hint, reference_status=status,
            direction=direction,
            linked_statement_id=linked_statement(text, start, end),
        ))
    return tuple(result)
