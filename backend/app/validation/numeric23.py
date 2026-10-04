"""Numeric defects remain separate from explicitly supplied qualitative findings."""

import re

from app.judging.compact23 import quantitative_claim
from app.judging.models import JudgeDecisionV2
from app.retrieval.models import EvidencePack
from app.validation.assertion_numeric import (
    compare_assertion_numbers,
    quantities,
    without_user_magnitude_references,
)
from app.validation.models import IssueCode, NumericAlignment, ValidationIssue
from app.validation.numeric_effects import NumericSourceFidelity
from app.validation.numeric_occurrences import occurrences as _occurrences

LEGACY_VERSION = "numeric-materiality-1.0"
PREVIOUS_VERSION = "numeric-materiality-1.1"
FIDELITY_VERSION = "numeric-materiality-1.2"
VERSION = "numeric-materiality-1.3"
VERSIONS = {LEGACY_VERSION, PREVIOUS_VERSION, FIDELITY_VERSION, VERSION}


def numeric_issues23(
    decision: JudgeDecisionV2, pack: EvidencePack, *, version: str = VERSION,
) -> tuple[ValidationIssue, ...]:
    if version not in VERSIONS:
        raise ValueError("Unsupported numeric materiality contract")
    issues: list[ValidationIssue] = []
    dependencies = set(decision.conclusion.based_on_statement_ids)
    user_claim = pack.claim_snapshot.standalone_text
    quantitative = quantitative_claim(user_claim)

    def check(target: str, raw: str, proposition: str, sources: tuple[str, ...],
              refs: tuple[str, ...], dependency: bool) -> None:
        if version == LEGACY_VERSION:
            material = quantitative or dependency or quantitative_claim(
                re.sub(r"\bS[1-5]\b", "", proposition),
            ) or bool(re.search(
                r"\b(?:convert\w*|calculat\w*|equivalent|correspond\w*)\b", raw, re.I,
            ) and re.search(r"\d", raw))
        else:
            proposition_without_claim, _ = without_user_magnitude_references(
                proposition, user_claim,
            )
            raw_without_claim, _ = without_user_magnitude_references(raw, user_claim)
            material_effect = quantitative and any(q.kind in {
                "relative_risk", "odds_ratio", "hazard_ratio", "risk_multiple_range",
                "percent_change", "percent_change_range",
            } for q in quantities(raw_without_claim, repaired=True))
            if version == VERSION:
                from app.validation.numeric_effects import (
                    Measure,
                    claim_references,
                    parse_quantities,
                )

                bound, _ = claim_references(raw, user_claim)
                material_effect = material_effect or quantitative and any(q.kind in {
                    Measure.RISK_RATIO, Measure.ODDS_RATIO, Measure.HAZARD_RATIO,
                    Measure.FOLD_CHANGE, Measure.PERCENT_CHANGE,
                } for q in parse_quantities(bound)[0])
            material = dependency or quantitative_claim(
                re.sub(r"\bS[1-5]\b", "", proposition_without_claim),
            ) or material_effect or bool(re.search(
                r"\b(?:convert\w*|calculat\w*|equivalent|correspond\w*)\b", raw, re.I,
            ) and re.search(r"\d", raw_without_claim))
        result = compare_assertion_numbers(
            raw, sources, user_claim=user_claim, repaired=version != LEGACY_VERSION,
        )
        fidelity: tuple[NumericSourceFidelity, ...] = ()
        if version in {FIDELITY_VERSION, VERSION}:
            from app.validation.numeric_effects import source_fidelity

            pairs = tuple(dict.fromkeys((r.evidence_id, r.quote)
                for s in decision.statements for r in s.evidence_refs
                if r.evidence_id in refs and r.quote in sources))
            fidelity, status = source_fidelity(
                raw, pairs, user_claim, followup=version == VERSION,
                statement_sources={s.statement_id: tuple(
                    (r.evidence_id, r.quote) for r in s.evidence_refs)
                    for s in decision.statements if s.statement_id in dependencies},
            )
            result = result.__class__(status=status, reason="source_fidelity_only",
                                      tokens=result.tokens)
        if result.status not in {NumericAlignment.MISMATCH, NumericAlignment.UNCERTAIN}:
            return
        mismatch = result.status == NumericAlignment.MISMATCH
        code = ((IssueCode.STATEMENT_NUMERIC_MISMATCH if mismatch else IssueCode.NUMERIC_UNCERTAIN)
                if material else (IssueCode.OPTIONAL_NUMERIC_DETAIL_INVALID if mismatch else
                                  IssueCode.OPTIONAL_NUMERIC_DETAIL_UNCERTAIN))
        issues.append(ValidationIssue(
            target_type="judge_statement", target_id=target, evidence_refs=refs,
            issue_code=code, severity="fatal" if material and mismatch else "warning",
            observed_value=raw, numeric_diagnostic={**result.diagnostic(), "version": version,
                                                    "material": material,
                                                    "qualitative_proposition": proposition,
                                                    **({"source_fidelity": [
                                                        f.model_dump(mode="json") for f in fidelity
                                                    ]} if version in {
                                                        FIDELITY_VERSION, VERSION} else {}),
                                                    **({"occurrences": [
                                                        o.model_dump(mode="json") for o in
                                                        _occurrences(raw, user_claim)
                                                    ]} if version == VERSION else {}),
                                                    "raw_numeric_content_preserved": True},
            conclusion_dependency=target in dependencies or target == "conclusion",
        ))

    for statement in decision.statements:
        sources = tuple(r.quote for r in statement.evidence_refs)
        refs = tuple(r.evidence_id for r in statement.evidence_refs)
        finding = statement.qualitative_finding or statement.text
        # Both embedded and separately supplied figures are checked, never deleted.
        for text in dict.fromkeys((statement.text, finding)):
            check(statement.statement_id, text, finding, sources, refs,
                  bool(statement.numeric_dependency))
        for detail in dict.fromkeys(statement.numeric_details):
            # A verbatim repeated detail adds no new assertion. Its containing
            # text/finding has already been checked against the same sources.
            if version != LEGACY_VERSION and detail.strip() and any(
                detail.casefold() in text.casefold() for text in (statement.text, finding)
            ):
                continue
            check(statement.statement_id, detail, finding, sources, refs,
                  bool(statement.numeric_dependency))
    conclusion = decision.conclusion
    sources = tuple(r.quote for s in decision.statements if s.statement_id in dependencies
                    for r in s.evidence_refs)
    refs = tuple(dict.fromkeys(r.evidence_id for s in decision.statements
                              if s.statement_id in dependencies for r in s.evidence_refs))
    for text in dict.fromkeys((conclusion.justification,
                              conclusion.qualitative_justification or conclusion.justification)):
        check("conclusion", text, conclusion.qualitative_justification or conclusion.justification,
              sources, refs, bool(conclusion.numeric_dependency))
    return tuple(issues)


def material_issue(issue: ValidationIssue) -> bool:
    return issue.issue_code not in {IssueCode.OPTIONAL_NUMERIC_DETAIL_INVALID,
                                    IssueCode.OPTIONAL_NUMERIC_DETAIL_UNCERTAIN}


def numeric_findings23(decision: JudgeDecisionV2, pack: EvidencePack, *,
                       version: str = VERSION,
                       assessments: dict[str, tuple[str, str, bool]] | None = None
                       ) -> tuple[dict[str, object], ...]:
    """Keep raw fields unchanged; append per-quantity diagnostics, not repaired statements."""
    from app.validation.numeric_effects import (
        Measure,
        NumericFinding,
        compare_to_claim,
        source_fidelity,
    )

    result = []
    pico = pack.claim_snapshot.pico
    magnitude = pico.numeric_effect if pico else None
    for statement in decision.statements:
        finding = statement.qualitative_finding or statement.text
        sources = tuple((r.evidence_id, r.quote) for r in statement.evidence_refs)
        scope, basis, allow_narrower = (assessments or {}).get(
            statement.statement_id, ("aligned", "same_question", False))
        structure = "structured"
        if re.search(r"\d", finding) and not statement.numeric_details:
            structure = "embedded_numeric_assertions"
        items = []
        for text in dict.fromkeys((statement.text, finding, *statement.numeric_details)):
            fidelity, _ = source_fidelity(text, sources, pack.claim_snapshot.standalone_text,
                                         followup=version == VERSION)
            for item in fidelity:
                comparable, effect = compare_to_claim(
                    item, magnitude, " ".join(s for _, s in sources), scope=scope,
                    scope_basis=basis, allow_narrower=allow_narrower,
                    claim_scope_text=pack.claim_snapshot.standalone_text,
                )
                items.append(NumericFinding.model_validate({
                    "version": ("numeric-fidelity-comparability-1.1" if version == VERSION
                                else "numeric-fidelity-comparability-1.0"),
                    "target_id": statement.statement_id,
                    "material": bool(statement.numeric_dependency or magnitude or
                                     quantitative_claim(finding)),
                    "fidelity": item, "comparability": comparable, "numeric_effect": effect,
                    "structure_status": structure,
                    "semantic_scope_checked": assessments is not None,
                }))
        measures = {f.fidelity.asserted.kind for f in items}
        if structure == "embedded_numeric_assertions" and len(measures - {Measure.UNKNOWN}) > 1:
            items = [f.model_copy(update={
                "structure_status": "mixed_measures_in_qualitative_finding",
                "numeric_effect": "noncomparable",
                "comparability": f.comparability.model_copy(update={
                    "status": "not_comparable", "reason": "mixed_unstructured_numeric_measures",
                }),
            }) for f in items]
        for finding_item in items:
            encoded = finding_item.model_dump(mode="json")
            if encoded not in result:
                result.append(encoded)
    return tuple(result)


def numeric_occurrences23(decision: JudgeDecisionV2, pack: EvidencePack
                          ) -> tuple[dict[str, object], ...]:
    """Save original occurrence roles, including references excluded only from fidelity."""
    result: list[dict[str, object]] = []
    for statement in decision.statements:
        for field, texts in (
            ("text", (statement.text,)), ("qualitative_finding", (statement.qualitative_finding,)),
            ("numeric_details", statement.numeric_details),
        ):
            for index, text in enumerate(texts):
                if text is not None:
                    result.extend({"target_id": statement.statement_id, "field": field,
                                   "detail_index": index, **o.model_dump(mode="json")}
                                  for o in _occurrences(text, pack.claim_snapshot.standalone_text))
    for field in ("justification", "qualitative_justification"):
        text = getattr(decision.conclusion, field)
        if text is not None:
            result.extend({"target_id": "conclusion", "field": field,
                           **o.model_dump(mode="json")} for o in
                          _occurrences(text, pack.claim_snapshot.standalone_text))
    return tuple(result)
