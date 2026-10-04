"""Statement-local quantitative checks with explicit unresolved assignments.

Source numerals are never assertions. The legacy parser remains unchanged for
historical decision 2.0; this contract repairs comma-form HR/CI and records
which asserted quantity could not be bound. Semantic scope checking is still
required even when typed values match.
"""

import re
from dataclasses import dataclass, replace
from decimal import Decimal

from app.validation.models import NumericAlignment
from app.validation.numeric import _PATTERNS, Quantity, _compatible, extract_quantities

VERSION = "assertion-numeric-2.1"
_NUMBER = r"\d+(?:\.\d+)?"
_FOLD_RANGE = re.compile(
    rf"\b({_NUMBER})\s*(?:-|to)\s*({_NUMBER})\s*(?:-?\s*)(?:times?|fold)\b", re.I,
)
_PERCENT_RANGE = re.compile(
    rf"\b({_NUMBER})\s*%?\s*(?:-|to)\s*({_NUMBER})\s*%"
    r"(?:\s+(?:risk\s+)?(reduction|decrease|increase|higher|lower))?(?!\d)", re.I,
)
_PERCENT = re.compile(rf"\b({_NUMBER})\s*%")
_CONTEXT_PATTERNS = (
    ("population_count", re.compile(
        r"\b(\d+)\s+(?:[A-Za-z-]+\s+){0,4}(?:participants|patients|subjects|residents|smokers)\b",
        re.I)),
    ("study_count", re.compile(r"\b(\d+)\s+(?:relevant\s+|included\s+)?studies\b", re.I)),
    ("age_range", re.compile(r"\bage(?:d)?\s+(\d+)\s*(?:-|–|to)\s*(\d+)\b", re.I)),
    ("exposure_rate", re.compile(
        r"\b(\d+)\s+cigarettes\s+(?:per\s+day|daily|a\s+day)\b", re.I)),
)


@dataclass(frozen=True)
class NumericCheck:
    status: NumericAlignment
    asserted: Quantity | None = None
    candidates: tuple[Quantity, ...] = ()
    reason: str = "no_numerical_assertion"
    tokens: tuple[tuple[str, int, int], ...] = ()

    def diagnostic(self) -> dict[str, object]:
        def encoded(quantity: Quantity) -> dict[str, object]:
            return {"kind": quantity.kind, "values": [str(v) for v in quantity.values],
                    "unit": quantity.unit, "operator": quantity.operator}
        return {"status": self.status.value, "reason": self.reason,
                "asserted_tokens": [{"text": text, "start": start, "end": end}
                                    for text, start, end in self.tokens],
                "asserted": encoded(self.asserted) if self.asserted else None,
                "candidates": [encoded(q) for q in self.candidates]}


def normalized_numeric_text(text: str, *, repaired: bool = False) -> str:
    # Expand documented punctuation without changing the value or quantity type.
    normalized = re.sub(r"\b(hazard ratio|odds ratio|relative risk)\s*[\[(](HR|OR|RR)[\])]",
                        r"\1", text, flags=re.I)
    normalized = re.sub(r"\b(HR|OR|RR|CI|confidence interval|hazard ratio|odds ratio|relative risk)"
                        r"\s*,\s*", r"\1 ", normalized)
    normalized = re.sub(r"\b([Pp])\s*([<=>])\s*\.(\d+)", r"\1\2 0.\3", normalized)
    normalized = re.sub(r"%\s+(?:risk|hazard|odds)\s+(reduction|increase)",
                        r"% \1", normalized, flags=re.I)
    normalized = re.sub(r"(?<=\d)[,\u2009\u200a\u202f](?=\d{3}\b)", "", normalized)
    if repaired:
        normalized = re.sub(r"(?<=\d)[\u2012\u2013\u2014\u2212](?=\d)", "-", normalized)
    normalized = re.sub(r"\b(\d+)-(year|month|week|day)\b", r"\1 \2", normalized)
    return normalized


def _ranges(text: str) -> tuple[tuple[Quantity, tuple[int, int]], ...]:
    found: list[tuple[Quantity, tuple[int, int]]] = []
    for match in _FOLD_RANGE.finditer(text):
        found.append((Quantity("risk_multiple_range", (Decimal(match[1]), Decimal(match[2]))),
                      match.span()))
    for match in _PERCENT_RANGE.finditer(text):
        if any(match.start() < end and start < match.end() for _, (start, end) in found):
            continue
        direction = match[3]
        if direction is None:
            preceding = text[max(0, match.start() - 80):match.start()]
            lead = re.search(
                r"\b(reduc\w*|decreas\w*|increas\w*|rais\w*|lower\w*)\b"
                r".{0,70}\b(?:by|of)\s*$", preceding, re.I,
            )
            direction = lead[1] if lead else None
        kind = "percent_change_range" if direction else "percent_range"
        unit = ("decrease" if direction and direction.casefold().startswith(
            ("reduc", "decreas", "lower"),
        ) else "increase" if direction else None)
        found.append((Quantity(kind, (Decimal(match[1]), Decimal(match[2])), unit),
                      match.span()))
    return tuple(found)


def _mask_spans(text: str, spans: tuple[tuple[int, int], ...]) -> str:
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def without_user_magnitude_references(
    statement: str, user_claim: str | None,
) -> tuple[str, bool]:
    """Remove only explicit *mentions* of the user's percentage, not estimates.

    A wrong quoted user magnitude is a mismatch. A positive source assertion
    never qualifies for removal and still needs source-side numeric validation.
    """

    if not user_claim:
        return statement, False
    claimed = {Decimal(m[1]) for m in _PERCENT.finditer(user_claim)}
    if not claimed:
        return statement, False
    spans: list[tuple[int, int]] = []
    for match in _PERCENT.finditer(statement):
        before = statement[max(0, match.start() - 130):match.start()]
        clause = re.split(r"[.;]", before)[-1]
        after = statement[match.end():match.end() + 75]
        claim_mention = bool(re.search(
            r"\b(?:claim(?:ed|'s)?|user(?:'s)?|submitted)\b.{0,95}$", clause, re.I,
        ))
        negative_mention = bool(re.search(
            r"\b(?:not|no|none|neither|rather than|without|fails? to|failed to)\b.{0,105}"
            r"\b(?:give|provid\w*|report\w*|quantif\w*|establish\w*|support\w*|"
            r"contain\w*|show\w*|confirm\w*|verif\w*|specific|measure|finding)\b.{0,60}$",
            clause, re.I,
        ) or re.search(r"\brather than(?:\s+\w+){0,6}\s*$", clause, re.I)
                                or re.search(r"\b(?:not|no)\s+(?:an?\s+)?$", clause, re.I))
        positive_source = bool(re.search(
            r"\b(?:source|study|trial|review|paper|evidence)\b.{0,75}"
            r"\b(?:report\w*|show\w*|found|confirm\w*|support\w*)\b.{0,35}$",
            clause, re.I,
        ) or re.search(r"\b(?:confirmed|supported|verified)\b", after, re.I))
        if (claim_mention or negative_mention) and (not positive_source or negative_mention):
            if Decimal(match[1]) not in claimed:
                return statement, True
            spans.append(match.span())
    return _mask_spans(statement, tuple(spans)), False


def quantities(text: str, *, repaired: bool = False) -> tuple[Quantity, ...]:
    normalized = normalized_numeric_text(text, repaired=repaired)
    ranges = _ranges(normalized) if repaired else ()
    masked = _mask_spans(normalized, tuple(span for _, span in ranges))
    found = [quantity for quantity, _ in ranges]
    found.extend(extract_quantities(masked))
    for kind, pattern in _CONTEXT_PATTERNS:
        found.extend(Quantity(kind, tuple(Decimal(g) for g in m.groups()))
                     for m in pattern.finditer(masked))
    # Confidence level is its own quantity, not a treatment percentage.
    levels = tuple(Decimal(m[1]) for m in re.finditer(
        r"\b(\d+(?:\.\d+)?)\s*%\s*(?:CI|confidence interval)\b", masked, re.I))
    found = [q for q in found if not (q.kind == "percent" and q.values[0] in levels)]
    found.extend(Quantity("confidence_level", (level,)) for level in levels)
    pair = re.search(r"\b(\d+)\s+(?:vs\.?|versus|in active v)\s+(\d+)\b",
                     masked if repaired else text, re.I)
    if pair:
        found.append(Quantity("event_count_pair", (Decimal(pair[1]), Decimal(pair[2]))))
    # Bind each interval to its own estimate, rather than any CI in the abstract.
    estimate_pattern = (r"\b(HR|RR|OR|hazard ratio|relative risk|odds ratio)"
                        r"\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\b")
    estimates = list(re.finditer(estimate_pattern, masked, re.I))
    for index, estimate in enumerate(estimates):
        end = estimates[index + 1].start() if index + 1 < len(estimates) else len(masked)
        tail = masked[estimate.end():end]
        interval = next((q for q in extract_quantities(tail)
                         if q.kind == "confidence_interval"), None)
        if interval:
            measure = {"hazard ratio": "HR", "odds ratio": "OR", "relative risk": "RR"}.get(
                estimate[1].casefold(), estimate[1].upper())
            level = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(?:CI|confidence interval)", tail, re.I)
            values = (Decimal(estimate[2]), *interval.values)
            if level:
                values = (*values, Decimal(level[1]))
            found.append(Quantity("estimate_interval", values, measure))
    return tuple(found)


def compare_assertion_numbers(
    statement: str, sources: tuple[str, ...], *, user_claim: str | None = None,
    repaired: bool = False,
) -> NumericCheck:
    check = _compare(statement, sources, user_claim=user_claim, repaired=repaired)
    return replace(check, tokens=tuple((m[0], m.start(), m.end())
                                      for m in re.finditer(r"\d+(?:\.\d+)?", statement)))


def _compare(
    statement: str, sources: tuple[str, ...], *, user_claim: str | None, repaired: bool,
) -> NumericCheck:
    # A clearly attributed user magnitude is compared with the user, never
    # required to equal the study's estimate. Preserve the contrast for semantics.
    if repaired:
        statement, misstated = without_user_magnitude_references(statement, user_claim)
        if misstated:
            return NumericCheck(NumericAlignment.MISMATCH,
                                reason="misstated_original_user_magnitude")
    else:
        user_refs = list(re.finditer(
            r"\b(?:claimed|claim(?:'s)?|user(?:'s)?)\s+(\d+(?:\.\d+)?)%",
            statement, re.I,
        ))
        if user_refs and user_claim:
            for ref in reversed(user_refs):
                if not re.search(rf"\b{re.escape(ref[1])}\s*%", user_claim):
                    return NumericCheck(NumericAlignment.MISMATCH,
                                        reason="misstated_original_user_magnitude")
                statement = statement[:ref.start()] + "user magnitude" + statement[ref.end():]
    asserted = quantities(statement, repaired=repaired)
    source = tuple(q for text in sources for q in quantities(text, repaired=repaired))
    # Any uncovered numeral remains explicitly unresolved, including exact doses
    # and years. It is never silently treated as a medical effect estimate.
    remaining = re.sub(r"\bS\d+\b|\bE\d+(?:\.U\d+)?\b", "", statement)
    if not asserted:
        if re.search(r"\d", remaining):
            return NumericCheck(NumericAlignment.UNCERTAIN, reason="unclassified_asserted_numeral")
        return NumericCheck(NumericAlignment.NOT_APPLICABLE)
    normalized = normalized_numeric_text(remaining, repaired=repaired)
    covered = [(m.start(), m.end()) for _, pattern in (*_PATTERNS, *_CONTEXT_PATTERNS)
               for m in pattern.finditer(normalized)]
    if repaired:
        covered.extend(span for _, span in _ranges(normalized))
    covered.extend(m.span() for m in re.finditer(r"\b\d+\s+(?:vs\.?|versus)\s+\d+\b", normalized))
    if any(not any(start <= m.start() and m.end() <= end for start, end in covered)
           for m in re.finditer(r"\d+(?:\.\d+)?", normalized)):
        return NumericCheck(NumericAlignment.UNCERTAIN, reason="unclassified_asserted_numeral")
    for value in asserted:
        matches = tuple(q for q in source if _compatible(value, q))
        if any(value.values == q.values and (value.kind != "p_value" or
                                             value.operator == q.operator) for q in matches):
            continue
        if value.kind == "percent_change":
            # Risk reduction is a transformation of RR; OR/HR are not risk ratios.
            risks = tuple(q for q in source if q.kind == "relative_risk")
            if len(risks) == 1 and value.unit == "decrease":
                derived = Quantity("percent_change", ((1 - risks[0].values[0]) * 100,),
                                   "decrease")
                return NumericCheck(NumericAlignment.ALIGNED if value.values == derived.values
                                    and len(asserted) == 1 else NumericAlignment.MISMATCH
                                    if value.values != derived.values
                                    else NumericAlignment.UNCERTAIN,
                                    value, (derived,), "relative_risk_transformation")
        if value.kind == "estimate_interval":
            same_estimate = tuple(q for q in matches if q.values[0] == value.values[0])
            if same_estimate:
                return NumericCheck(NumericAlignment.MISMATCH, value, same_estimate,
                                    "interval_bound_to_different_estimate")
        if not matches and value.kind in {"odds_ratio", "relative_risk", "hazard_ratio"}:
            ratios = tuple(q for q in source if q.kind in {
                "odds_ratio", "relative_risk", "hazard_ratio"})
            if ratios:
                return NumericCheck(NumericAlignment.MISMATCH, value, ratios,
                                    "quantity_type_substitution")
        distinct = tuple(dict.fromkeys(matches))
        if len(distinct) == 1 and value.kind != "event_count_pair":
            return NumericCheck(NumericAlignment.MISMATCH, value, distinct,
                                "different_value_at_same_quantity_type")
        return NumericCheck(NumericAlignment.UNCERTAIN, value, distinct,
                            "quantity_assignment_unresolved")
    return NumericCheck(NumericAlignment.ALIGNED, reason="typed_values_match_statement_sources")
