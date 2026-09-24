"""Replaceable UMLS vocabulary lookup; no licensed content is shipped."""

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class UmlsMatch:
    """One candidate mention returned by a licensed vocabulary provider."""

    surface_text: str
    start: int
    end: int
    cui: str
    preferred_name: str
    confidence: float
    terminology_version: str = "fixture"


class UmlsProvider(Protocol):
    """Search a phrase for candidates and return phrase-relative offsets."""

    def find_mentions(self, phrase: str) -> tuple[UmlsMatch, ...]: ...


@dataclass(frozen=True, slots=True)
class UnconfiguredUmlsProvider:
    """Default until an authorized UMLS release or API is configured."""

    def find_mentions(self, phrase: str) -> tuple[UmlsMatch, ...]:
        del phrase
        return ()


@dataclass(frozen=True, slots=True)
class LocalUmlsProvider:
    """Fixture-backed exact-alias lookup for tests, not a medical vocabulary."""

    aliases: dict[str, tuple[str, str, float]]

    def find_mentions(self, phrase: str) -> tuple[UmlsMatch, ...]:
        matches: list[UmlsMatch] = []
        for alias, (cui, preferred_name, confidence) in self.aliases.items():
            pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
            for match in re.finditer(pattern, phrase, flags=re.IGNORECASE):
                matches.append(
                    UmlsMatch(
                        surface_text=match.group(),
                        start=match.start(),
                        end=match.end(),
                        cui=cui,
                        preferred_name=preferred_name,
                        confidence=confidence,
                    )
                )
        return tuple(matches)
