import json
from dataclasses import asdict
from datetime import datetime

try:
    from .utils import (
        config, sort_and_truncate, latest_parsed_date,
        LeetCodeFetcher, get_existing_ids, has_crossed_till_date, is_within_lag_period
    )
except ImportError:
    from utils import (
        config, sort_and_truncate, latest_parsed_date,
        LeetCodeFetcher, get_existing_ids, has_crossed_till_date, is_within_lag_period
    )


def refresh_posts(output_file: str, max_posts: int = 100):
    """Refresh posts from LeetCode and save to file."""
    fetcher = LeetCodeFetcher()
    existing_ids = get_existing_ids(output_file)
    till_date = latest_parsed_date(output_file)
    
    skip = 0
    first = 50
    new_posts_count = 0
    skipped_due_to_lag = 0
    should_stop = False
    
    with open(output_file, "a") as f:
        while new_posts_count < max_posts and not should_stop:
            posts_list = fetcher.fetch_posts_list(skip, first)
            
            if not posts_list:
                break
                
            for post_edge in posts_list:
                node = post_edge["node"]
                topic_id = node["topicId"]
                
                if topic_id in existing_ids:
                    continue
                
                # Parse creation date from the posts list (no need to fetch details)
                creation_date_iso = node["createdAt"]
                creation_date = datetime.fromisoformat(creation_date_iso.replace('Z', '+00:00'))
                formatted_date = creation_date.strftime(config["app"]["date_fmt"])
                
                # Check date conditions early before fetching post details
                if has_crossed_till_date(formatted_date, till_date):
                    print(f"Reached posts older than {till_date}, stopping...")
                    should_stop = True
                    break
                
                if is_within_lag_period(formatted_date):
                    skipped_due_to_lag += 1
                    continue
                
                try:
                    # Only fetch details if we passed the date filters
                    post_details = fetcher.fetch_post_details(topic_id)
                    post = fetcher.parse_post_data(post_details)
                    
                    if fetcher.should_parse_post(post):
                        f.write(json.dumps(asdict(post)) + "\n")
                        f.flush()
                        new_posts_count += 1
                        print(f"Fetched post {topic_id} from {post.creation_date}: {post.title[:50]}...")
                        
                        if new_posts_count >= max_posts:
                            should_stop = True
                            break
                
                except Exception as e:
                    print(f"Error fetching post {topic_id}: {e}")
                    continue
            
            skip += first
            
            if len(posts_list) < first:
                break
    
    print(f"Fetched {new_posts_count} new posts")
    if skipped_due_to_lag > 0:
        print(f"Skipped {skipped_due_to_lag} posts due to lag period")
    sort_and_truncate(output_file)


if __name__ == "__main__":
    output_file = config["app"]["data_dir"] / "raw_comps.jsonl"
    refresh_posts(str(output_file))