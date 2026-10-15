
import csv
from collections.abc import Iterable
from pathlib import Path


def load_csv(
    file_path: str | Path,
    required_columns: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    """Read a CSV file and validate required columns."""

    path = Path(file_path)

    with path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("CSV file must contain a header.")

        missing_columns = sorted(
            set(required_columns or [])
            - set(reader.fieldnames)
        )

        if missing_columns:
            raise ValueError(
                "Missing required CSV columns: "
                + ", ".join(missing_columns)
            )

        
        records = []

        for record_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(
                    f"CSV record {record_number} has "
                    "more values than columns."
                )

            if any(value is None for value in row.values()):
                raise ValueError(
                    f"CSV record {record_number} has "
                    "fewer values than columns."
                )

            records.append(dict(row))

        return records
