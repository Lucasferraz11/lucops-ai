import argparse
from pathlib import Path

from .application import analyze_csv
from .rules import is_positive_amount
from .status import get_quality_status


def main():
    parser = argparse.ArgumentParser(
        description="LucOps AI - Data Quality Analysis"
    )

    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to the CSV file",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/quality_report.txt"),
        help="Path to save the quality report",
    )

    args = parser.parse_args()

    try:
        result = analyze_csv(
            file_path=args.csv_file,
            output_path=args.output,
            required_columns=[
                "id_transacao",
                "cliente_id",
                "valor",
            ],
            rules={"valor": is_positive_amount},
            unique_fields=["id_transacao"],
        )
    except FileNotFoundError:
        parser.error(
            f"Arquivo CSV não encontrado: {args.csv_file}"
        )
    except ValueError as exc:
        parser.error(
            f"CSV inválido: {exc}"
        )

    quality_status = get_quality_status(result.summary)

    print(result.report)
    print(f"\nStatus da qualidade: {quality_status}")
    print(f"\nRelatório salvo em: {result.saved_path}")


if __name__ == "__main__":
    main()
