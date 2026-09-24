"""Combine independently supplied UMLS/MeSH candidates without inventing IDs."""

from dataclasses import dataclass

from app.medical.entities import EntityType, MedicalEntity, MedicalEntityCandidate
from app.medical.mesh import MeshMatch, MeshProvider
from app.medical.umls import UmlsMatch, UmlsProvider
from app.pipeline.pico import NormalizedPico


@dataclass(frozen=True, slots=True)
class MedicalEntityLinker:
    """Link claim-grounded PICO mentions with a conservative confidence threshold."""

    umls: UmlsProvider
    mesh: MeshProvider
    minimum_confidence: float = 0.8

    def link(self, pico: NormalizedPico) -> tuple[MedicalEntity, ...]:
        """Return resolved and explicit unresolved mentions for each PICO slot."""

        entities: list[MedicalEntity] = []
        for entity_type in ("population", "intervention_or_exposure", "comparator", "outcome"):
            phrase = getattr(pico, entity_type)
            if phrase:
                entities.extend(self._link_phrase(phrase, entity_type))
        return tuple(entities)

    def _link_phrase(self, phrase: str, entity_type: EntityType) -> list[MedicalEntity]:
        umls_matches = [
            match for match in self.umls.find_mentions(phrase) if _valid_match(phrase, match)
        ]
        mesh_matches = [
            match for match in self.mesh.find_mentions(phrase) if _valid_match(phrase, match)
        ]
        spans = sorted(
            {(match.start, match.end) for match in umls_matches}
            | {(match.start, match.end) for match in mesh_matches},
            key=lambda span: (-(span[1] - span[0]), span[0]),
        )
        selected: list[tuple[int, int]] = []
        for start, end in spans:
            if not any(
                start < previous_end and end > previous_start
                for previous_start, previous_end in selected
            ):
                selected.append((start, end))
        if not selected:
            return [MedicalEntity(surface_text=phrase, entity_type=entity_type)]

        entities: list[MedicalEntity] = []
        for start, end in sorted(selected):
            umls = _best_umls(umls_matches, start, end)
            mesh_candidates = _mesh_candidates(mesh_matches, start, end)
            mesh = mesh_candidates[0] if len(mesh_candidates) == 1 else None
            ambiguous = len(mesh_candidates) > 1
            if umls and umls.confidence < self.minimum_confidence:
                umls = None
            if mesh and (
                mesh.confidence < self.minimum_confidence or mesh.match_type == "fuzzy"
            ):
                mesh = None
            if (
                umls is not None
                and mesh is not None
                and umls.preferred_name.casefold() != mesh.preferred_name.casefold()
            ):
                # A shared surface is insufficient proof that two concepts are equivalent.
                umls = None
            if ambiguous:
                umls = None
            confidence = min(
                (match.confidence for match in (umls, mesh) if match is not None),
                default=mesh_candidates[0].confidence if mesh_candidates else None,
            )
            preferred_name = (
                umls.preferred_name if umls else mesh.preferred_name if mesh else None
            )
            entities.append(
                MedicalEntity(
                    surface_text=phrase[start:end],
                    entity_type=entity_type,
                    umls_cui=umls.cui if umls else None,
                    umls_version=umls.terminology_version if umls else None,
                    mesh_id=mesh.mesh_id if mesh else None,
                    preferred_name=preferred_name,
                    confidence=confidence,
                    match_type=(
                        mesh.match_type if mesh else mesh_candidates[0].match_type
                        if mesh_candidates else "exact" if umls else "unresolved"
                    ),
                    ambiguous=ambiguous,
                    terminology_source=(
                        "mesh" if mesh_candidates else "umls" if umls else None
                    ),
                    terminology_version=(
                        mesh_candidates[0].terminology_version if mesh_candidates else
                        umls.terminology_version if umls else None
                    ),
                    terminology_sha256=(
                        mesh_candidates[0].terminology_sha256 if mesh_candidates else None
                    ),
                    tree_numbers=mesh.tree_numbers if mesh else (),
                    candidates=tuple(
                        MedicalEntityCandidate(
                            mesh_id=candidate.mesh_id,
                            preferred_name=candidate.preferred_name,
                            match_type=candidate.match_type,
                            confidence=candidate.confidence,
                            terminology_version=candidate.terminology_version,
                            terminology_sha256=candidate.terminology_sha256,
                            tree_numbers=candidate.tree_numbers,
                        )
                        for candidate in mesh_candidates[:3]
                    ) if ambiguous or mesh is None else (),
                )
            )
        return entities


def _valid_match(phrase: str, match: UmlsMatch | MeshMatch) -> bool:
    return (
        0 <= match.start < match.end <= len(phrase)
        and phrase[match.start : match.end] == match.surface_text
        and bool(match.preferred_name.strip())
        and bool((match.cui if isinstance(match, UmlsMatch) else match.mesh_id).strip())
        and 0 <= match.confidence <= 1
    )


def _best_umls(matches: list[UmlsMatch], start: int, end: int) -> UmlsMatch | None:
    candidates = [match for match in matches if (match.start, match.end) == (start, end)]
    return max(candidates, key=lambda match: match.confidence, default=None)


def _mesh_candidates(matches: list[MeshMatch], start: int, end: int) -> list[MeshMatch]:
    candidates = [match for match in matches if (match.start, match.end) == (start, end)]
    by_id: dict[str, MeshMatch] = {}
    for candidate in candidates:
        previous = by_id.get(candidate.mesh_id)
        if previous is None or candidate.confidence > previous.confidence:
            by_id[candidate.mesh_id] = candidate
    return sorted(by_id.values(), key=lambda match: (-match.confidence, match.mesh_id))
