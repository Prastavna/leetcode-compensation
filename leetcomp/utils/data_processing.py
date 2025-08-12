import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .config import config


def get_existing_ids(filepath: str) -> Set[str]:
    """Get set of existing IDs from a JSONL file."""
    if not os.path.exists(filepath):
        return set()
    
    existing_ids = set()
    with open(filepath, "r") as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    existing_ids.add(data["id"])
                except json.JSONDecodeError:
                    continue
    return existing_ids


def has_crossed_till_date(creation_date: str, till_date: Optional[datetime]) -> bool:
    """Check if creation date is before or equal to till_date."""
    if till_date is None:
        return False
    dt = datetime.strptime(creation_date, config["app"]["date_fmt"])
    return dt <= till_date


def cleanup_record(record: Dict[Any, Any]) -> None:
    """Clean up a record by removing unnecessary fields and formatting data."""
    record.pop("vote_count", None)
    record.pop("comment_count", None)
    record.pop("view_count", None)

    record["creation_date"] = record["creation_date"][:10]
    record["yoe"] = round(record["yoe"])
    record["base"] = round(float(record["base_offer"]), 2)
    record["total"] = round(float(record["total_offer"]), 2)

    record.pop("base_offer", None)
    record.pop("total_offer", None)


def mapped_record(
    item: str,
    mapping: Dict[str, str],
    default: Optional[str] = None,
    extras: Optional[List[str]] = None,
) -> str:
    """Map an item using a mapping dictionary with optional extras."""
    item = item.lower()
    if extras:
        for role_str in extras:
            if role_str in item:
                return role_str.capitalize()

    return mapping.get(item, default or item.capitalize())


def map_location(location: str, location_map: Dict[str, str]) -> str:
    """Map location string using location mapping."""
    location = location.lower()

    if location == "n/a":
        return location_map[location]

    if "(" in location:
        location = location.split("(")[0].strip()

    for sep in [",", "/"]:
        if sep in location:
            locations = [loc.strip().lower() for loc in location.split(sep)]
            location = "/".join(
                [location_map.get(loc, loc.capitalize()) for loc in locations]
            )
            return location

    return location_map.get(location, location.capitalize())


def map_yoe(yoe: int, yoe_map: Dict[tuple[int, int], str]) -> str:
    """Map years of experience to a category."""
    for (start, end), mapped_yoe in yoe_map.items():
        if start <= yoe <= end:
            return mapped_yoe

    return "Senior +"


def load_mapping(map_path: str | Path) -> Dict[str, str]:
    """Load mapping dictionary from JSON file."""
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


def jsonl_to_json(jsonl_path: str, json_path: str) -> None:
    """Convert JSONL file to JSON with data processing and mapping."""
    # Load mappings
    company_map = load_mapping(config["app"]["data_dir"] / "company_map.json")
    role_map = load_mapping(config["app"]["data_dir"] / "role_map.json")
    location_map = load_mapping(config["app"]["data_dir"] / "location_map.json")
    
    # YOE mapping
    yoe_map: Dict[tuple[int, int], str] = {
        (0, 1): "Entry (0-1)",
        (2, 6): "Mid (2-6)",
        (7, 10): "Senior (7-10)",
        (11, 30): "Senior + (11+)",
    }
    
    records = []

    with open(jsonl_path, "r") as file:
        for line in file:
            if not line.strip():
                continue
            
            try:
                record = json.loads(line)
                cleanup_record(record)
                record["company"] = mapped_record(record["company"], company_map)
                role_to_map = "".join(re.findall(r"\w+", record["role"]))
                record["mapped_role"] = mapped_record(
                    role_to_map,
                    role_map,
                    default=record["role"],
                    extras=["analyst", "intern", "associate"],
                )
                record["mapped_yoe"] = map_yoe(record["yoe"], yoe_map)
                record["location"] = map_location(record["location"], location_map)
                records.append(record)
            except json.JSONDecodeError:
                continue

    with open(json_path, "w") as file:
        json.dump(records, file, indent=4)

    print(f"Converted {len(records)} records!")


def create_parsed_record(raw_post: Dict, offer: Any) -> Dict:
    """Create a parsed record from raw post and compensation offer."""
    return {
        "id": raw_post["id"],
        "vote_count": raw_post["vote_count"],
        "comment_count": raw_post["comment_count"],
        "view_count": raw_post["view_count"],
        "creation_date": raw_post["creation_date"],
        "company": offer.company,
        "role": offer.role,
        "yoe": offer.yoe,
        "base_offer": offer.base_offer,
        "total_offer": offer.total_offer,
        "location": offer.location or "n/a",
        "interview_exp": offer.interview_exp,
    }