import json
import os
import re
from datetime import datetime
from typing import Any, Generator, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from leetcomp.utils import (
    config,
    latest_parsed_date,
    mapping,
    sort_and_truncate,
)

client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.getenv("GITHUB_TOKEN"),
)

interview_exp_pattern = re.compile(
    r"https://leetcode.com/discuss/interview-experience/\S+"
)

yoe_map: dict[tuple[int, int], str] = {
    (0, 1): "Entry (0-1)",
    (2, 6): "Mid (2-6)",
    (7, 10): "Senior (7-10)",
    (11, 30): "Senior + (11+)",
}


class CompensationOffer(BaseModel):
    """Single compensation offer from a LeetCode post"""

    company: str = Field(description="Company name")
    role: str = Field(description="Job role/title")
    yoe: float = Field(description="Years of experience", ge=0, le=50)
    base_offer: float = Field(
        description="Base salary offer",
        ge=config["parsing"]["min_base_offer"],
        le=config["parsing"]["max_base_offer"],
    )
    total_offer: float = Field(
        description="Total compensation offer",
        ge=config["parsing"]["min_total_offer"],
        le=config["parsing"]["max_total_offer"],
    )
    location: Optional[str] = Field(default="n/a", description="Job location")
    non_indian: Optional[str] = Field(
        default=None, description="Non-Indian candidate flag"
    )

    @field_validator("non_indian")
    @classmethod
    def validate_non_indian(cls, v: Optional[str]) -> Optional[str]:
        if v == "yes":
            raise ValueError("non_indian cannot be 'yes'")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if "intern" in v.lower():
            raise ValueError("intern roles are not supported")
        return v


class CompensationOffers(BaseModel):
    """Multiple compensation offers from a single LeetCode post"""

    offers: List[CompensationOffer] = Field(
        description="List of compensation offers"
    )

    @field_validator("offers")
    @classmethod
    def validate_offers(
        cls, v: List[CompensationOffer]
    ) -> List[CompensationOffer]:
        if not v:
            raise ValueError("At least one offer must be provided")
        return v


def post_should_be_parsed(post: dict[Any, Any]) -> bool:
    """Check if a post should be parsed based on basic criteria"""
    if "title" not in post:
        print(f" x skipping {post['id']}; no title")
        return False
    if "|" not in post["title"]:
        print(f" x skipping {post['id']}; | not in title")
        return False
    if "vote_count" not in post:
        print(f" x skipping {post['id']}; no vote_count")
        return False
    if post["vote_count"] < 0:
        print(f" x skipping {post['id']}; negative vote_count")
        return False
    return True


def has_crossed_till_date(
    creation_date: str, till_date: Optional[datetime] = None
) -> bool:
    """Check if post creation date has crossed the till_date threshold"""
    if till_date is None:
        return False

    dt = datetime.strptime(creation_date, config["app"]["date_fmt"])
    return dt <= till_date


def comps_posts_iter(comps_path: str) -> Generator[dict[Any, Any], None, None]:
    """Iterator over compensation posts from JSONL file"""
    with open(comps_path, "r") as f:
        for line in f:
            yield json.loads(line)


def parse_compensation_with_openai(
    post_content: str,
) -> Optional[CompensationOffers]:
    """Parse compensation data using OpenAI structured output"""
    try:
        response = client.chat.completions.parse(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that extracts compensation information from LeetCode posts. Extract all compensation offers mentioned in the post.",
                },
                {
                    "role": "user",
                    "content": post_content,
                },
            ],
            model="openai/gpt-4o-mini",
            temperature=0.1,  # Low temperature for consistency
            max_tokens=4096 * 2,
            top_p=1,
            response_format=CompensationOffers,
        )

        return response.choices[0].message.parsed
    except Exception as e:
        print(f" x OpenAI parsing error: {str(e)}")
        return None


def extract_interview_exp(content: str) -> str:
    """Extract interview experience URL from post content"""
    match = interview_exp_pattern.search(content)
    return match.group(0) if match else "N/A"


def get_parsed_posts(
    raw_post: dict[Any, Any], compensation_offers: CompensationOffers
) -> list[dict[Any, Any]]:
    """Convert structured compensation offers to parsed post format"""
    parsed_posts = []

    for offer in compensation_offers.offers:
        parsed_post = {
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
            "interview_exp": extract_interview_exp(raw_post["content"]),
        }
        parsed_posts.append(parsed_post)

    return parsed_posts


def fill_yoe(parsed_posts: list[dict[Any, Any]]) -> None:
    """Fill YOE for subsequent offers if multiple offers exist"""
    if len(parsed_posts) > 1:
        first_yoe = parsed_posts[0]["yoe"]
        for post in parsed_posts[1:]:
            post["yoe"] = first_yoe


def parse_posts(
    in_comps_path: str,
    out_comps_path: str,
    parsed_ids: Optional[set[int]] = None,
    till_date: Optional[datetime] = None,
) -> None:
    """Main function to parse compensation posts using OpenAI structured output"""
    n_skips = 0
    n_parsed = 0
    parsed_ids = parsed_ids or set()

    for i, post in enumerate(comps_posts_iter(in_comps_path), start=1):
        if i % 20 == 0:
            print(f"Processed {i} posts; {n_parsed} parsed; {n_skips} skips")

        if post["id"] in parsed_ids or not post_should_be_parsed(post):
            n_skips += 1
            continue

        if has_crossed_till_date(post["creation_date"], till_date):
            break

        # Prepare input for OpenAI
        input_text = f"{post['title']}\n---\n{post['content']}"

        # Parse using OpenAI structured output
        compensation_offers = parse_compensation_with_openai(input_text)

        if compensation_offers and compensation_offers.offers:
            # Convert to the expected format
            parsed_posts = get_parsed_posts(post, compensation_offers)
            fill_yoe(parsed_posts)

            # Write to output file
            with open(out_comps_path, "a") as f:
                for parsed_post in parsed_posts:
                    f.write(json.dumps(parsed_post) + "\n")

            n_parsed += 1
            print(f" ✓ parsed {post['id']} -> {len(parsed_posts)} offers")
        else:
            n_skips += 1
            print(f" x failed to parse {post['id']}")

    print(f"Parsing complete: {n_parsed} posts parsed, {n_skips} skipped")


def get_parsed_ids(out_comps_path: str) -> set[int]:
    """Get set of already parsed post IDs"""
    if not os.path.exists(out_comps_path):
        return set()

    with open(out_comps_path, "r") as f:
        return {json.loads(line)["id"] for line in f}


def cleanup_record(record: dict[Any, Any]) -> None:
    """Clean up and format record for final output"""
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
    default: Optional[str] = None,
    extras: Optional[list[str]] = None,
) -> str:
    """Map item to standardized value using mapping dictionary"""
    item = item.lower()
    if extras:
        for role_str in extras:
            if role_str in item:
                return role_str.capitalize()

    return mapping.get(item, default or item.capitalize())


def map_location(location: str, location_map: dict[str, str]) -> str:
    """Map location to standardized value"""
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
    """Map years of experience to category"""
    for (start, end), mapped_yoe in yoe_map.items():
        if start <= yoe <= end:
            return mapped_yoe

    return "Senior +"


def jsonl_to_json(jsonl_path: str, json_path: str) -> None:
    """Convert JSONL to JSON with mappings applied"""
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse LeetCode Compensations posts using OpenAI structured output."
    )
    parser.add_argument(
        "--in_comps_path",
        type=str,
        default=config["app"]["data_dir"] / "raw_comps.jsonl",
        help="Path to the file to store posts.",
    )
    parser.add_argument(
        "--out_comps_path",
        type=str,
        default=config["app"]["data_dir"] / "parsed_comps.jsonl",
        help="Path to the file to store parsed posts.",
    )
    parser.add_argument(
        "--json_path",
        type=str,
        default=config["app"]["data_dir"] / "parsed_comps.json",
        help="Path to the file to store parsed posts in JSON format.",
    )
    args = parser.parse_args()

    print(
        f"Parsing comps from {args.in_comps_path} using OpenAI structured output..."
    )

    parsed_ids = (
        get_parsed_ids(args.out_comps_path)
        if os.path.exists(args.out_comps_path)
        else set()
    )
    print(f"Found {len(parsed_ids)} parsed ids...")

    till_date = (
        latest_parsed_date(args.out_comps_path)
        if os.path.exists(args.out_comps_path)
        else None
    )

    parse_posts(args.in_comps_path, args.out_comps_path, parsed_ids, till_date)
    sort_and_truncate(args.out_comps_path, truncate=True)
    jsonl_to_json(args.out_comps_path, args.json_path)
