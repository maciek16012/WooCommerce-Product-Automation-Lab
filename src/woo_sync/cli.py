"""Multi-source product synchronization CLI with run-level reporting."""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .core import ValidationError, WooClient, sync
from .locking import sync_lock
from .sources import load_source


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Źródło produktów → WooCommerce po SKU; "
            "domyślnie wykonywany jest tylko plan zmian"
        )
    )

    parser.add_argument(
        "command",
        choices=("validate", "sync"),
    )

    parser.add_argument(
        "source_file",
        type=str,
        help="Plik CSV/JSON albo publiczny URL Google Sheets",
    )

    parser.add_argument(
        "--source-type",
        choices=("auto", "csv", "json", "sheets"),
        default="auto",
        help="Typ źródła; auto rozpoznaje plik albo URL Google Sheets",
    )

    parser.add_argument(
        "--media",
        type=Path,
        help=(
            "Manifest mediów dla JSON. "
            "Domyślnie media.local.json obok katalogu."
        ),
    )

    parser.add_argument(
        "--stock-authority",
        choices=("source", "woocommerce"),
        default="source",
        help=(
            "Właściciel stock_quantity. source pozwala źródłu "
            "aktualizować stock; woocommerce zachowuje stock "
            "istniejących produktów po sprzedaży."
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path(".secrets/woocommerce.json"),
    )

    parser.add_argument(
        "--log",
        type=Path,
    )

    args = parser.parse_args(argv)

    if args.command == "validate" and args.apply:
        parser.error("--apply tylko dla sync")

    run_id = uuid.uuid4().hex
    started = time.perf_counter()

    def elapsed_ms():
        return round(
            (time.perf_counter() - started) * 1000,
            3,
        )

    log = (
        args.log
        or Path("logs")
        / (
            datetime.now(timezone.utc)
            .strftime("%Y%m%dT%H%M%S%fZ")
            + ".jsonl"
        )
    )

    try:
        rows = load_source(
            args.source_file,
            source_type=args.source_type,
            media_path=args.media,
        )

        if args.command == "validate":
            duration = elapsed_ms()

            log.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with log.open(
                "x",
                encoding="utf-8",
            ) as stream:
                stream.write(
                    json.dumps(
                        {
                            "event": "VALIDATION",
                            "run_id": run_id,
                            "valid": True,
                            "rows": len(rows),
                            "source": str(args.source_file),
                            "source_type": args.source_type,
                            "duration_ms": duration,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            print(
                f"Źródło poprawne: {len(rows)} produktów"
            )

            return 0

        creds = (
            json.loads(
                args.credentials.read_text(
                    encoding="utf-8-sig"
                )
            )
            if args.credentials.exists()
            else {}
        )

        api = WooClient(
            *[
                os.getenv(key)
                or creds.get(key, "")
                for key in (
                    "WC_URL",
                    "WC_CONSUMER_KEY",
                    "WC_CONSUMER_SECRET",
                )
            ]
        )

        with sync_lock():
            counts = sync(
                rows,
                api,
                args.apply,
                log,
                stock_authority=args.stock_authority,
            )

        duration = elapsed_ms()

        run_summary = {
            "event": "RUN_SUMMARY",
            "run_id": run_id,
            "source": str(args.source_file),
            "source_type": args.source_type,
            "mode": (
                "APPLIED"
                if args.apply
                else "PLAN"
            ),
            "stock_authority": args.stock_authority,
            "duration_ms": duration,
            "counts": counts,
            "requests": api.stats,
        }

        with log.open(
            "a",
            encoding="utf-8",
        ) as stream:
            stream.write(
                json.dumps(
                    run_summary,
                    ensure_ascii=False,
                )
                + "\n"
            )

        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "mode": run_summary["mode"],
                    "counts": counts,
                    "stock_authority": args.stock_authority,
                    "requests": api.stats,
                    "source": str(args.source_file),
                    "duration_ms": duration,
                    "log": str(log),
                },
                ensure_ascii=False,
            )
        )

        return 1 if counts["ERROR"] else 0

    except (
        ValidationError,
        OSError,
        ValueError,
    ) as exc:
        message = (
            str(exc)
            if isinstance(exc, ValidationError)
            else (
                "Nie można odczytać wejścia/konfiguracji "
                "lub zapisać nowego raportu"
            )
        )

        if not log.exists():
            log.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with log.open(
                "x",
                encoding="utf-8",
            ) as stream:
                stream.write(
                    json.dumps(
                        {
                            "action": "ERROR",
                            "phase": "VALIDATION",
                            "run_id": run_id,
                            "source": str(args.source_file),
                            "source_type": args.source_type,
                            "duration_ms": elapsed_ms(),
                            "error": message,
                            "writes": 0,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        print(
            "Błąd: " + message,
            file=sys.stderr,
        )

        return 2
