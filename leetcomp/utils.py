import json
import random
import time
import tomllib
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Callable, Optional, Any

from dotenv import load_dotenv

load_dotenv(override=True)

with open("../config.toml", "rb") as f:
    config = tomllib.load(f)

config["app"]["data_dir"] = Path(config["app"]["data_dir"])

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

def latest_parsed_date(file_path: str) -> Optional[datetime]:
    if not Path(file_path).exists():
        return None
    
    with open(file_path, "r") as f:
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
                return datetime.strptime(record["creation_date"], config["app"]["date_fmt"])
        except json.JSONDecodeError:
            continue
    
    return None

def sort_and_truncate(file_path: str):
    if not Path(file_path).exists():
        return
    
    records = []
    with open(file_path, "r") as f:
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
        reverse=True
    )
    
    max_records = config["app"].get("max_recs", 1000)
    if len(records) > max_records:
        records = records[:max_records]
        print(f"Truncated to {max_records} records")
    
    with open(file_path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    
    print(f"Sorted {len(records)} records")