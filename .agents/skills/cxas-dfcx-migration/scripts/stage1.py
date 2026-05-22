#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Stage 1: CXASOptimizer variable dedup + optional Gemini consolidation.

Thin shell over :meth:`MigrationService.run_stage1`. Loads the IR bundle
written by :mod:`migrate`, restores a :class:`MigrationService` from it,
then delegates everything (dedup, consolidator, integrity checks,
topology link, orphan cleanup, version checkpoint, bundle persist) to
the service method.

This script's only skill-specific responsibility is wiring the
interactive grouping review TUI (`cxas_scrapi.migration.grouping_review`) into
the service's ``grouping_callback``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from rich.console import Console
from rich.logging import RichHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bundle  # noqa: E402
import _phase_tracker  # noqa: E402
import _prompts  # noqa: E402
import _shared  # noqa: E402

from cxas_scrapi.migration.service import MigrationService

logger = logging.getLogger(__name__)
console = Console()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Stage 1: variable dedup + optional Gemini consolidation. "
            "Loads <target>_ir.json."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument(
        "--ir-bundle",
        help="Path to <target>_ir.json (defaults to newest in cwd)",
    )
    src.add_argument(
        "--target-name",
        help="Resolves to <target>_ir.json in the cwd",
    )
    p.add_argument("--project-id", help="Override bundle project ID")
    p.add_argument("--location", help="Override bundle location")
    p.add_argument("--yes", "-y", action="store_true", help="Non-interactive.")
    return p


def _resolve_bundle_path(args) -> str:
    if args.ir_bundle:
        return args.ir_bundle
    path = _bundle.find_default_bundle(args.target_name)
    if not path:
        console.print(
            "[red]No IR bundle found.[/] Run migrate.py first, or pass "
            "--ir-bundle / --target-name."
        )
        sys.exit(1)
    return path


async def _run(args) -> None:
    tracker = _phase_tracker.PhaseTracker(console)

    if not _shared.auth_check(console):
        if not args.yes and not _prompts.prompt_yes_no(
            "Proceed anyway?", default=False
        ):
            sys.exit(1)

    bundle_path = _resolve_bundle_path(args)
    console.print(f"[cyan]Loading IR bundle:[/] {bundle_path}")
    bundle = _bundle.load(bundle_path)
    target_name = bundle.config.target_name

    service = MigrationService.restore_from_bundle(
        bundle,
        project_id=args.project_id,
        location=args.location,
    )

    with tracker.phase(
        "Stage 1",
        "variable dedup",
    ):
        await service.run_stage1(
            bundle=bundle,
            version_label="0.0.2",
            persist_bundle_path=bundle_path,
            console=console,
        )

    console.print()
    console.print(tracker.summary_table())
    console.print("\n[bold green]Stage 1 complete.[/]")
    console.print(f"  • IR bundle:        {bundle_path}")
    if bundle.grouping:
        console.print(f"  • Grouping JSON:    {target_name}_grouping.json")
    if bundle.app_url:
        console.print(f"  • App console:      {bundle.app_url}")
    console.print(
        f"\n[dim]Next:[/] [cyan]stage2.py --target-name {target_name}[/]"
        " for instruction state machines + tool mocks + lint + report."
    )


def main() -> None:
    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    args = _build_parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
