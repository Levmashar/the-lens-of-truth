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
_COMPARATIVE = re.compile(r"^(?P<outcome>(?:lower|higher|more|less)\s+\S.+)$", re.I | re.S)
_ANTECEDENT = re.compile(
    rf"^(?P<subject>[^.;:!?]{{2,160}}?)\s+"
    rf"(?:(?P<modal>may|might|could|can|will|does not|did not|will not|cannot)\s+)?"
    rf"(?P<verb>{_VERB}|had)\s+[^.;:!?]{{1,200}}$",
    re.I,
)
_LEADING = re.compile(
    r"^(?:(?:and|but|plus)\s+)?(?:(?:it|they|this|that|these|those)\s+(?:also\s+)?|also\s+)?", re.I,
)
_PRONOUN = re.compile(r"^(?:it|they|this|that|these|those)\b", re.I)
_SEPARATOR = re.compile(r"(?:,\s*)?(?:and|but)\s*$", re.I)
_REPORTED_SEPARATOR = re.compile(r",\s*(?:(?P<coordinator>and|plus)\s+)?$", re.I)
_REPORTED_GROUP_RESULT = re.compile(
    r"^(?:(?:the|this|our|a|an)\s+)?"
    r"(?:analysis|study|trial|review|report|results|findings|researchers)\s+"
    r"(?:showed|reported|found|observed|identified|documented)\s+"
    r"(?P<result>(?:[^.;:!?]|\.(?<=\d\.)(?=\d)){1,300}?)\s+(?:for|among)\s+"
    r"(?P<subject>[^\s.;:!?][^.;:!?]{1,159})$",
    re.I,
)
_REPORTING_FRAME = re.compile(
    r"^(?:(?:the|this|our|a|an)\s+)?"
    r"(?:analysis|study|trial|review|report|results|findings|researchers)\s+"
    r"(?:(?:did|does|had|has|have|will|would|may|might|could|not|never)\s+)*"
    r"(?:shows?|showed|reports?|reported|finds?|found|observes?|observed|"
    r"identifies|identified|documents?|documented)\b", re.I,
)
_HUMAN_GROUP = re.compile(
    r"\b(?:users|participants|patients|people|persons|adults|children|men|women|"
    r"infants|newborns|workers|individuals|subjects)\b", re.I,
)
_RESULT_METRIC = re.compile(r"\b(?:risks?|rates?|incidence|prevalence)\b", re.I)
_UNASSERTED_RESULT = re.compile(
    r"\b(?:may|might|could|will|would|planned|hypothesized|hypothesised|"
    r"not|no|never|neither|without)\b", re.I,
)


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

    if comparative is not None and not pronoun:
        reported = _reconstruct_reported_comparison(source, start, raw, comparative)
        if reported is not None:
            return reported

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


def _reconstruct_reported_comparison(
    source: str, start: int, raw: str, comparative: re.Match[str],
) -> StandaloneResult | None:
    """Share one explicit group across adjacent reported risk/rate results.

    Unlike a grammatical reporting subject ("the study"), the terminal human
    group in "a risk of Y for X users, plus higher rates of Z" is the actual
    source-stated actor. Only that exact group is inherited. Reporting qualifiers,
    numeric estimates and endpoints of the first result are never borrowed.
    """

    preceding = source[:start]
    boundary = _REPORTED_SEPARATOR.search(preceding)
    if boundary is None or not (
        boundary.group("coordinator") or re.match(r"^(?:and|plus)\b", raw, re.I)
    ):
        return None
    if not _RESULT_METRIC.search(comparative.group("outcome")):
        return None
    prior_end = boundary.start()
    sentence_boundaries = list(re.finditer(r"[.!?;](?:\s+|$)", preceding[:prior_end]))
    prior_start = sentence_boundaries[-1].end() if sentence_boundaries else 0
    original_clause = source[prior_start:prior_end]
    clause = original_clause.strip()
    match = _REPORTED_GROUP_RESULT.fullmatch(clause)
    if match is None:
        # A reporting subject is not a patient/exposure. Do not let an unknown
        # reported-result frame fall through to ordinary grammatical subjects.
        if _REPORTING_FRAME.match(clause):
            return StandaloneResult(text=None, status="incomplete")
        return None
    if _UNASSERTED_RESULT.search(clause):
        return StandaloneResult(text=None, status="incomplete")
    subject = match.group("subject").strip()
    if (
        not _RESULT_METRIC.search(match.group("result"))
        or not _HUMAN_GROUP.search(subject)
        or _PRONOUN.match(subject)
        or re.search(r"\b(?:and|or)\b", subject, re.I)
    ):
        return StandaloneResult(text=None, status="incomplete")
    leading_whitespace = len(original_clause) - len(original_clause.lstrip())
    subject_start = prior_start + leading_whitespace + match.start("subject")
    outcome = comparative.group("outcome")
    return StandaloneResult(
        text=f"{subject} had {outcome}.", status="reconstructed",
        inherited_start=subject_start, inherited_end=subject_start + len(subject),
        subject=subject, outcome=outcome,
    )
