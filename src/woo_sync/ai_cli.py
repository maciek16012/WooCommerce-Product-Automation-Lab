"""CLI for auditable human-in-the-loop AI content proposals."""

import argparse
import json
import sys
from pathlib import Path

from .ai_providers import PROVIDER_NAMES, get_provider
from .content_proposals import (
    apply_approved,
    build_proposal,
)
from .core import ValidationError
from .proposal_io import (
    load_proposal,
    review_proposal,
    write_materialized_csv,
    write_new_proposal,
)
from .sources import load_source


def add_source_arguments(parser):
    parser.add_argument(
        "source_file",
        type=str,
        help="CSV, JSON albo publiczny URL Google Sheets",
    )

    parser.add_argument(
        "--source-type",
        choices=("auto", "csv", "json", "sheets"),
        default="auto",
    )

    parser.add_argument(
        "--media",
        type=Path,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Human-in-the-loop AI product content workflow"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    propose = commands.add_parser(
        "propose",
        help="Generate a new pending proposal",
    )
    add_source_arguments(propose)
    propose.add_argument(
        "--out",
        type=Path,
        required=True,
    )
    propose.add_argument(
        "--provider",
        choices=PROVIDER_NAMES,
        default="demo",
    )

    approve = commands.add_parser(
        "approve",
        help="Approve one SKU in a proposal",
    )
    approve.add_argument("proposal_file", type=Path)
    approve.add_argument("sku")

    reject = commands.add_parser(
        "reject",
        help="Reject one SKU in a proposal",
    )
    reject.add_argument("proposal_file", type=Path)
    reject.add_argument("sku")

    apply_cmd = commands.add_parser(
        "apply-proposal",
        help="Materialize approved content as sync-compatible CSV",
    )
    add_source_arguments(apply_cmd)
    apply_cmd.add_argument("proposal_file", type=Path)
    apply_cmd.add_argument(
        "--out",
        type=Path,
        required=True,
    )

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "propose":
            if args.out.exists():
                raise ValidationError("Proposal już istnieje; nie zostanie nadpisany")
            rows = load_source(
                args.source_file,
                source_type=args.source_type,
                media_path=args.media,
            )

            proposal = build_proposal(
                rows,
                get_provider(args.provider),
                args.source_file,
            )

            write_new_proposal(
                args.out,
                proposal,
            )

            print(
                json.dumps(
                    {
                        "event": "PROPOSAL_CREATED",
                        "proposal_id": proposal["proposal_id"],
                        "products": len(proposal["items"]),
                        "status": "pending",
                        "provider": args.provider,
                        "output": str(args.out),
                    },
                    ensure_ascii=False,
                )
            )

            return 0

        if args.command in ("approve", "reject"):
            decision = "approved" if args.command == "approve" else "rejected"
            review_proposal(args.proposal_file, args.sku, decision)

            print(
                json.dumps(
                    {
                        "event": "REVIEW_DECISION",
                        "sku": args.sku,
                        "decision": decision,
                        "proposal": str(args.proposal_file),
                    },
                    ensure_ascii=False,
                )
            )

            return 0

        rows = load_source(
            args.source_file,
            source_type=args.source_type,
            media_path=args.media,
        )

        proposal = load_proposal(
            args.proposal_file
        )

        approved = [
            item
            for item in proposal["items"]
            if item["approval"] == "approved"
        ]

        if not approved:
            raise ValidationError(
                "Proposal nie zawiera zatwierdzonych produktów"
            )

        source_skus = {
            row.sku.casefold()
            for row in rows
        }

        missing = [
            item["sku"]
            for item in approved
            if item["sku"].casefold() not in source_skus
        ]

        if missing:
            raise ValidationError(
                "Zatwierdzone SKU nie istnieją w bieżącym źródle: "
                + ", ".join(missing)
            )

        materialized = apply_approved(
            rows,
            proposal,
        )

        write_materialized_csv(
            args.out,
            materialized,
        )

        print(
            json.dumps(
                {
                    "event": "PROPOSAL_MATERIALIZED",
                    "approved": len(approved),
                    "products": len(materialized),
                    "output": str(args.out),
                },
                ensure_ascii=False,
            )
        )

        return 0

    except (ValidationError, OSError, ValueError) as exc:
        message = (
            str(exc)
            if isinstance(exc, ValidationError)
            else "Nie można wykonać operacji AI workflow"
        )

        print(
            "Błąd: " + message,
            file=sys.stderr,
        )

        return 2


if __name__ == "__main__":
    raise SystemExit(main())
