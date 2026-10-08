"""Reject lexical aliases that cannot establish a medical mention alone."""

from app.medical.mesh import MeshMatch


def unsafe_contextless_alias(match: MeshMatch) -> bool:
    """Preserve explicit names/acronyms without medicalizing ordinary grammar."""

    if match.match_type != "synonym":
        return False
    surface = match.surface_text.casefold()
    # MeSH's WHO entry term also matches the relative pronoun after its
    # case-insensitive lookup. Only the stated acronym establishes that alias;
    # the full organization name remains an independent exact mention.
    if surface == "who" and match.surface_text != "WHO":
        return True
    # The entry term "consumption" also names Economics. In a multiword
    # exposure that isolated generic word does not establish the concept.
    return surface == "consumption"
