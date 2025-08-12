import json
import sys
from pathlib import Path
from typing import Set

try:
    from .utils import config
except ImportError:
    from utils import config


def remove_posts_from_jsonl(file_path: str, post_ids: Set[str]) -> int:
    """Remove posts with given IDs from JSONL file and return count of removed posts."""
    if not Path(file_path).exists():
        print(f"File {file_path} does not exist")
        return 0
    
    removed_count = 0
    temp_file = file_path + ".tmp"
    
    with open(file_path, "r") as infile, open(temp_file, "w") as outfile:
        for line in infile:
            if not line.strip():
                continue
            
            try:
                record = json.loads(line)
                if record.get("id") not in post_ids:
                    outfile.write(line)
                else:
                    removed_count += 1
                    print(f"Removed post ID: {record.get('id')}")
            except json.JSONDecodeError:
                # Keep malformed lines as-is
                outfile.write(line)
    
    # Replace original file with cleaned version
    Path(temp_file).rename(file_path)
    return removed_count


def remove_posts_from_json(file_path: str, post_ids: Set[str]) -> int:
    """Remove posts with given IDs from JSON file and return count of removed posts."""
    if not Path(file_path).exists():
        print(f"File {file_path} does not exist")
        return 0
    
    with open(file_path, "r") as f:
        records = json.load(f)
    
    original_count = len(records)
    filtered_records = [record for record in records if record.get("id") not in post_ids]
    removed_count = original_count - len(filtered_records)
    
    with open(file_path, "w") as f:
        json.dump(filtered_records, f, indent=4)
    
    for post_id in post_ids:
        if any(record.get("id") == post_id for record in records):
            print(f"Removed post ID: {post_id}")
    
    return removed_count


def clean_posts(post_ids_str: str):
    """Clean posts from both parsed_comps.jsonl and parsed_comps.json files."""
    if not post_ids_str.strip():
        print("No post IDs provided")
        return
    
    # Parse comma-separated post IDs
    post_ids = {post_id.strip() for post_id in post_ids_str.split(",") if post_id.strip()}
    
    if not post_ids:
        print("No valid post IDs found")
        return
    
    print(f"Cleaning {len(post_ids)} post IDs: {', '.join(post_ids)}")
    
    data_dir = config["app"]["data_dir"]
    jsonl_file = str(data_dir / "parsed_comps.jsonl")
    json_file = str(data_dir / "parsed_comps.json")
    
    # Remove from JSONL file
    jsonl_removed = remove_posts_from_jsonl(jsonl_file, post_ids)
    print(f"Removed {jsonl_removed} records from {jsonl_file}")
    
    # Remove from JSON file
    json_removed = remove_posts_from_json(json_file, post_ids)
    print(f"Removed {json_removed} records from {json_file}")
    
    print("Cleanup complete!")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python clean.py <comma_separated_post_ids>")
        print("Example: python clean.py 12345,67890,11111")
        sys.exit(1)
    
    post_ids_str = sys.argv[1]
    clean_posts(post_ids_str)