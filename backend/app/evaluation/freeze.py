"""Read-only capture of retained recent controls and sanitized gateway discovery."""

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.adapters.model_catalog import discover_models
from app.core.config import Settings
from app.evaluation.artifacts import runtime_directory, save_artifact
from app.judging.config import configured_slots
from app.models.analysis_run import AnalysisRunRecord
from app.models.claim import Claim
from app.models.submission import Submission
from app.validation.replay import capture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    parser.add_argument("--database-url")
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--analysis", action="append", type=UUID,
                        help="Capture explicit retained analyses without starting the worker")
    args = parser.parse_args()
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test only")
    directory = runtime_directory(args.runtime)
    slots = configured_slots(settings)
    if args.catalog:
        catalog = asyncio.run(discover_models(slots[0]))
        path = save_artifact(directory, "catalog", {"models": catalog}, settings)
        print(path)
        wanted = ("openai/gpt-6.1-sol", "openai/gpt-6-astra",
                  "google/gemini-2.5-pro", "google/gemini-3.8-flash",
                  "anthropic/claude-sonnet-5.5", "alibaba/qwen3.8-max-prime")
        print([r for r in catalog if r["model"] in wanted and r["eligible"]])
    engine = create_engine(args.database_url or settings.database_url)
    with Session(engine) as session:
        if args.analysis:
            for identifier in args.analysis:
                data = capture(session, identifier)
                path = save_artifact(directory, "baseline", data, settings)
                print(identifier, data.get("availability"), path.name)
            return
        rows = session.execute(select(AnalysisRunRecord.id, Claim.normalized_text).join(
            Submission, Submission.id == AnalysisRunRecord.submission_id,
        ).join(Claim, Claim.submission_id == Submission.id).order_by(
            AnalysisRunRecord.created_at.desc(),
        ).limit(30)).all()
        seen: set[str] = set()
        for identifier, text in rows:
            topic = next((t for t in ("smoking", "sunscreen", "soy", "carrots", "vitamin", "blood")
                          if t in (text or "").casefold()), None)
            if not topic or topic in seen:
                continue
            data = capture(session, identifier)
            path = save_artifact(directory, "baseline", data, settings)
            print(identifier, topic, data.get("availability"), path.name)
            seen.add(topic)


if __name__ == "__main__":
    main()
