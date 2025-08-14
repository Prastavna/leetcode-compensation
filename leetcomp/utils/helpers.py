import json
import random
import time
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from pathlib import Path

from .config import config


def retry_with_exp_backoff(retries: int):
    def decorator(function: Callable):
        @wraps(function)
        def wrapper(*args, **kwargs):
            i = 1
            while i <= retries:
                try:
                    return function(*args, **kwargs)
                except Exception as e:
                    sleep_for = random.uniform(2**i, 2 ** (i + 1))
                    err_msg = f"{function.__name__} ({args}, {kwargs}): {e}"
                    print(f"Retry={i} Rest={sleep_for:.1f}s Err={err_msg}")
                    time.sleep(sleep_for)
                    i += 1
                    if i > retries:
                        raise

        return wrapper

    return decorator


def latest_parsed_date(file_path: str) -> datetime | None:
    if not Path(file_path).exists():
        return None

    with open(file_path) as f:
        lines = f.readlines()

    if not lines:
        return None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if "creation_date" in record:
                return datetime.strptime(
                    record["creation_date"], config["app"]["date_fmt"]
                )
        except json.JSONDecodeError:
            continue

    return None


def sort_and_truncate(file_path: str):
    if not Path(file_path).exists():
        return

    records = []
    with open(file_path) as f:
        for line in f:
            if line.strip():
                try:
                    record = json.loads(line)
                    if "creation_date" in record:
                        records.append(record)
                except json.JSONDecodeError:
                    continue

    if not records:
        return

    records.sort(
        key=lambda x: datetime.strptime(x["creation_date"], config["app"]["date_fmt"]),
        reverse=True,
    )

    max_records = config["app"].get("max_recs", 1000)
    if len(records) > max_records:
        records = records[:max_records]
        print(f"Truncated to {max_records} records")

    with open(file_path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print(f"Sorted {len(records)} records")


def truncate_raw_posts(file_path: str, keep_count: int = 100):
    """Keep only the latest N records in the raw posts file to prevent growth."""
    if not Path(file_path).exists():
        print(f"File {file_path} does not exist")
        return

    records = []
    with open(file_path) as f:
        for line in f:
            if line.strip():
                try:
                    record = json.loads(line)
                    if "creation_date" in record:
                        records.append(record)
                except json.JSONDecodeError:
                    continue

    if not records:
        print(f"No valid records found in {file_path}")
        return

    # Sort by creation date (newest first)
    records.sort(
        key=lambda x: datetime.strptime(x["creation_date"], config["app"]["date_fmt"]),
        reverse=True,
    )

    original_count = len(records)

    # Keep only the latest records
    if len(records) > keep_count:
        records = records[:keep_count]
        removed_count = original_count - len(records)

        # Write back to file
        with open(file_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        msg = (
            f"Truncated raw posts: kept {len(records)} latest records, "
            f"removed {removed_count} older records"
        )
        print(msg)
    else:
        msg = (
            f"Raw posts file has {len(records)} records (≤ {keep_count}), "
            "no truncation needed"
        )
        print(msg)
