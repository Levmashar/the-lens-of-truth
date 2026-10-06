"""Narrow literal polarity cross-check; scope/design still require validation."""

import re

from app.validation.relationship_guards import RelationshipContext

_UP = re.compile(r"\b(?:increas\w*|rais\w*|higher|causes?|risk factor)\b", re.I)
_DOWN = re.compile(r"\b(?:reduc\w*|lower\w*|decreas\w*|protect\w*|prevent\w*)\b", re.I)


def literal_direction(text: str, context: RelationshipContext, *, claim: bool = False
                      ) -> int | None:
    """Only a named subject, effect phrase, then the same named endpoint.

    Conflicting, negated source or intervention-reversal phrases are unresolved.
    This never reads model reasons, infers from p-values or manufactures strength.
    """
    signs = set()
    outcomes = tuple(dict.fromkeys(re.sub(r"^(?:the )?risk of\s+", "", term, flags=re.I)
                                  for term in context.outcome_terms))
    for sentence in re.split(r"[.!?;]\s*", text):
        for exposure in context.exposure_terms:
            for e in re.finditer(r"(?<!\w)" + re.escape(exposure) + r"(?!\w)", sentence, re.I):
                # Lowering X is a different intervention from exposure to X.
                if re.search(r"\b(?:lowering|reducing|reduction of|treating)\s*$",
                             sentence[max(0, e.start()-30):e.start()], re.I):
                    continue
                for outcome in outcomes:
                    for o in re.finditer(r"(?<!\w)" + re.escape(outcome) + r"(?:s)?(?!\w)",
                                         sentence[e.end():], re.I):
                        relation = sentence[e.end():e.end()+o.start()]
                        if len(relation) > 160:
                            continue
                        negated = bool(re.search(r"\b(?:not|never|no|without)\b|n't",
                                                relation, re.I))
                        if negated and not claim:
                            continue
                        up, down = bool(_UP.search(relation)), bool(_DOWN.search(relation))
                        if up != down:
                            signs.add((-1 if down else 1) * (-1 if negated else 1))
    return next(iter(signs)) if len(signs) == 1 else None


def checked_direction(exact_claim: str, finding: str, sources: tuple[str, ...],
                      context: RelationshipContext) -> str | None:
    asserted = literal_direction(exact_claim, context, claim=True)
    found = literal_direction(finding, context)
    sourced = {literal_direction(text, context) for text in sources} - {None}
    if asserted is None or found is None or sourced != {found}:
        return None
    return "supports_claim" if asserted == found else "opposes_claim"
