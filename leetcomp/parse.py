import json
import os
from datetime import datetime
from typing import List, Optional, Any
import re
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from utils import config, sort_and_truncate, latest_parsed_date

client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.getenv("GITHUB_TOKEN"),
)

yoe_map: dict[tuple[int, int], str] = {
    (0, 1): "Entry (0-1)",
    (2, 6): "Mid (2-6)",
    (7, 10): "Senior (7-10)",
    (11, 30): "Senior + (11+)",
}

def cleanup_record(record: dict[Any, Any]) -> None:
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
    mapping: dict[str, str],
    default: str | None = None,
    extras: list[str] | None = None,
) -> str:
    item = item.lower()
    if extras:
        for role_str in extras:
            if role_str in item:
                return role_str.capitalize()

    return mapping.get(item, default or item.capitalize())

def map_location(location: str, location_map: dict[str, str]) -> str:
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

def map_yoe(yoe: int, yoe_map: dict[tuple[int, int], str]) -> str:
    for (start, end), mapped_yoe in yoe_map.items():
        if start <= yoe <= end:
            return mapped_yoe

    return "Senior +"

def mapping(map_path: str | Path) -> dict[str, str]:
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
    company_map = mapping(config["app"]["data_dir"] / "company_map.json")
    role_map = mapping(config["app"]["data_dir"] / "role_map.json")
    location_map = mapping(config["app"]["data_dir"] / "location_map.json")
    records = []

    with open(jsonl_path, "r") as file:
        for line in file:
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

    with open(json_path, "w") as file:
        json.dump(records, file, indent=4)

    print(f"Converted {len(records)} records!")

class CompensationOffer(BaseModel):
    company: str = Field(description="Company name")
    role: str = Field(description="Job role/title")
    yoe: float = Field(description="Years of experience", ge=0, le=50)
    base_offer: float = Field(description="Base salary offer")
    total_offer: float = Field(description="Total compensation offer")
    location: Optional[str] = Field(default="n/a", description="Job location")
    interview_exp: Optional[str] = Field(default="n/a", description="Interview experience")

    @field_validator("company")
    @classmethod
    def validate_company(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("empty company name is not supported")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if "intern" in v.lower():
            raise ValueError("intern roles are not supported")
        if not v.strip():
            raise ValueError("empty roles are not supported")
        return v

    @field_validator("base_offer")
    @classmethod
    def validate_base_offer(cls, v: float) -> float:
        min_base = config["parsing"]["min_base_offer"]
        max_base = config["parsing"]["max_base_offer"]

        # If value is too large, it might be in absolute terms (lakhs)
        # Try dividing by 100,000 to convert to lakhs
        if v > max_base:
            converted_v = v / 100000
            if min_base <= converted_v <= max_base:
                return converted_v

        if min_base <= v <= max_base:
            return v

        raise ValueError(
            f"base_offer {v} is out of range [{min_base}, {max_base}] even after conversion"
        )

    @field_validator("total_offer")
    @classmethod
    def validate_total_offer(cls, v: float) -> float:
        min_total = config["parsing"]["min_total_offer"]
        max_total = config["parsing"]["max_total_offer"]

        # If value is too large, it might be in absolute terms (lakhs)
        # Try dividing by 100,000 to convert to lakhs
        if v > max_total:
            converted_v = v / 100000
            if min_total <= converted_v <= max_total:
                return converted_v

        if min_total <= v <= max_total:
            return v

        raise ValueError(
            f"total_offer {v} is out of range [{min_total}, {max_total}] even after conversion"
        )

    @field_validator("interview_exp")
    @classmethod
    def validate_interview_exp(cls, v: str) -> str:
        if not v.strip():
            return "n/a"
        return v

class CompensationOffers(BaseModel):
    offers: List[CompensationOffer] = Field(description="List of compensation offers")

    @field_validator("offers")
    @classmethod
    def validate_offers(cls, v: List[CompensationOffer]) -> List[CompensationOffer]:
        if not v:
            raise ValueError("At least one offer must be provided")
        return v

def parse_compensation_with_openai(post_content: str) -> Optional[CompensationOffers]:
    try:
        response = client.chat.completions.parse(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that extracts compensation information from LeetCode posts. Extract all compensation offers mentioned in the post. If some role or company is not mentioned, return empty string for that field. Interview experience is a link to leetcode post. If no interview experience is mentioned, return empty string for that field.",
                },
                {
                    "role": "user",
                    "content": post_content,
                },
            ],
            model="openai/gpt-4o-mini",
            temperature=0.1,
            max_tokens=4096 * 2,
            top_p=1,
            response_format=CompensationOffers,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"OpenAI parsing error: {str(e)}")
        return None

def get_existing_parsed_ids(filepath: str) -> set:
    if not os.path.exists(filepath):
        return set()
    
    existing_ids = set()
    with open(filepath, "r") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                existing_ids.add(data["id"])
    return existing_ids

def create_parsed_record(raw_post: dict, offer: CompensationOffer) -> dict:
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

def has_crossed_till_date(creation_date: str, till_date) -> bool:
    if till_date is None:
        return False
    dt = datetime.strptime(creation_date, config["app"]["date_fmt"])
    return dt <= till_date

def parse_posts(input_file: str, output_file: str):
    existing_parsed_ids = get_existing_parsed_ids(output_file)
    till_date = latest_parsed_date(output_file)
    
    parsed_count = 0
    failed_count = 0
    
    with open(input_file, "r") as infile, open(output_file, "a") as outfile:
        for line in infile:
            if not line.strip():
                continue
                
            raw_post = json.loads(line)
            post_id = raw_post["id"]
            
            if post_id in existing_parsed_ids:
                continue
                
            if has_crossed_till_date(raw_post["creation_date"], till_date):
                break
            
            input_text = f"{raw_post['title']}\n---\n{raw_post['content']}"
            compensation_offers = parse_compensation_with_openai(input_text)
            
            if compensation_offers and compensation_offers.offers:
                for offer in compensation_offers.offers:
                    parsed_record = create_parsed_record(raw_post, offer)
                    outfile.write(json.dumps(parsed_record) + "\n")
                    outfile.flush()
                
                parsed_count += 1
                print(f"Parsed post {post_id}: {len(compensation_offers.offers)} offers")
            else:
                failed_count += 1
                print(f"Failed to parse post {post_id}")
    
    print(f"Parsing complete: {parsed_count} posts parsed, {failed_count} failed")
    sort_and_truncate(output_file)
    jsonl_to_json(str(output_file), str(config["app"]["data_dir"] / "parsed_comps.json"))

if __name__ == "__main__":
    input_file = config["app"]["data_dir"] / "raw_comps.jsonl"
    output_file = config["app"]["data_dir"] / "parsed_comps.jsonl"
    parse_posts(str(input_file), str(output_file))