"""Reconcile provider whitespace without relaxing exact source attribution."""


def reconcile_unique_source_span(
    source_text: str, proposed_span: str,
) -> tuple[int, int, str] | None:
    """Return one exact source span when only whitespace runs differ.

    Every non-whitespace character remains exact, including case, punctuation,
    numbers and negation. Whitespace must exist in the same positions between
    those characters; it may not be inserted or removed. Leading and trailing
    whitespace are significant too. Uniqueness covers all whitespace-equivalent
    occurrences, including overlapping ones, rather than only literal matches.

    Offsets refer to the original Unicode source, and the returned text is its
    unchanged substring. An empty, invented or ambiguous proposal returns None.
    """

    if not proposed_span:
        return None
    projected_source, offsets = _project_whitespace(source_text)
    projected_span, _ = _project_whitespace(proposed_span)
    match_start = projected_source.find(projected_span)
    if match_start < 0 or projected_source.find(projected_span, match_start + 1) >= 0:
        return None
    source_start = offsets[match_start][0]
    source_end = offsets[match_start + len(projected_span) - 1][1]
    return source_start, source_end, source_text[source_start:source_end]


def _project_whitespace(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Collapse each run and retain its complete original source boundaries."""

    characters: list[str] = []
    offsets: list[tuple[int, int]] = []
    index = 0
    while index < len(text):
        start = index
        character = text[index]
        index += 1
        if character.isspace():
            while index < len(text) and text[index].isspace():
                index += 1
            character = " "
        characters.append(character)
        offsets.append((start, index))
    return "".join(characters), offsets
