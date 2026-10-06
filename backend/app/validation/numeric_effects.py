"""Versioned source fidelity and claim comparability; no model or evidence changes."""

import re
from decimal import Decimal
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.pipeline.numeric_effect import NumericEffect
from app.validation.assertion_numeric import (
    _CONTEXT_PATTERNS,
    _mask_spans,
    _ranges,
    compare_assertion_numbers,
    normalized_numeric_text,
    quantities,
    without_user_magnitude_references,
)
from app.validation.models import NumericAlignment
from app.validation.numeric import _PATTERNS
from app.validation.numeric_occurrences import clause_span, linked_statement, occurrences

VERSION = "numeric-fidelity-comparability-1.1"
PREVIOUS_VERSION = "numeric-fidelity-comparability-1.0"
N = r"\d+(?:\.\d+)?"


class Measure(StrEnum):
    PERCENT_CHANGE = "percent_change"
    PERCENTAGE_POINTS = "percentage_points"
    RISK_RATIO = "risk_ratio"
    ODDS_RATIO = "odds_ratio"
    HAZARD_RATIO = "hazard_ratio"
    RATE_RATIO = "rate_ratio"
    ABSOLUTE_RISK = "absolute_risk"
    RISK_DIFFERENCE = "risk_difference"
    PAF = "population_attributable_fraction"
    AF_EXPOSED = "attributable_fraction_exposed"
    PREVALENCE = "prevalence"
    INCIDENCE_RATE = "incidence_rate"
    EVENT_COUNT = "event_count"
    FOLD_CHANGE = "fold_change"
    DURATION = "duration"
    DOSE = "dose"
    UNKNOWN = "unknown"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NumericQuantity(Frozen):
    values: tuple[str, ...]
    kind: Measure
    unit: str | None = None
    literal: str
    normalization_reason: str | None = None
    binding: str | None = None
    start: int | None = Field(default=None, exclude_if=lambda v: v is None)
    end: int | None = Field(default=None, exclude_if=lambda v: v is None)
    role: str | None = Field(default=None, exclude_if=lambda v: v is None)
    linked_statement_id: str | None = Field(default=None, exclude_if=lambda v: v is None)


class NumericSourceFidelity(Frozen):
    status: Literal["verified", "mismatch", "uncertain", "not_found"]
    asserted: NumericQuantity
    source: NumericQuantity | None
    source_evidence_ids: tuple[str, ...]
    reason: str
    conversions: tuple[str, ...] = ()


class NumericClaimComparability(Frozen):
    status: Literal["aligned", "compatible_but_narrower", "different_measure",
                    "different_comparator", "different_population", "different_exposure",
                    "different_endpoint", "different_timeframe", "not_comparable", "uncertain"]
    claim_measure: Measure
    reason: str
    differences: tuple[str, ...] = ()
    conversions: tuple[str, ...] = ()
    magnitude_relation: Literal["matching", "different", "uncertain"] = "uncertain"


class NumericFinding(Frozen):
    version: Literal["numeric-fidelity-comparability-1.0",
                     "numeric-fidelity-comparability-1.1",
                     "numeric-reference-comparability-2.4"] = "numeric-fidelity-comparability-1.1"
    target_id: str
    material: bool
    fidelity: NumericSourceFidelity
    comparability: NumericClaimComparability
    numeric_effect: Literal["supports_magnitude", "opposes_magnitude", "noncomparable",
                            "unresolved"]
    semantic_scope_checked: bool = False
    source_quantity_id: str | None = Field(default=None, exclude_if=lambda v: v is None)
    structure_status: Literal["structured", "embedded_numeric_assertions",
                              "mixed_measures_in_qualitative_finding"] = "structured"


def claim_references(text: str, claim: str, *, followup: bool = True) -> tuple[str, bool]:
    """Mask explicit comparisons/negations of the user's quantity, never source estimates."""
    if followup:
        found = occurrences(text, claim)
        return _mask_spans(text, tuple((o.start, o.end) for o in found
            if o.role == "identifier" or o.role == "claim_reference"
            and o.reference_status == "matched")), any(
                o.reference_status == "mismatch" for o in found)
    text, wrong = without_user_magnitude_references(text, claim)
    if wrong:
        return text, True
    asserted = {Decimal(m[1]) for m in re.finditer(rf"({N})\s*%", claim)}
    spans = []
    for match in re.finditer(rf"({N})\s*%", text):
        before = text[max(0, match.start() - 65):match.start()]
        after = text[match.end():match.end() + 65]
        reference = bool(re.search(
            r"(?:\b(?:larger|smaller|higher|lower|greater|less)\b.{0,25}\bthan\s+(?:an?\s+)?|"
            r"\b(?:above|below)\s+(?:an?\s+)?|"
            r"\b(?:not|no|without)\s+(?:an?\s+|specific\s+)?)$", before, re.I,
        ) or re.match(r"\s*(?:figure|magnitude|increase)\b.{0,30}"
                      r"(?:absent|unsupported|contradicted|not established|given)", after, re.I))
        if reference:
            if Decimal(match[1]) not in asserted:
                return text, True
            spans.append(match.span())
    return _mask_spans(text, tuple(spans)), False


def parse_quantities(text: str, *, followup: bool = True
                     ) -> tuple[tuple[NumericQuantity, ...], str]:
    """Typed spans plus a residual checked by the historical strict assertion parser."""
    normalized = normalized_numeric_text(text, repaired=True)
    if followup:
        normalized = re.sub(r"(?<=\d)(\s*)[–—−](\s*)(?=\d)", r"\1-\2", normalized)
    found: list[NumericQuantity] = []
    spans: list[tuple[int, int]] = []
    opcodes = SequenceMatcher(None, text, normalized, autojunk=False).get_opcodes()

    def original_span(start: int, end: int) -> tuple[int, int]:
        covered = [(a + max(0, start-c) if tag == "equal" else a,
                    a + min(end, d)-c if tag == "equal" else b)
                   for tag, a, b, c, d in opcodes if c < end and start < d]
        return covered[0][0], covered[-1][1]

    def add(match: re.Match[str], kind: Measure, values: tuple[str, ...],
            unit: str | None = None, reason: str | None = None,
            binding: str | None = None) -> None:
        if any(match.start() < end and start < match.end() for start, end in spans):
            return
        original_start, original_end = original_span(*match.span())
        found.append(NumericQuantity(values=values, kind=kind, unit=unit,
                                     literal=text[original_start:original_end] if followup
                                     else match.group(), normalization_reason=reason,
                                     binding=binding,
                                     start=original_start if followup else None,
                                     end=original_end if followup else None,
                                     linked_statement_id=linked_statement(
                                         text, original_start, original_end) if followup else None))
        spans.append(match.span())

    if followup:
        for match in re.finditer(
            rf"\b({N})(?:\s*(?:-|to)\s*({N}))?\s*[x×]\s+(?:the\s+)?"
            r"(?:(?:lung\s+cancer|cancer)\s+)?risk\b", normalized, re.I,
        ):
            add(match, Measure.FOLD_CHANGE, tuple(str(Decimal(v)) for v in
                (match[1], match[2]) if v), "risk_multiple", "literal_risk_multiple")
    for match in re.finditer(
        rf"\b(?:absolute\s+)?risk\s*(?:changed\s+)?(?:from\s+)?({N})\s*%\s*"
        rf"(?:to|→)\s*({N})\s*%", normalized, re.I,
    ):
        if "→" not in match.group() and not re.search(r"\bfrom\b", match.group(), re.I):
            continue  # An interval/range without an ordered baseline is not arithmetic input.
        add(match, Measure.ABSOLUTE_RISK, (str(Decimal(match[1])), str(Decimal(match[2]))),
            "%", "ordered_absolute_risk_pair")

    for match in re.finditer(
        rf"\b({N})(?:\s*(?:-|to)\s*({N}))?\s*[- ]?\s*(?:times?|fold|×)"
        r"(?:\s+(?:the\s+)?(?:risk|higher))?", normalized, re.I,
    ):
        tail = normalized[match.start():match.end() + 35]
        ambiguous = bool(re.search(r"\btimes?\s+higher\b", tail, re.I))
        left, right = clause_span(normalized, match.start(), match.end())
        risk_context = bool(re.search(r"\brisk\b", normalized[
            max(left, match.start()-55) if followup else max(0, match.start()-55):
            min(right, match.end()+45) if followup else match.end()+45], re.I))
        if followup and "×" in match.group():
            # Symbolic multiplication also denotes microscope magnification and
            # dimensions. Nearby risk prose cannot bind those uses to a risk ratio.
            risk_context = bool(
                re.search(r"\brisk\s*(?:was|is|=|:)?\s*$", normalized[left:match.start()], re.I)
                or re.search(r"[×]\s+(?:the\s+)?risk\b", match.group(), re.I)
            )
        add(match, Measure.FOLD_CHANGE, tuple(str(Decimal(v)) for v in
            (match[1], match[2]) if v), "risk_multiple" if risk_context else "multiple",
            "literal_times_higher_no_arithmetic_convention" if ambiguous else
            "literal_risk_multiple" if risk_context else "literal_fold_change")
    for match in re.finditer(rf"\b(?:rate ratio|IRR)\s*(?:of|=|:)?\s*({N})", normalized, re.I):
        add(match, Measure.RATE_RATIO, (str(Decimal(match[1])),))
    for measure_kind, pattern in (
        (Measure.RISK_DIFFERENCE, rf"\brisk difference\s*(?:of|=|:)?\s*({N})(\s*%)?"),
        (Measure.INCIDENCE_RATE, rf"\b({N})\s*(?:cases|events)?\s*per\s*({N})\s*person[- ]years?"),
        (Measure.EVENT_COUNT, rf"\b({N})\s*(?:events|cases|deaths)\b"),
    ):
        for match in re.finditer(pattern, normalized, re.I):
            values = ((str(Decimal(match[1])), str(Decimal(match[2])))
                      if measure_kind == Measure.INCIDENCE_RATE else (str(Decimal(match[1])),))
            add(match, measure_kind, values,
                "per_person_years" if measure_kind == Measure.INCIDENCE_RATE else
                "%" if measure_kind == Measure.RISK_DIFFERENCE and match[2] else None)
    percent_pattern = (rf"\b({N})(?:\s*(?:-|to)\s*({N}))?\s*%" if followup
                       else rf"\b({N})\s*%")
    for match in re.finditer(percent_pattern, normalized):
        context = normalized[max(0, match.start()-100):match.end()+115]
        if followup:
            left, right = clause_span(normalized, match.start(), match.end())
            context = normalized[left:right]
            # An explicit local change is more specific than a PAF elsewhere.
            if re.match(r"\s*(?:relative\s+|risk\s+)?"
                        r"(?:increase|decrease|reduction|higher|lower)\b",
                        normalized[match.end():right], re.I):
                continue
        # A confidence level or an explicit percent change has its own legacy binding.
        if re.match(r"\s*(?:CI|confidence interval)\b", normalized[match.end():], re.I):
            continue
        kind: Measure | None = None
        if re.search(r"\battribut(?:able|ed|es?)\b|\bmain cause of\b", context, re.I):
            kind = (Measure.AF_EXPOSED if re.search(r"\bamong (?:the )?exposed\b", context,
                                                   re.I) else Measure.PAF)
        elif re.search(r"\bprevalence\b", context, re.I):
            kind = Measure.PREVALENCE
        elif re.search(r"\babsolute risk\b", context, re.I):
            kind = Measure.ABSOLUTE_RISK
        if kind:
            sex = re.match(r"\s*(?:of\s+)?(male|female)\b", normalized[match.end():], re.I)
            vals = tuple(str(Decimal(v)) for v in (
                match[1], match[2] if followup else None) if v)
            add(match, kind, vals, "%",
                binding=sex[1].casefold() if sex else None)
    residual = _mask_spans(normalized, tuple(spans))
    # Existing CI, p-value, dose, duration and count checks remain strict. New
    # typed fidelity replaces only spans whose meaning has been explicitly bound.
    mapping = {"relative_risk": Measure.RISK_RATIO, "hazard_ratio": Measure.HAZARD_RATIO,
               "odds_ratio": Measure.ODDS_RATIO, "percent_change": Measure.PERCENT_CHANGE,
               "percent_change_range": Measure.PERCENT_CHANGE,
               "percentage_points": Measure.PERCENTAGE_POINTS,
               "risk_multiple_range": Measure.FOLD_CHANGE, "dose": Measure.DOSE,
               "duration": Measure.DURATION, "event_count_pair": Measure.EVENT_COUNT,
               "sample_count": Measure.EVENT_COUNT, "population_count": Measure.EVENT_COUNT}
    legacy_spans = [m.span() for _, pattern in (*_PATTERNS, *_CONTEXT_PATTERNS)
                    for m in pattern.finditer(residual)]
    legacy_spans.extend(span for _, span in _ranges(residual))
    used_spans: set[tuple[int, int]] = set()
    for quantity in quantities(residual, repaired=True):
        matching_span = next(((start, end) for start, end in legacy_spans
                              if (start, end) not in used_spans and quantity in
                              quantities(residual[start:end], repaired=True)), None)
        start, end = (original_span(*matching_span) if matching_span else (None, None))
        if matching_span:
            used_spans.add(matching_span)
        found.append(NumericQuantity(values=tuple(str(v) for v in quantity.values),
                                     kind=mapping.get(quantity.kind, Measure.UNKNOWN),
                                     unit=quantity.unit,
                                     literal=text[start:end] if followup and start is not None
                                     else residual.strip(), start=start if followup else None,
                                     end=end if followup else None,
                                     linked_statement_id=linked_statement(text, start, end)
                                     if followup and start is not None and end is not None
                                     else None))
    return tuple(found), residual


def source_fidelity(text: str, sources: tuple[tuple[str, str], ...], claim: str,
                    *, followup: bool = True,
                    statement_sources: dict[str, tuple[tuple[str, str], ...]] | None = None,
                    ) -> tuple[tuple[NumericSourceFidelity, ...], NumericAlignment]:
    roles = occurrences(text, claim) if followup else ()
    clean, wrong = claim_references(text, claim, followup=followup)
    asserted, residual = parse_quantities(clean, followup=followup)
    legacy = compare_assertion_numbers(residual, tuple(s for _, s in sources),
                                      user_claim=None if followup else claim, repaired=True)
    if not asserted and legacy.status == NumericAlignment.UNCERTAIN:
        unmapped = re.sub(r"\bS\d+\b|\bE\d+(?:\.U\d+)?\b", "", residual)
        asserted = tuple(NumericQuantity(values=(m.group(),), kind=Measure.UNKNOWN,
                                         literal=m.group()) for m in re.finditer(N, unmapped))
    result: list[NumericSourceFidelity] = []
    candidates = [(identifier, q) for identifier, source in sources
                  for q in parse_quantities(source, followup=followup)[0]]
    for q in asserted:
        applicable = candidates
        source_pairs = sources
        role = next((o for o in roles if q.start is not None
                     and o.start < (q.end or q.start) and q.start < o.end), None)
        if followup and role:
            q = q.model_copy(update={"role": role.role,
                                     "linked_statement_id": linked_statement(
                                         text, q.start or 0, q.end or 0)})
        if followup and q.linked_statement_id and statement_sources is not None:
            bound = statement_sources.get(q.linked_statement_id, ())
            source_pairs = tuple(pair for pair in bound if pair in sources)
            applicable = [(identifier, quantity) for identifier, source in bound
                          if (identifier, source) in sources
                          for quantity in parse_quantities(source)[0]]
        matches = [(i, s) for i, s in applicable if s.kind == q.kind and s.unit == q.unit
                   and (q.binding is None or s.binding == q.binding)]
        exact = [(i, s) for i, s in matches if tuple(Decimal(v) for v in s.values) ==
                 tuple(Decimal(v) for v in q.values)]
        if followup and not exact and q.kind == Measure.PAF and len(q.values) == 2:
            # A literal summary range needs both actual endpoint fractions from
            # the same cited passage, not a bound plucked from another source.
            for identifier, quote in dict.fromkeys(source_pairs):
                endpoints = [s for s in parse_quantities(quote)[0]
                             if s.kind == q.kind and s.unit == q.unit and len(s.values) == 1
                             and s.values[0] in q.values
                             and (q.binding is None or s.binding == q.binding)]
                if {s.values[0] for s in endpoints} == set(q.values):
                    first = min(s.start for s in endpoints if s.start is not None)
                    last = max(s.end for s in endpoints if s.end is not None)
                    combined = endpoints[0].model_copy(update={
                        "values": q.values, "literal": quote[first:last],
                        "start": first, "end": last,
                        "normalization_reason": "summary_of_distinct_source_fractions",
                        "binding": "; ".join(f"{s.binding}:{s.values[0]}"
                                              for s in endpoints if s.binding) or None,
                    })
                    exact = [(identifier, combined)]
                    break
        derived = []
        if not exact and q.kind == Measure.PERCENT_CHANGE and q.unit == "decrease":
            risks = [(i, s) for i, s in applicable if s.kind == Measure.RISK_RATIO
                     and len(s.values) == 1]
            if len(risks) == 1 and legacy.status == NumericAlignment.ALIGNED and tuple(
                Decimal(v) for v in q.values) == (
                (1 - Decimal(risks[0][1].values[0])) * 100,
            ):
                derived = risks
                exact = derived
        # The legacy parser guards unknown/CI bindings and unsupported arithmetic.
        status: Literal["verified", "mismatch", "uncertain", "not_found"] = (
            "verified" if exact else "mismatch" if matches else "not_found")
        reason = ("typed_values_present_in_cited_source" if exact else
                  "different_value_or_measure_in_cited_source" if matches else
                  "quantity_absent_from_source")
        if derived:
            reason = "existing_deterministic_RR_to_relative_reduction_conversion"
        if q.kind == Measure.UNKNOWN and legacy.status in {
            NumericAlignment.UNCERTAIN, NumericAlignment.MISMATCH,
        }:
            status = "mismatch" if legacy.status == NumericAlignment.MISMATCH else "uncertain"
            reason = legacy.reason
        result.append(NumericSourceFidelity(
            status=status, asserted=q, source=exact[0][1] if exact else matches[0][1]
            if matches else None,
            source_evidence_ids=tuple(dict.fromkeys(i for i, _ in (exact or matches))),
            reason=reason,
            conversions=("relative_reduction=(1-source_RR)*100",) if derived else (),
        ))
    overall = NumericAlignment.ALIGNED if asserted else NumericAlignment.NOT_APPLICABLE
    if wrong or legacy.status == NumericAlignment.MISMATCH or any(
        f.status == "mismatch" for f in result
    ):
        overall = NumericAlignment.MISMATCH
    elif any(o.role == "ambiguous" or o.reference_status == "uncertain" for o in roles) \
            or legacy.status == NumericAlignment.UNCERTAIN or any(
        f.status in {"uncertain", "not_found"} for f in result
    ):
        overall = NumericAlignment.UNCERTAIN
    return tuple(result), overall


def compare_to_claim(
    fidelity: NumericSourceFidelity, claim: NumericEffect | None, source_text: str,
    *, scope: str = "aligned", scope_basis: str = "same_question", allow_narrower: bool = False,
    claim_scope_text: str = "",
) -> tuple[NumericClaimComparability, str]:
    claimed = Measure(claim.kind) if claim and claim.kind in set(Measure) else Measure.UNKNOWN
    if claimed == Measure.FOLD_CHANGE and claim and "risk" in source_text.casefold():
        claimed = Measure.RISK_RATIO
    q = fidelity.asserted
    conversion: tuple[str, ...] = fidelity.conversions
    relation = "uncertain"

    def done(status: str, reason: str, effect: str = "noncomparable",
             differences: tuple[str, ...] = ()) -> tuple[NumericClaimComparability, str]:
        return NumericClaimComparability.model_validate({
            "status": status, "claim_measure": claimed, "reason": reason,
            "differences": differences, "conversions": conversion,
            "magnitude_relation": relation,
        }), effect

    if fidelity.status != "verified" or claim is None or claim.status != "parsed":
        return done("uncertain", "source_fidelity_or_claim_quantity_unresolved", "unresolved")
    ratio_like = q.kind == Measure.RISK_RATIO or (q.kind == Measure.FOLD_CHANGE
                                                and q.unit == "risk_multiple")
    absolute_pair = q.kind == Measure.ABSOLUTE_RISK and len(q.values) == 2
    same_measure = q.kind == claimed or (ratio_like and claimed in {
        Measure.PERCENT_CHANGE, Measure.RISK_RATIO,
    }) or (
        absolute_pair and claimed in {Measure.PERCENT_CHANGE, Measure.PERCENTAGE_POINTS})
    if ratio_like and claimed == Measure.PERCENT_CHANGE and claim_scope_text and not re.search(
        r"\brisk\b", claim_scope_text, re.I,
    ):
        same_measure = False
    if not same_measure:
        return done("different_measure", "source_measure_cannot_substitute_for_claim_measure",
                    differences=(f"{q.kind} versus {claimed}",))
    ambiguous = (q.normalization_reason == "literal_times_higher_no_arithmetic_convention"
                 or (fidelity.source is not None and fidelity.source.normalization_reason ==
                     "literal_times_higher_no_arithmetic_convention"))
    if claim.value and not ambiguous:
        target_value = Decimal(claim.value)
        if ratio_like and claimed == Measure.PERCENT_CHANGE:
            target_value = (1 + target_value / 100 if claim.direction == "increase" else
                            1 - target_value / 100)
        numeric_values = tuple(Decimal(v) for v in q.values)
        if not absolute_pair:
            relation = ("matching" if numeric_values == (target_value,) else
                        "different" if target_value < min(numeric_values) or
                        target_value > max(numeric_values) else "uncertain")
    if scope in {"incompatible", "broader_or_indirect"}:
        mapping = {"population": "different_population",
                   "active_alternative": "different_comparator",
                   "endpoint": "different_endpoint", "dose": "different_exposure"}
        return done(mapping.get(scope_basis, "not_comparable"), "audited_scope_difference",
                    differences=(scope_basis,))
    # Literal restrictions do not invent an unexposed comparator for a null PICO.
    restricted = re.search(r"\b(?:lifelong|life-long|high-dose|heavy|long-term)\s+"
                           r"(?:smokers|users|exposure|exposed|\w+)\b",
                           source_text, re.I)
    if restricted and restricted.group().casefold() in claim_scope_text.casefold():
        restricted = None
    if scope == "compatible_but_narrower" or restricted:
        if not allow_narrower:
            return done("compatible_but_narrower", "source_estimate_has_a_restricted_scope",
                        differences=(restricted.group() if restricted else scope_basis,))
    if scope == "uncertain":
        return done("uncertain", "semantic_scope_unresolved", "unresolved")
    if ambiguous:
        return done("aligned", "literal_source_phrase_verified_but_arithmetic_convention_ambiguous",
                    "unresolved")
    values = tuple(Decimal(v) for v in q.values)
    if claim.lower_value is not None and claim.upper_value is not None:
        bounds = (Decimal(claim.lower_value), Decimal(claim.upper_value))
        if bounds[0] > bounds[1]:
            return done("uncertain", "claim_range_unordered", "unresolved")
        if absolute_pair:
            return done("uncertain", "range_requires_a_direct_comparable_effect", "unresolved")
        relation = "matching" if values == bounds else "different" if (
            max(values) < bounds[0] or min(values) > bounds[1]) else "uncertain"
        effect = "supports_magnitude" if relation == "matching" else (
            "opposes_magnitude" if relation == "different" else "unresolved")
        return done("aligned", "verified_range_compared_without_metric_substitution", effect)
    target = Decimal(claim.value) if claim.value else None
    if target is None:
        return done("uncertain", "claim_value_unresolved", "unresolved")
    if ratio_like and claimed == Measure.PERCENT_CHANGE:
        target = 1 + target / 100 if claim.direction == "increase" else 1 - target / 100
        conversion = (*conversion, "claim_relative_percent_change_to_RR: 1 +/- value/100")
    if absolute_pair:
        baseline, exposed = values
        if not (0 <= baseline <= 100 and 0 <= exposed <= 100) or baseline == 0:
            return done("uncertain", "absolute_risk_arithmetic_inputs_incomplete", "unresolved")
        if claimed == Measure.PERCENT_CHANGE:
            values = ((exposed - baseline) / baseline * 100,)
            if claim.direction == "decrease":
                values = (-values[0],)
            conversion = ("relative_change=(exposed-baseline)/baseline*100",)
        else:
            values = (exposed - baseline,)
            conversion = ("percentage_point_difference=exposed-baseline",)
    if q.kind == Measure.PERCENT_CHANGE and q.unit != claim.direction:
        return done("aligned", "verified_opposite_numeric_direction", "opposes_magnitude")
    if len(values) == 1:
        effect = "supports_magnitude" if values[0] == target else "opposes_magnitude"
    elif min(values) <= target <= max(values):
        effect = "unresolved"  # A broad range cannot establish an exact point magnitude.
    else:
        effect = "opposes_magnitude"
    return done("compatible_but_narrower" if allow_narrower and scope != "aligned" else "aligned",
                "verified_quantity_compared_without_metric_substitution", effect)


def magnitude_alignment(findings: tuple[NumericFinding, ...]) -> NumericAlignment:
    effects = {f.numeric_effect for f in findings}
    if effects == {"supports_magnitude"}:
        return NumericAlignment.ALIGNED
    if effects == {"opposes_magnitude"}:
        return NumericAlignment.MISMATCH
    return NumericAlignment.UNCERTAIN
