"""Main coordinator — runs the full communication triage pipeline.

This file does not classify emails or talk to the model directly.
It calls the pieces that do the jobs and ensures the full flow
runs in the right order. Every major step is timed and logged.
"""

import asyncio
import time
from pathlib import Path

from dotenv import load_dotenv

from briefing_agent.graph_client.connector import O365Connector
from briefing_agent.pipeline.email_cleaner import EmailCleaner
from briefing_agent.pipeline.processor import CommunicationSummaryProcessor
from briefing_agent.pipeline.briefing_writer import BriefingWriter
from briefing_agent.pipeline.action_exports import ActionExporter
from briefing_agent.config import settings

load_dotenv()


async def run_pipeline() -> None:
    total_start = time.perf_counter()
    print("\n=== O365 Briefing Agent — Communication Triage ===")
    print(f"Model   : {settings.llm_model}")
    print(f"Endpoint: {settings.llm_base_url}")
    print(f"Lookback: {settings.lookback_hours}h\n")

    # ── 1. Fetch messages from O365 ────────────────────────────────────────
    t0 = time.perf_counter()
    print("[1/5] Fetching messages from O365...")
    connector = O365Connector()
    raw_messages = await connector.fetch_messages()
    raw_events = await connector.fetch_events()
    print(f"      → {len(raw_messages)} messages, {len(raw_events)} calendar events  "
          f"({time.perf_counter() - t0:.1f}s)")

    # ── 2. Clean + filter ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    print("[2/5] Cleaning and filtering messages...")
    cleaner = EmailCleaner()
    messages, skipped = cleaner.clean_and_filter(raw_messages)
    print(f"      → {len(messages)} kept, {len(skipped)} skipped  "
          f"({time.perf_counter() - t0:.1f}s)")

    if not messages:
        print("\nNo messages to process. Inbox is quiet — enjoy your day!")
        return

    # ── 3. Triage via local LLM (batched) ─────────────────────────────────
    t0 = time.perf_counter()
    print(f"[3/5] Running triage in batches of {settings.batch_size}...")
    processor = CommunicationSummaryProcessor()
    triage_result = await processor.summarize_messages(messages)
    print(f"      → Classified {sum(len(v) for v in triage_result.values())} messages  "
          f"({time.perf_counter() - t0:.1f}s)")

    # ── 4. Write human-readable briefing ──────────────────────────────────
    t0 = time.perf_counter()
    print("[4/5] Writing daily briefing...")
    writer = BriefingWriter(output_dir=settings.output_dir)
    briefing_path = writer.write(triage_result, events=raw_events)
    print(f"      → {briefing_path}  ({time.perf_counter() - t0:.1f}s)")

    # ── 5. Export action handoff files ────────────────────────────────────
    t0 = time.perf_counter()
    print("[5/5] Exporting action handoff files...")
    exporter = ActionExporter(output_dir=settings.output_dir)
    paths = exporter.export(triage_result)
    for p in paths:
        print(f"      → {p}")
    print(f"      ({time.perf_counter() - t0:.1f}s)")

    print(f"\n✓ Pipeline complete in {time.perf_counter() - total_start:.1f}s")
    print(f"  Briefing: {briefing_path}")


def app() -> None:
    asyncio.run(run_pipeline())


if __name__ == "__main__":
    app()
