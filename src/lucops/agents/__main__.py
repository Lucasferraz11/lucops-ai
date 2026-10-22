"""Independent investigation CLI; existing CLIs remain unchanged."""

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from .openai_provider import OpenAIProviderError
from .service import investigate_transaction


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="LucOps evidence-based investigation (simulated by default)."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    investigate = commands.add_parser("investigate", help="Investigate one CSV record.")
    investigate.add_argument("csv_file", type=Path)
    investigate.add_argument("--record-index", type=int, required=True)
    investigate.add_argument(
        "--provider",
        choices=("simulated", "openai"),
        default="simulated",
        help="Investigation provider; openai requires explicit backend configuration.",
    )
    investigate.add_argument(
        "--no-ml",
        action="store_true",
        help="Do not request inference; ML unavailability is reported explicitly.",
    )
    investigate.add_argument(
        "--output", type=Path, help="Optionally save complete JSON; must not exist."
    )
    args = parser.parse_args(argv)
    try:
        result = investigate_transaction(
            args.csv_file,
            args.record_index,
            include_ml=not args.no_ml,
            provider_mode=args.provider,
        )
        output = json.dumps(
            asdict(result), ensure_ascii=True, indent=2, allow_nan=False
        )
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(output + "\n")
        print(output)
    except (OSError, ValueError, IndexError, csv.Error, OpenAIProviderError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
