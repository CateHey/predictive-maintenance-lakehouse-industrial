"""Streaming simulator for NASA C-MAPSS FD001 turbofan dataset.

Reads raw sensor data from space-separated text files and emits timestamped
JSON batches at configurable intervals, simulating real-time telemetry from
industrial rotating equipment (haul truck engines, mill drives).

Pandas only — designed to run locally or on a single-node Databricks driver.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from loguru import logger

CMAPSS_COLUMNS: list[str] = [
    "unit_id",
    "cycle",
    "op_setting_1",
    "op_setting_2",
    "op_setting_3",
    *(f"s{i}" for i in range(1, 22)),
]

_shutdown_requested: bool = False


def _handle_sigint(signum: int, frame: Any) -> None:
    """Set shutdown flag on SIGINT for graceful termination."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.warning("Shutdown requested (Ctrl+C) — finishing current batch")


def configure_logging(log_level: str = "INFO") -> None:
    """Configure loguru with structured console and file sinks.

    Args:
        log_level: Minimum severity to emit. One of DEBUG, INFO, WARNING, ERROR.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
    )
    Path("logs").mkdir(exist_ok=True)
    logger.add(
        "logs/streaming_simulator.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        serialize=True,
    )


def load_cmapss_data(file_path: Path) -> pd.DataFrame:
    """Load and parse a NASA C-MAPSS space-separated text file.

    The C-MAPSS format has no header row. Columns are:
    unit_id, cycle, 3 operational settings, 21 sensor readings.

    Args:
        file_path: Path to the raw FD001 text file (e.g. train_FD001.txt).

    Returns:
        Parsed DataFrame with named columns.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If the file has an unexpected number of columns.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    df = pd.read_csv(file_path, sep=r"\s+", header=None)

    if df.shape[1] != len(CMAPSS_COLUMNS):
        raise ValueError(
            f"Expected {len(CMAPSS_COLUMNS)} columns, got {df.shape[1]}. "
            f"Verify this is a valid C-MAPSS file."
        )

    df.columns = pd.Index(CMAPSS_COLUMNS)
    df["unit_id"] = df["unit_id"].astype(int)
    df["cycle"] = df["cycle"].astype(int)

    logger.info(
        "Loaded {records} records from {file} ({units} units, cycles {min_c}–{max_c})",
        records=len(df),
        file=file_path.name,
        units=df["unit_id"].nunique(),
        min_c=df["cycle"].min(),
        max_c=df["cycle"].max(),
    )
    return df


def generate_batches(
    df: pd.DataFrame,
    batch_size: int = 10,
) -> Iterator[list[dict[str, Any]]]:
    """Yield fixed-size batches of sensor readings as lists of dicts.

    Each record is enriched with an ISO-8601 timestamp at emission time.

    Args:
        df: Full sensor DataFrame.
        batch_size: Number of records per batch.

    Yields:
        List of row dictionaries, each containing a ``timestamp`` field.
    """
    for start_idx in range(0, len(df), batch_size):
        batch_df = df.iloc[start_idx : start_idx + batch_size]
        records = batch_df.to_dict(orient="records")
        emission_ts = datetime.now(tz=timezone.utc).isoformat()
        for record in records:
            record["timestamp"] = emission_ts
        yield records


def write_batch(
    batch: list[dict[str, Any]],
    output_dir: Path,
    batch_number: int,
) -> Path:
    """Write a single batch to a numbered JSON file.

    Args:
        batch: List of sensor reading dictionaries.
        output_dir: Directory to write batch files into.
        batch_number: Sequential batch identifier (zero-padded in filename).

    Returns:
        Path to the written JSON file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"batch_{batch_number:06d}.json"

    with open(file_path, "w") as f:
        json.dump(batch, f, indent=2)

    return file_path


def run_simulator(
    input_path: Path,
    output_dir: Path,
    batch_size: int = 10,
    delay_seconds: float = 2.0,
    max_batches: int | None = None,
) -> int:
    """Run the streaming simulator end-to-end.

    Emits JSON batch files at a configurable cadence until all data is
    exhausted, the batch limit is reached, or Ctrl+C is pressed.

    Args:
        input_path: Path to the raw C-MAPSS data file.
        output_dir: Directory for output JSON batch files.
        batch_size: Number of sensor readings per batch.
        delay_seconds: Seconds to wait between batch emissions.
        max_batches: Stop after this many batches. None = unlimited.

    Returns:
        Total number of batches written.
    """
    global _shutdown_requested
    _shutdown_requested = False
    signal.signal(signal.SIGINT, _handle_sigint)

    df = load_cmapss_data(input_path)
    total_possible = (len(df) + batch_size - 1) // batch_size
    effective_max = min(total_possible, max_batches) if max_batches else total_possible

    logger.info(
        "Starting simulator: batch_size={bs}, delay={delay}s, "
        "max_batches={mb}, output={out}",
        bs=batch_size,
        delay=delay_seconds,
        mb=effective_max,
        out=output_dir,
    )

    total_records = 0
    batch_number = 0

    for batch_number, batch in enumerate(generate_batches(df, batch_size), start=1):
        if _shutdown_requested:
            logger.warning("Graceful shutdown — stopping before batch {n}", n=batch_number)
            batch_number -= 1
            break

        file_path = write_batch(batch, output_dir, batch_number)
        total_records += len(batch)

        logger.info(
            "Batch {n} written, {count} records, next in {delay}s "
            "({progress:.1f}% complete)",
            n=batch_number,
            count=len(batch),
            delay=delay_seconds,
            progress=(total_records / len(df)) * 100,
        )

        if max_batches and batch_number >= max_batches:
            logger.info("Reached max_batches limit ({mb})", mb=max_batches)
            break

        if batch_number < effective_max:
            time.sleep(delay_seconds)

    logger.success(
        "Simulation complete: {batches} batches, {records} records emitted to {out}",
        batches=batch_number,
        records=total_records,
        out=output_dir,
    )
    return batch_number


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the streaming simulator.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Simulate streaming sensor telemetry from NASA C-MAPSS FD001 data",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/train_FD001.txt"),
        help="Path to input C-MAPSS text file (default: data/raw/train_FD001.txt)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/streaming"),
        help="Output directory for JSON batches (default: data/streaming)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of sensor readings per batch (default: 10)",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=2.0,
        help="Seconds between batch emissions (default: 2.0)",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Stop after N batches (default: unlimited)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    configure_logging(args.log_level)
    run_simulator(
        input_path=args.input,
        output_dir=args.output,
        batch_size=args.batch_size,
        delay_seconds=args.delay_seconds,
        max_batches=args.max_batches,
    )
