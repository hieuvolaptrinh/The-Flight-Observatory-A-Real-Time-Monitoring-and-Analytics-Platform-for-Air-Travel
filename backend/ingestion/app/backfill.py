"""Load a bounded sample per calendar day from historical simulator CSVs."""

import argparse
import asyncio
import csv
from collections import Counter, defaultdict
from pathlib import Path
from random import Random

from app.pipeline import Pipeline


def sample_days(path: Path, per_day: int) -> dict[str, list[dict[str, str]]]:
    days = defaultdict(list)
    counts = Counter()
    random = Random(path.name)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        date_column = next((name for name in ("FL_DATE", "FlightDate") if name in (reader.fieldnames or [])), None)
        if date_column is None:
            raise ValueError(f"{path.name} has no flight date column")
        for row in reader:
            day = row[date_column]
            if not day:
                continue
            sample = days[day]
            counts[day] += 1
            if len(sample) < per_day:
                sample.append(row)
            else:
                position = random.randrange(counts[day])
                if position < per_day:
                    sample[position] = row
    return days


async def load(paths: list[Path], per_day: int) -> None:
    pipeline = Pipeline()
    for path in paths:
        days = await asyncio.to_thread(sample_days, path, per_day)
        counts = await pipeline.ingest_payload({
            "data": [row for day in sorted(days) for row in days[day]],
            "source": f"historical_sample ({path.name}, max {per_day}/day)",
        })
        print(f"{path.name}: {len(days)} days, {counts['inserted_count']} new flights", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="+")
    parser.add_argument("--per-day", type=int, default=100)
    args = parser.parse_args()
    if args.per_day < 1:
        parser.error("--per-day must be positive")
    for path in args.paths:
        if not path.is_file():
            parser.error(f"CSV not found: {path}")
    asyncio.run(load(args.paths, args.per_day))
