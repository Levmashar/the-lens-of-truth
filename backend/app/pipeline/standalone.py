"""Conservative, source-grounded reconstruction of English coordinated claims."""

import re
from dataclasses import dataclass
from typing import Literal

StandaloneStatus = Literal["complete", "reconstructed", "uncertain", "incomplete"]

_VERB = (
    r"(?:causes?|caused|increases?|increased|raises?|raised|elevates?|elevated|"
    r"reduces?|reduced|decreases?|decreased|lowers?|lowered|prevents?|prevented|"
    r"improves?|improved|worsens?|worsened|results?\s+in)"
)
_PREDICATE = re.compile(rf"^(?P<verb>{_VERB})\s+(?P<outcome>\S.+)$", re.I)
_COMPARATIVE = re.compile(r"^(?P<outcome>(?:lower|higher|more|less)\s+\S.+)$", re.I)
_ANTECEDENT = re.compile(
    rf"^(?P<subject>[^.;:!?]{{2,160}}?)\s+"
    rf"(?:(?P<modal>may|might|could|can|will|does not|did not|will not|cannot)\s+)?"
    rf"(?P<verb>{_VERB}|had)\s+[^.;:!?]{{1,200}}$",
    re.I,
)
_LEADING = re.compile(
    r"^(?:(?:and|but)\s+)?(?:(?:it|they|this|that)\s+(?:also\s+)?|also\s+)?", re.I,
)
_PRONOUN = re.compile(r"^(?:it|they|this|that)\b", re.I)
_SEPARATOR = re.compile(r"(?:,\s*)?(?:and|but)\s*$", re.I)


@dataclass(frozen=True, slots=True)
class StandaloneResult:
    text: str | None
    status: StandaloneStatus
    inherited_start: int | None = None
    inherited_end: int | None = None
    subject: str | None = None
    outcome: str | None = None


def validate_standalone(source: str, start: int, end: int) -> StandaloneResult:
    """Accept full clauses; rebuild only an adjacent, explicitly shared subject."""

    raw = source[start:end].strip()
    head = _LEADING.match(raw)
    assert head is not None
    predicate = raw[head.end():].rstrip(".!? ")
    pronoun = bool(_PRONOUN.match(raw))
    verb = _PREDICATE.fullmatch(predicate)
    comparative = _COMPARATIVE.fullmatch(predicate)
    fragment = pronoun or bool(verb or comparative) or head.end() > 0
    if not fragment:
        return StandaloneResult(text=raw, status="complete")
    if not (verb or comparative):
        return StandaloneResult(text=None, status="uncertain" if pronoun else "incomplete")

    preceding = source[:start]
    if pronoun:
        boundary = re.search(r"[.!?]\s*$", preceding)
    else:
        boundary = _SEPARATOR.search(preceding)
    if boundary is None:
        return StandaloneResult(text=None, status="uncertain" if pronoun else "incomplete")
    prior_end = boundary.start()
    prior_start = max(preceding.rfind(mark, 0, prior_end) for mark in ".!?;") + 1
    clause = preceding[prior_start:prior_end].strip()
    match = _ANTECEDENT.fullmatch(clause)
    if match is None:
        return StandaloneResult(text=None, status="uncertain" if pronoun else "incomplete")
    subject = match.group("subject").strip()
    if re.search(r"\b(?:and|or)\b", subject, re.I) or _PRONOUN.match(subject):
        return StandaloneResult(text=None, status="uncertain")
    subject_start = preceding.find(subject, prior_start, prior_end)
    if subject_start < 0:
        return StandaloneResult(text=None, status="uncertain")
    modal = match.group("modal")
    if modal and ("not" in modal or modal == "cannot") and not (
        not pronoun and boundary.group().strip().endswith("but")
    ):
        return StandaloneResult(text=None, status="uncertain")
    inherited_modal = modal if modal and "not" not in modal and modal != "cannot" else None
    prefix = " ".join(part for part in (subject, inherited_modal, "had" if comparative else None)
                      if part)
    normalized = f"{prefix} {predicate}."
    assert verb is not None or comparative is not None
    outcome = verb.group("outcome") if verb is not None else (
        comparative.group("outcome") if comparative is not None else ""
    )
    return StandaloneResult(
        text=normalized, status="reconstructed", inherited_start=subject_start,
        inherited_end=subject_start + len(subject), subject=subject,
        outcome=outcome,
    )
