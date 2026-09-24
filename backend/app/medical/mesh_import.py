"""Import NLM's official annual MeSH descriptor XML into a local search index."""

import argparse
import gzip
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, cast

import httpx

from app.medical.mesh import normalize_term

NLM_SOURCE = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/"
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def import_mesh_xml(
    *, source_path: Path, index_path: Path, release: str,
    source_url: str | None = None, replace: bool = False,
) -> int:
    """Atomically build a descriptor/entry-term index from NLM XML or gzip XML."""

    if not re.fullmatch(r"20\d{2}", release):
        raise ValueError("MeSH release must be a four-digit production year")
    if index_path.exists() and not replace:
        raise FileExistsError("MeSH index exists; pass --replace for an intentional update")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix="mesh-", suffix=".sqlite3", dir=index_path.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with closing(sqlite3.connect(temporary)) as connection:
            connection.executescript(
                """CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                   CREATE TABLE descriptor (
                     id TEXT PRIMARY KEY, label TEXT NOT NULL, tree_numbers TEXT NOT NULL
                   );
                   CREATE TABLE alias (
                     term_norm TEXT NOT NULL, descriptor_id TEXT NOT NULL,
                     match_type TEXT NOT NULL,
                     PRIMARY KEY (term_norm, descriptor_id)
                   );
                   CREATE INDEX alias_term ON alias(term_norm);"""
            )
            count = _read_descriptors(source_path, connection)
            if count == 0:
                raise ValueError("No MeSH descriptor records were found")
            digest = hashlib.sha256()
            with source_path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            metadata = {
                "source": "nlm_mesh_descriptor_xml",
                "release": release,
                "source_url": source_url or "local_official_xml",
                "source_sha256": digest.hexdigest(),
                "imported_at": datetime.now(UTC).isoformat(),
                "descriptor_count": str(count),
            }
            connection.executemany(
                "INSERT INTO metadata (key, value) VALUES (?, ?)", metadata.items()
            )
            connection.commit()
        os.replace(temporary, index_path)
        return count
    finally:
        temporary.unlink(missing_ok=True)


def _read_descriptors(source_path: Path, connection: sqlite3.Connection) -> int:
    opener = gzip.open if source_path.suffix == ".gz" else Path.open
    with opener(source_path, "rb") as source:
        return _parse_xml(cast(IO[bytes], source), connection)


def _parse_xml(source: IO[bytes], connection: sqlite3.Connection) -> int:
    events = ET.iterparse(source, events=("start", "end"))
    _, root = next(events)
    if root.tag != "DescriptorRecordSet":
        raise ValueError("Expected an NLM MeSH DescriptorRecordSet")
    count = 0
    for event, record in events:
        if event != "end" or record.tag != "DescriptorRecord":
            continue
        mesh_id = record.findtext("DescriptorUI")
        label = record.findtext("DescriptorName/String")
        if mesh_id is None or label is None or not re.fullmatch(r"D\d+", mesh_id):
            raise ValueError("Invalid MeSH descriptor ID or label")
        trees = [node.text for node in record.findall("TreeNumberList/TreeNumber") if node.text]
        connection.execute(
            "INSERT INTO descriptor (id, label, tree_numbers) VALUES (?, ?, ?)",
            (mesh_id, label, json.dumps(trees)),
        )
        _insert_alias(connection, label, mesh_id, "exact")
        for term in record.findall("ConceptList/Concept/TermList/Term/String"):
            if term.text:
                _insert_alias(connection, term.text, mesh_id, "synonym")
        count += 1
        root.clear()
    return count


def _insert_alias(
    connection: sqlite3.Connection, term: str, mesh_id: str, match_type: str
) -> None:
    normalized = normalize_term(term)
    if normalized:
        connection.execute(
            """INSERT INTO alias (term_norm, descriptor_id, match_type)
               VALUES (?, ?, ?)
               ON CONFLICT (term_norm, descriptor_id) DO UPDATE SET match_type =
                 CASE WHEN excluded.match_type = 'exact' THEN 'exact' ELSE match_type END""",
            (normalized, mesh_id, match_type),
        )


def _download_release(*, release: str, directory: Path) -> Path:
    """Download only the fixed NLM descriptor URL; never fetch a caller URL."""

    destination = directory / f"desc{release}.gz"
    total = 0
    with httpx.stream(
        "GET", f"{NLM_SOURCE}desc{release}.gz", timeout=60, follow_redirects=False
    ) as response:
        response.raise_for_status()
        with destination.open("wb") as output:
            # NLM serves this .gz with Content-Encoding: x-gzip; keep raw bytes.
            for chunk in response.iter_raw():
                total += len(chunk)
                if total > _MAX_DOWNLOAD_BYTES:
                    raise ValueError("NLM MeSH download exceeds safety limit")
                output.write(chunk)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, help="NLM production year, e.g. 2026")
    parser.add_argument("--index", type=Path, required=True, help="Local SQLite index path")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--source", type=Path, help="Previously downloaded official descriptor XML/gz"
    )
    source.add_argument("--download", action="store_true", help="Fetch fixed NLM descriptor URL")
    parser.add_argument(
        "--replace", action="store_true", help="Replace an existing index atomically"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="nlm-mesh-") as directory:
        source_path = (
            _download_release(release=args.release, directory=Path(directory))
            if args.download else args.source
        )
        count = import_mesh_xml(
            source_path=source_path, index_path=args.index, release=args.release,
            source_url=f"{NLM_SOURCE}desc{args.release}.gz" if args.download else None,
            replace=args.replace,
        )
    print(f"Imported {count} MeSH descriptors from release {args.release} into {args.index}")


if __name__ == "__main__":
    main()
