"""Download NASA C-MAPSS FD001 dataset from Kaggle via kagglehub.

Uses the KAGGLE_API_TOKEN environment variable for authentication
and copies the relevant FD001 files into data/raw/.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import kagglehub
from loguru import logger

DATASET_HANDLE = "behrad3d/nasa-cmaps"
TARGET_FILES = ["train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt"]
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def configure_logging(log_level: str = "INFO") -> None:
    """Set up structured logging with loguru."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )


def validate_kaggle_token() -> None:
    """Verify KAGGLE_API_TOKEN is set in the environment.

    Raises:
        EnvironmentError: If the token is missing.
    """
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise EnvironmentError(
            "KAGGLE_API_TOKEN environment variable is not set. "
            "Export it as: export KAGGLE_API_TOKEN='{\"username\":\"...\",\"key\":\"...\"}'"
        )
    logger.info("KAGGLE_API_TOKEN found in environment")


def download_dataset() -> Path:
    """Download the NASA C-MAPSS dataset using kagglehub.

    Returns:
        Path to the downloaded dataset directory.
    """
    logger.info(f"Downloading dataset: {DATASET_HANDLE}")
    dataset_path = Path(kagglehub.dataset_download(DATASET_HANDLE))
    logger.info(f"Dataset downloaded to: {dataset_path}")
    return dataset_path


def find_and_copy_files(dataset_path: Path, target_dir: Path) -> list[Path]:
    """Locate FD001 files in the download directory and copy them to target.

    Handles both flat layouts and nested CMAPSSData/ subfolder structures.

    Args:
        dataset_path: Root directory of the downloaded dataset.
        target_dir: Destination directory for the copied files.

    Returns:
        List of paths to the copied files.

    Raises:
        FileNotFoundError: If any required file is missing from the download.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    for filename in TARGET_FILES:
        source = dataset_path / filename
        if not source.exists():
            source = dataset_path / "CMAPSSData" / filename

        if not source.exists():
            matches = list(dataset_path.rglob(filename))
            if matches:
                source = matches[0]
            else:
                raise FileNotFoundError(
                    f"Could not find {filename} in {dataset_path} "
                    f"(searched root, CMAPSSData/, and recursive glob)"
                )

        dest = target_dir / filename
        shutil.copy2(source, dest)
        logger.info(f"Copied {source.name} → {dest} ({dest.stat().st_size:,} bytes)")
        copied.append(dest)

    return copied


def main() -> None:
    """Download NASA C-MAPSS FD001 and stage files in data/raw/."""
    configure_logging()
    validate_kaggle_token()
    dataset_path = download_dataset()
    copied_files = find_and_copy_files(dataset_path, RAW_DIR)
    logger.success(f"All {len(copied_files)} FD001 files staged in {RAW_DIR}")


if __name__ == "__main__":
    main()
