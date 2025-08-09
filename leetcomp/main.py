from utils import config
from refresh import refresh_posts
from parse import parse_posts

def main():
    data_dir = config["app"]["data_dir"]
    raw_file = data_dir / "raw_comps.jsonl"
    parsed_file = data_dir / "parsed_comps.jsonl"
    json_file = data_dir / "parsed_comps.json"
    
    print("Step 1: Refreshing posts from LeetCode...")
    refresh_posts(str(raw_file), max_posts=10000)
    
    print("\nStep 2: Parsing compensation data...")
    parse_posts(str(raw_file), str(parsed_file))
    
    # print("\nStep 3: Converting to JSON...")
    # jsonl_to_json(str(parsed_file), str(json_file))
    
    print("\nPipeline complete!")

if __name__ == "__main__":
    main()