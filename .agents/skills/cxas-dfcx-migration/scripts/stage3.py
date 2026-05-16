#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Stage 3: parent-child topology wiring for consolidated CXAS agents.

This is a thin Rich/CLI wrapper around
:mod:`cxas_scrapi.migration.topology_wirer`. The wiring logic itself —
hub-and-spoke vs preserve-hierarchy, cycle breaking, the CXAS
``update_agent`` push, and root-agent reset — lives in the migration
package so the CLI and any notebook can call it without re-implementing.

Two modes:

  --hub-and-spoke (default)
    Root.children = every non-root group.
    Non-root.children = [] (peer transfers route via root).

  --preserve-hierarchy
    Derive children from the source DFCX dep graph with cycle breaking.

Idempotent: safe to re-run. Doesn't touch instructions, tools, or variables.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bundle  # noqa: E402
import _phase_tracker  # noqa: E402
import _prompts  # noqa: E402
import _shared  # noqa: E402

from cxas_scrapi.migration.topology_wirer import (  # noqa: E402
    apply_topology as _apply_topology,
)
from cxas_scrapi.migration.topology_wirer import (  # noqa: E402
    compute_group_children,
    set_app_root_agent,
)

logger = logging.getLogger(__name__)
console = Console()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Stage 3: rewire consolidated agent parent-child topology from the "
            "source DFCX dep graph. Idempotent."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--ir-bundle", help="Path to <target>_ir.json")
    src.add_argument(
        "--target-name", help="Resolves to <target>_ir.json in cwd"
    )
    p.add_argument("--project-id", help="Override bundle project ID")
    p.add_argument("--location", help="Override bundle location")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--hub-and-spoke",
        dest="mode",
        action="store_const",
        const="hub",
        help=(
            "(default) Root has every non-root group as a direct child; "
            "non-root groups have no children. Peer transfers route via root."
        ),
    )
    mode.add_argument(
        "--preserve-hierarchy",
        dest="mode",
        action="store_const",
        const="hierarchy",
        help=(
            "Derive children from the source DFCX dep graph, breaking cycles. "
            "Use only when the source has a true hierarchy worth preserving."
        ),
    )
    p.set_defaults(mode="hub")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=("Print the proposed parent → children mapping without applying."),
    )
    p.add_argument(
        "--no-set-root",
        action="store_true",
        help=("Skip resetting the app's root_agent (keep whatever is set)."),
    )
    p.add_argument("--yes", "-y", action="store_true", help="Non-interactive.")
    return p


def _resolve_bundle_path(args) -> str:
    if args.ir_bundle:
        return args.ir_bundle
    path = _bundle.find_default_bundle(args.target_name)
    if not path:
        console.print(
            "[red]No IR bundle found.[/] Run migrate.py + stage1.py first."
        )
        sys.exit(1)
    return path


def _render_proposed_table(children: dict[str, set[str]]) -> Table:
    table = Table(title="Proposed parent → children (from source dep graph)")
    table.add_column("Parent group", style="cyan")
    table.add_column("Children", style="magenta")
    table.add_column("Count", justify="right")
    for parent, child_groups in children.items():
        names = sorted(child_groups)
        table.add_row(
            parent,
            ", ".join(names) if names else "[dim](none)[/]",
            str(len(names)),
        )
    return table


def _apply_topology_with_rich(
    bundle: _bundle.IRBundle,
    children: dict[str, set[str]],
    dry_run: bool,
) -> tuple[int, int, int]:
    """Print the proposed mapping and forward to topology_wirer, surfacing
    per-update progress in the Rich console."""

    def _progress(event: str, payload) -> None:
        if event == "missing_groups":
            console.print(
                f"[yellow]These groups have no resource_name in the bundle "
                f"(skipped): {payload}[/]"
            )
        elif event == "start":
            console.print(_render_proposed_table(payload))
            if dry_run:
                console.print("[yellow]--dry-run set; not applying.[/]")
        elif event == "updated":
            console.print(
                f"  [green]updated[/] {payload['parent']} → "
                f"{payload['child_count']} children"
            )
        elif event == "failed":
            console.print(
                f"  [red]failed[/] {payload['parent']}: {payload['error']}"
            )

    return _apply_topology(
        bundle,
        children,
        dry_run=dry_run,
        progress=_progress,
    )


def _maybe_set_root_with_rich(bundle: _bundle.IRBundle) -> None:
    ok, msg = set_app_root_agent(bundle)
    if ok:
        console.print(f"[green]{msg}[/]")
    elif "no_grouping" in msg or msg.startswith(
        ("No grouping", "No is_root")
    ):
        return
    else:
        console.print(f"[yellow]{msg}[/]")


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

    if not bundle.grouping:
        console.print(
            "[red]Bundle has no `grouping` field.[/] Stage 3 only runs "
            "after Stage 1 consolidation. If you ran stage1.py with "
            "--no-consolidate, the original 1:1 topology from migrate.py "
            "is still in effect and Stage 3 isn't needed."
        )
        sys.exit(1)

    started_at = datetime.now()

    mode_label = (
        "hub-and-spoke (root has all groups as direct children)"
        if args.mode == "hub"
        else "preserve-hierarchy (source dep graph, cycles broken)"
    )
    with tracker.phase("Compute topology", mode_label):
        children = compute_group_children(bundle, mode=args.mode)

    with tracker.phase("Apply topology", "update_agent per consolidated group"):
        updated, skipped, failed = _apply_topology_with_rich(
            bundle, children, args.dry_run
        )

    if not args.no_set_root and not args.dry_run:
        with tracker.phase("Root agent", "set app.root_agent to is_root group"):
            _maybe_set_root_with_rich(bundle)

    if not args.dry_run:
        _bundle.append_stage(
            bundle,
            "stage3",
            "ok" if failed == 0 else "partial",
            started_at,
            notes=(f"updated={updated} skipped={skipped} failed={failed}"),
        )
        _bundle.save(bundle, bundle_path)

    console.print()
    console.print(tracker.summary_table())
    console.print("\n[bold green]Stage 3 complete.[/]")
    console.print(f"  • updated={updated}, skipped={skipped}, failed={failed}")


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
