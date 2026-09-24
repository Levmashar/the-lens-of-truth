"""MeSH descriptor lookup over an imported official NLM release."""

import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol, cast

from app.medical.entities import MatchType

_WORDS = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


def normalize_term(value: str) -> str:
    """Apply the same conservative lexical normalization at import and lookup."""

    return " ".join(_WORDS.findall(unicodedata.normalize("NFKC", value).casefold()))


@dataclass(frozen=True, slots=True)
class MeshMatch:
    """One MeSH descriptor candidate with phrase-relative source offsets."""

    surface_text: str
    start: int
    end: int
    mesh_id: str
    preferred_name: str
    confidence: float
    match_type: MatchType = "exact"
    terminology_version: str = "fixture"
    terminology_sha256: str | None = None
    tree_numbers: tuple[str, ...] = ()


class MeshProvider(Protocol):
    def find_mentions(self, phrase: str) -> tuple[MeshMatch, ...]: ...

    def lookup(self, term: str) -> tuple[MeshMatch, ...]: ...

    def candidates(self, term: str, *, limit: int = 3) -> tuple[MeshMatch, ...]: ...


@dataclass(frozen=True, slots=True)
class UnconfiguredMeshProvider:
    """Safe fallback when no official index has been imported."""

    def find_mentions(self, phrase: str) -> tuple[MeshMatch, ...]:
        del phrase
        return ()

    def lookup(self, term: str) -> tuple[MeshMatch, ...]:
        del term
        return ()

    def candidates(self, term: str, *, limit: int = 3) -> tuple[MeshMatch, ...]:
        del term, limit
        return ()


@dataclass(frozen=True, slots=True)
class LocalMeshProvider:
    """Caller-supplied fixture mappings for isolated tests only."""

    aliases: dict[str, tuple[str, str, float]]

    def lookup(self, term: str) -> tuple[MeshMatch, ...]:
        return tuple(
            match for match in self.find_mentions(term)
            if match.start == 0 and match.end == len(term)
        )

    def candidates(self, term: str, *, limit: int = 3) -> tuple[MeshMatch, ...]:
        return self.lookup(term)[:limit]

    def find_mentions(self, phrase: str) -> tuple[MeshMatch, ...]:
        matches: list[MeshMatch] = []
        for alias, (mesh_id, preferred_name, confidence) in self.aliases.items():
            pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
            for match in re.finditer(pattern, phrase, flags=re.IGNORECASE):
                matches.append(
                    MeshMatch(
                        surface_text=match.group(), start=match.start(), end=match.end(),
                        mesh_id=mesh_id, preferred_name=preferred_name, confidence=confidence,
                        match_type="exact" if alias.casefold() == preferred_name.casefold()
                        else "synonym",
                    )
                )
        return tuple(matches)


class IndexedMeshProvider:
    """Read-only, bounded lookups against a versioned official MeSH SQLite index."""

    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path.resolve(strict=True)
        with closing(self._connect()) as connection:
            release = connection.execute(
                "SELECT value FROM metadata WHERE key = 'release'"
            ).fetchone()
            source = connection.execute(
                "SELECT value FROM metadata WHERE key = 'source'"
            ).fetchone()
            digest = connection.execute(
                "SELECT value FROM metadata WHERE key = 'source_sha256'"
            ).fetchone()
        if release is None or source is None or source[0] != "nlm_mesh_descriptor_xml":
            raise ValueError("Not an imported NLM MeSH descriptor index")
        self.release: str = release[0]
        self.source_sha256: str | None = digest[0] if digest else None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"{self.index_path.as_uri()}?mode=ro", uri=True)

    def lookup(self, term: str) -> tuple[MeshMatch, ...]:
        """Exact preferred-name or entry-term lookup for a complete surface."""

        normalized = normalize_term(term)
        if not normalized:
            return ()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT a.descriptor_id, d.label, d.tree_numbers, a.match_type
                   FROM alias AS a JOIN descriptor AS d ON d.id = a.descriptor_id
                   WHERE a.term_norm = ?
                   ORDER BY CASE a.match_type WHEN 'exact' THEN 0 ELSE 1 END,
                            a.descriptor_id LIMIT 4""",
                (normalized,),
            ).fetchall()
        return tuple(
            MeshMatch(
                surface_text=term, start=0, end=len(term), mesh_id=row[0],
                preferred_name=row[1], confidence=1.0 if row[3] == "exact" else 0.95,
                match_type=row[3], terminology_version=self.release,
                terminology_sha256=self.source_sha256,
                tree_numbers=tuple(json.loads(row[2])),
            )
            for row in rows
        )

    def candidates(self, term: str, *, limit: int = 3) -> tuple[MeshMatch, ...]:
        """Return exact/alias candidates, or low-confidence fuzzy suggestions."""

        if not 1 <= limit <= 3:
            raise ValueError("candidate limit must be between 1 and 3")
        direct = self.lookup(term)
        if direct:
            return direct[:limit]
        normalized = normalize_term(term)
        if len(normalized) < 4:
            return ()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT a.term_norm, a.descriptor_id, d.label, d.tree_numbers
                   FROM alias AS a JOIN descriptor AS d ON d.id = a.descriptor_id
                   WHERE a.term_norm LIKE ? LIMIT 80""",
                (normalized[:4] + "%",),
            ).fetchall()
        suggestions: dict[str, MeshMatch] = {}
        for alias, mesh_id, label, tree_json in rows:
            ratio = SequenceMatcher(None, normalized, alias).ratio()
            if ratio < 0.75:
                continue
            match = MeshMatch(
                surface_text=term, start=0, end=len(term), mesh_id=mesh_id,
                preferred_name=label, confidence=min(0.79, round(ratio * 0.79, 3)),
                match_type="fuzzy", terminology_version=self.release,
                terminology_sha256=self.source_sha256,
                tree_numbers=tuple(json.loads(tree_json)),
            )
            previous = suggestions.get(mesh_id)
            if previous is None or match.confidence > previous.confidence:
                suggestions[mesh_id] = match
        return tuple(sorted(
            suggestions.values(), key=lambda item: (-item.confidence, item.mesh_id)
        )[:limit])

    def find_mentions(self, phrase: str) -> tuple[MeshMatch, ...]:
        """Look up bounded source subphrases, keeping offsets and all ambiguities."""

        tokens = list(_WORDS.finditer(phrase[:256]))[:20]
        spans: dict[tuple[int, int], str] = {}
        for start_index in range(len(tokens)):
            for end_index in range(start_index, min(len(tokens), start_index + 8)):
                start, end = tokens[start_index].start(), tokens[end_index].end()
                spans[(start, end)] = normalize_term(phrase[start:end])
        if not spans:
            return ()
        terms = tuple(set(spans.values()))
        placeholders = ",".join("?" for _ in terms)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""SELECT a.term_norm, a.descriptor_id, d.label, d.tree_numbers,
                           a.match_type
                    FROM alias AS a JOIN descriptor AS d ON d.id = a.descriptor_id
                    WHERE a.term_norm IN ({placeholders})""",
                terms,
            ).fetchall()
        by_term: dict[str, list[tuple[str, str, str, str]]] = {}
        for term_norm, mesh_id, label, tree_json, match_type in rows:
            by_term.setdefault(term_norm, []).append((mesh_id, label, tree_json, match_type))
        matches = [
            MeshMatch(
                surface_text=phrase[start:end], start=start, end=end, mesh_id=mesh_id,
                preferred_name=label, confidence=1.0 if match_type == "exact" else 0.95,
                match_type=cast(MatchType, match_type), terminology_version=self.release,
                terminology_sha256=self.source_sha256,
                tree_numbers=tuple(json.loads(tree_json)),
            )
            for (start, end), term in spans.items()
            for mesh_id, label, tree_json, match_type in by_term.get(term, ())
        ]
        if not matches and len(phrase) <= 256:
            matches.extend(self.candidates(phrase))
        return tuple(sorted(
            matches, key=lambda item: (item.start, -(item.end - item.start),
                                       -item.confidence, item.mesh_id)
        ))
