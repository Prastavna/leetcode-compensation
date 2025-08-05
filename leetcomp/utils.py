import json
import random
import time
import tomllib
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv

load_dotenv(override=True)

# Load configuration
with open("config.toml", "rb") as f:
    config = tomllib.load(f)

config["app"]["data_dir"] = Path(config["app"]["data_dir"])


def retry_with_exp_backoff(retries: int):  # type: ignore[no-untyped-def]
    def decorator(function: Callable):  # type: ignore
        @wraps(function)
        def wrapper(*args, **kwargs):  # type: ignore
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


def latest_parsed_date(comps_path: str) -> Optional[datetime]:
    """Get the latest parsed date from the compensation file"""
    try:
        if not Path(comps_path).exists():
            print(f"File {comps_path} does not exist")
            return None

        with open(comps_path, "r") as f:
            lines = f.readlines()

        if not lines:
            print(f"File {comps_path} is empty")
            return None

        # Try to find the first valid JSON line
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
                if "creation_date" in record:
                    return datetime.strptime(
                        record["creation_date"], config["app"]["date_fmt"]
                    )
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON on line {i+1}: {e}")
                continue

        print("No valid records with creation_date found")
        return None

    except Exception as e:
        print(f"Error reading {comps_path}: {e}")
        return None


def sort_and_truncate(comps_path: str, truncate: bool = False) -> None:
    """Sort records by date and optionally truncate to max_recs"""
    if not Path(comps_path).exists():
        print(f"File {comps_path} does not exist, nothing to sort")
        return

    valid_records = []
    invalid_lines = 0

    try:
        with open(comps_path, "r") as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                    # Validate that the record has required fields
                    if "creation_date" in record:
                        valid_records.append(record)
                    else:
                        print(
                            f"Warning: Line {line_num} missing creation_date field"
                        )
                        invalid_lines += 1
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON on line {line_num}: {e}")
                    print(
                        f"Line content: {line[:100]}..."
                    )  # Show first 100 chars
                    invalid_lines += 1
                    continue

        if not valid_records:
            print("No valid records found to sort")
            return

        # Sort by creation date (newest first)
        valid_records.sort(
            key=lambda x: datetime.strptime(
                x["creation_date"], config["app"]["date_fmt"]
            ),
            reverse=True,
        )

        if truncate:
            original_count = len(valid_records)
            valid_records = valid_records[: config["app"]["max_recs"]]
            if original_count > len(valid_records):
                print(
                    f"Truncated from {original_count} to {len(valid_records)} records"
                )

        # Write back to file
        with open(comps_path, "w") as file:
            for record in valid_records:
                file.write(json.dumps(record) + "\n")

        print(f"Sorted {len(valid_records)} valid records!")
        if invalid_lines > 0:
            print(f"Skipped {invalid_lines} invalid lines")

    except Exception as e:
        print(f"Error in sort_and_truncate: {e}")
        raise


def clean_data_file(comps_path: str) -> None:
    """Clean the data file by removing invalid JSON lines"""
    if not Path(comps_path).exists():
        print(f"File {comps_path} does not exist")
        return

    valid_records = []
    invalid_lines = 0

    with open(comps_path, "r") as file:
        for line_num, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
                valid_records.append(record)
            except json.JSONDecodeError as e:
                print(f"Removing invalid JSON on line {line_num}: {e}")
                print(f"Line content: {line[:100]}...")
                invalid_lines += 1
                continue

    # Write back only valid records
    with open(comps_path, "w") as file:
        for record in valid_records:
            file.write(json.dumps(record) + "\n")

    print(
        f"Cleaned file: kept {len(valid_records)} valid records, removed {invalid_lines} invalid lines"
    )


def mapping(map_path: str | Path) -> dict[str, str]:
    """Load mapping dictionary from JSON file"""
    try:
        with open(map_path, "r") as f:
            data = json.load(f)

        mapping_dict = {}
        for d in data:
            if "cluster" in d and "cluster_name" in d:
                for item in d["cluster"]:
                    mapping_dict[item] = d["cluster_name"]
            else:
                print(f"Warning: Invalid mapping entry: {d}")

        return mapping_dict

    except Exception as e:
        print(f"Error loading mapping from {map_path}: {e}")
        return {}
