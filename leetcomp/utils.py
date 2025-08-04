import json
import random
import time
import tomllib
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Callable

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


def latest_parsed_date(comps_path: str) -> datetime:
    """Get the latest parsed date from the compensation file"""
    with open(comps_path, "r") as f:
        top_line = json.loads(f.readline())

    return datetime.strptime(
        top_line["creation_date"], config["app"]["date_fmt"]
    )


def sort_and_truncate(comps_path: str, truncate: bool = False) -> None:
    """Sort records by date and optionally truncate to max_recs"""
    with open(comps_path, "r") as file:
        records = [json.loads(line) for line in file]

    records.sort(
        key=lambda x: datetime.strptime(
            x["creation_date"], config["app"]["date_fmt"]
        ),
        reverse=True,
    )

    if truncate:
        records = records[: config["app"]["max_recs"]]

    with open(comps_path, "w") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")

    print(f"Sorted {len(records)} records!")


def mapping(map_path: str | Path) -> dict[str, str]:
    """Load mapping dictionary from JSON file"""
    with open(map_path, "r") as f:
        data = json.load(f)

    mapping = {}
    for d in data:
        for item in d["cluster"]:
            mapping[item] = d["cluster_name"]

    return mapping
