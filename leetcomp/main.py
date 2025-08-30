try:
    from .parse import parse_posts
    from .refresh import refresh_posts
    from .utils import config, truncate_raw_posts
except ImportError:
    from parse import parse_posts
    from refresh import refresh_posts
    from utils import config, truncate_raw_posts


def main():
    data_dir = config["app"]["data_dir"]
    raw_file = data_dir / "raw_comps.jsonl"
    parsed_file = data_dir / "parsed_comps.jsonl"

    print("Step 1: Refreshing posts from LeetCode...")
    refresh_posts(str(raw_file), max_posts=config["app"]["max_fetch_recs"])

    print("\nStep 2: Parsing compensation data...")
    parse_posts(str(raw_file), str(parsed_file))

    print("\nStep 3: Cleaning up raw posts file...")
    truncate_raw_posts(str(raw_file), keep_count=100)

    print("\nPipeline complete!")


if __name__ == "__main__":
    main()
