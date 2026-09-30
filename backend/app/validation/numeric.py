"""Conservative, deterministic comparisons of material quantitative assertions."""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.validation.models import NumericAlignment

VERSION = "numeric-1.0"
_NUMBER = r"\d+(?:\.\d+)?"
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("relative_risk", re.compile(
        rf"\b(?:(?-i:RR)|relative risk(?:\s*\(\s*RR\s*\))?)"
        rf"\s*(?:was|of|=|:)?\s*({_NUMBER})\b", re.I,
    )),
    ("odds_ratio", re.compile(
        rf"\b(?:(?-i:OR)|odds ratio(?:\s*\(\s*OR\s*\))?)"
        rf"\s*(?:was|of|=|:)?\s*({_NUMBER})\b", re.I,
    )),
    ("hazard_ratio", re.compile(
        rf"\b(?:(?-i:HR)|hazard ratio(?:\s*\(\s*HR\s*\))?)"
        rf"\s*(?:was|of|=|:)?\s*({_NUMBER})\b", re.I,
    )),
    ("confidence_interval", re.compile(
        rf"\b(?:95%\s*)?(?:CI|confidence interval(?:\s*\(\s*CI\s*\))?)\s*[=:]?\s*"
        rf"[\[(]?({_NUMBER})\s*(?:-|–|to|,)\s*({_NUMBER})[\])]??", re.I,
    )),
    ("p_value", re.compile(rf"\bp\s*([<=>])\s*({_NUMBER})\b", re.I)),
    ("ratio", re.compile(rf"\bratio\s*(?:(?:of|=|:)\s*)?({_NUMBER})\s*:\s*({_NUMBER})\b",
                          re.I)),
    ("dose", re.compile(rf"\b({_NUMBER})\s*(mg|g|mcg|µg|μg|mL|L)\b", re.I)),
    ("duration", re.compile(
        rf"\b({_NUMBER})\s*(days?|weeks?|months?|years?|hours?)\b", re.I,
    )),
    ("percent_change", re.compile(
        rf"\b(?:by\s+)?({_NUMBER})\s*%\s*(?:reduction|decrease|increase|higher|lower)\b|"
        rf"\b(?:reduc\w*|decreas\w*|increas\w*|higher|lower\w*)\s+"
        rf"(?:\w+\s+){{0,5}}?(?:by|was|of)\s+({_NUMBER})\s*%", re.I,
    )),
    ("percentage_points", re.compile(rf"\b({_NUMBER})\s*percentage[ -]points?\b", re.I)),
    ("percent", re.compile(rf"\b({_NUMBER})\s*%", re.I)),
    ("sample_count", re.compile(
        rf"\b(?:n\s*=\s*|sample\s+(?:of|size\s+of)\s+|"
        rf"({_NUMBER})\s+(?:participants|patients|subjects|people)\b)({_NUMBER})?", re.I,
    )),
)


@dataclass(frozen=True)
class Quantity:
    kind: str
    values: tuple[Decimal, ...]
    unit: str | None = None
    operator: str | None = None


def extract_quantities(text: str) -> tuple[Quantity, ...]:
    """Use nonoverlapping typed spans; do not compare unrelated numeric forms."""

    found: list[Quantity] = []
    occupied: list[tuple[int, int]] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in occupied):
                continue
            groups = [group for group in match.groups() if group is not None]
            if kind == "sample_count":
                numbers = re.findall(_NUMBER, match.group())
                groups = numbers[-1:] if numbers else []
            if not groups:
                continue
            if kind == "p_value":
                quantity = Quantity(kind, (Decimal(groups[1]),), operator=groups[0])
            elif kind == "dose":
                unit = groups[1].casefold()
                scale = {"g": Decimal(1000), "mg": Decimal(1),
                         "mcg": Decimal("0.001"), "µg": Decimal("0.001"),
                         "μg": Decimal("0.001"), "l": Decimal(1000),
                         "ml": Decimal(1)}[unit]
                base_unit = "mg" if unit in {"g", "mg", "mcg", "µg", "μg"} else "ml"
                quantity = Quantity(kind, (Decimal(groups[0]) * scale,), unit=base_unit)
            elif kind == "duration":
                quantity = Quantity(kind, (Decimal(groups[0]),),
                                    unit=groups[1].casefold().rstrip("s"))
            else:
                values = tuple(Decimal(group) for group in groups)
                quantity = Quantity(kind, values)
                if kind == "percent_change":
                    word = match.group().casefold()
                    direction = "decrease" if re.search(
                        r"reduc|decreas|lower", word,
                    ) else "increase"
                    quantity = Quantity(kind, values, unit=direction)
            found.append(quantity)
            occupied.append(match.span())
    return tuple(found)


def _compatible(a: Quantity, b: Quantity) -> bool:
    return a.kind == b.kind and a.unit == b.unit


def _derived_reduction(evidence: tuple[Quantity, ...]) -> Quantity | None:
    risks = [item for item in evidence if item.kind == "relative_risk"]
    if len(risks) != 1 or risks[0].values[0] > 1:
        return None
    return Quantity("percent_change", ((1 - risks[0].values[0]) * 100,), "decrease")


def compare_numbers(claim: str, reasoning: str, passage: str) -> NumericAlignment:
    """A mismatch is fatal only for one unambiguous, comparable material value."""

    asserted = (*extract_quantities(claim), *extract_quantities(reasoning))
    if not asserted:
        return NumericAlignment.NOT_APPLICABLE
    evidence = extract_quantities(passage)
    derived = _derived_reduction(evidence)
    if derived is not None:
        evidence = (*evidence, derived)
    comparisons: list[bool] = []
    for quantity in asserted:
        matches = [item for item in evidence if _compatible(quantity, item)]
        if len(matches) != 1:
            continue
        other = matches[0]
        if quantity.kind == "p_value" and quantity.operator != other.operator:
            continue
        comparisons.append(quantity.values == other.values)
    if not comparisons:
        return NumericAlignment.UNCERTAIN
    if False in comparisons:
        return NumericAlignment.MISMATCH
    if len(comparisons) == len(asserted):
        return NumericAlignment.ALIGNED
    return NumericAlignment.UNCERTAIN


def compare_statement_numbers(
    statement: str, quoted_source: str,
) -> tuple[NumericAlignment, Quantity | None, Quantity | None]:
    """Compare one attributed statement with its own cited quotation only.

    A distinct study, an untyped year, or the original user's number never
    enters this comparison. Multiple candidate estimates are uncertain unless
    the exact typed value occurs in the quote.
    """

    asserted = extract_quantities(statement)
    if not asserted:
        return NumericAlignment.NOT_APPLICABLE, None, None
    source = extract_quantities(quoted_source)
    uncertain = False
    for value in asserted:
        same_type = [candidate for candidate in source if _compatible(value, candidate)]
        if any(candidate.values == value.values and
               (value.kind != "p_value" or candidate.operator == value.operator)
               for candidate in same_type):
            continue
        if len(same_type) == 1:
            return NumericAlignment.MISMATCH, value, same_type[0]
        uncertain = True
    return (NumericAlignment.UNCERTAIN if uncertain else NumericAlignment.ALIGNED,
            None, None)
