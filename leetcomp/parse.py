import json

try:
    from .utils import (
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
        config,
        create_parsed_record,
        get_existing_ids,
        has_crossed_till_date,
        jsonl_to_json,
        latest_parsed_date,
        parse_compensation_with_openai,
        sort_and_truncate,
    )


def parse_posts(input_file: str, output_file: str):
    """Parse posts from input file and save parsed data to output file."""
    existing_parsed_ids = get_existing_ids(output_file)
    till_date = latest_parsed_date(output_file)

    parsed_count = 0
    failed_count = 0

    with open(input_file) as infile, open(output_file, "a") as outfile:
        for line in infile:
            if not line.strip():
                continue

            try:
                raw_post = json.loads(line)
            except json.JSONDecodeError:
                continue

            post_id = raw_post["id"]

            if post_id in existing_parsed_ids:
                continue

            if has_crossed_till_date(raw_post["creation_date"], till_date):
                break

            input_text = f"{raw_post['title']}\n---\n{raw_post['content']}"
            compensation_offers = parse_compensation_with_openai(input_text)

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
                        f"Parsed post {post_id}: {len(valid_offers)} offers (filtered from {len(compensation_offers.offers)})"
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


if __name__ == "__main__":
    input_file = config["app"]["data_dir"] / "raw_comps.jsonl"
    output_file = config["app"]["data_dir"] / "parsed_comps.jsonl"
    parse_posts(str(input_file), str(output_file))
