import json
from datetime import datetime

try:
    from .utils import (
        RETRYABLE_LLM_ERRORS,
        config,
        create_parsed_record,
        get_existing_ids,
        has_crossed_till_date,
        jsonl_to_json,
        latest_parsed_date,
        parse_compensation_with_openai,
        sort_and_truncate,
    )
except ImportError:
    from utils import (
        RETRYABLE_LLM_ERRORS,
        config,
        create_parsed_record,
        get_existing_ids,
        has_crossed_till_date,
        jsonl_to_json,
        latest_parsed_date,
        parse_compensation_with_openai,
        sort_and_truncate,
    )


class NoProgressError(RuntimeError):
    """Raised when a retryable LLM failure blocked every pending post."""


def load_pending_posts(input_file: str, output_file: str) -> list[dict]:
    """Raw posts not parsed yet, oldest first."""
    existing_parsed_ids = get_existing_ids(output_file)
    till_date = latest_parsed_date(output_file)

    pending = []
    with open(input_file) as infile:
        for line in infile:
            if not line.strip():
                continue

            try:
                raw_post = json.loads(line)
            except json.JSONDecodeError:
                continue

            if raw_post["id"] in existing_parsed_ids:
                continue

            if has_crossed_till_date(raw_post["creation_date"], till_date):
                continue

            pending.append(raw_post)

    pending.sort(key=lambda post: datetime.strptime(post["creation_date"], config["app"]["date_fmt"]))
    return pending


def parse_posts(input_file: str, output_file: str):
    """Parse posts from input file and save parsed data to output file."""
    # The next run resumes after the newest parsed date, so posts are parsed oldest-first and
    # the run stops at the first retryable failure; that post and everything after it is retried.
    pending = load_pending_posts(input_file, output_file)
    print(f"Found {len(pending)} posts to parse")

    parsed_count = 0
    failed_count = 0
    retry_from_date = None

    with open(output_file, "a") as outfile:
        for raw_post in pending:
            post_id = raw_post["id"]

            input_text = f"{raw_post['title']}\n---\n{raw_post['content']}"
            try:
                compensation_offers = parse_compensation_with_openai(input_text)
            except RETRYABLE_LLM_ERRORS as e:
                retry_from_date = raw_post["creation_date"]
                print(f"Retryable LLM error on post {post_id}: {e}")
                break

            if compensation_offers and compensation_offers.offers:
                # Track companies to prevent duplicates within the same post
                seen_companies = set()
                valid_offers = []

                for offer in compensation_offers.offers:
                    company = offer.company.lower() if hasattr(offer, 'company') and offer.company else None
                    if company and company not in seen_companies:
                        seen_companies.add(company)
                        valid_offers.append(offer)

                if valid_offers:
                    for offer in valid_offers:
                        parsed_record = create_parsed_record(raw_post, offer)
                        outfile.write(json.dumps(parsed_record) + "\n")
                        outfile.flush()

                    parsed_count += 1
                    print(
                        f"Parsed post {post_id}: {len(valid_offers)} offers (from {len(compensation_offers.offers)})"
                    )
                else:
                    failed_count += 1
                    print(f"No valid offers after deduplication for post {post_id}")
            else:
                failed_count += 1
                print(f"Failed to parse post {post_id}")

    print(f"Parsing complete: {parsed_count} posts parsed, {failed_count} failed")
    sort_and_truncate(output_file)
    jsonl_to_json(
        str(output_file), str(config["app"]["data_dir"] / "parsed_comps.json")
    )

    if retry_from_date is not None:
        print(f"Stopped at a retryable failure; posts from {retry_from_date} onwards will be retried next run.")
        if parsed_count == 0 and failed_count == 0:
            raise NoProgressError("No progress: a retryable LLM failure blocked every post.")


if __name__ == "__main__":
    input_file = config["app"]["data_dir"] / "raw_comps.jsonl"
    output_file = config["app"]["data_dir"] / "parsed_comps.jsonl"
    parse_posts(str(input_file), str(output_file))
