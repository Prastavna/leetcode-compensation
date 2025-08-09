import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

from utils import config, retry_with_exp_backoff, sort_and_truncate, latest_parsed_date

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"
LAG_DAYS = 3

@dataclass
class LeetCodePost:
    id: str
    title: str
    content: str
    vote_count: int
    comment_count: int
    view_count: int
    creation_date: str

class LeetCodeFetcher:
    def __init__(self):
        transport = RequestsHTTPTransport(url=LEETCODE_GRAPHQL_URL)
        self.client = Client(transport=transport)
        
        with open("queries/discussion_post_items.gql", "r") as f:
            self.posts_query = gql(f.read())
        
        with open("queries/post_details.gql", "r") as f:
            self.details_query = gql(f.read())

    @retry_with_exp_backoff(retries=3)
    def fetch_posts_list(self, skip: int = 0, first: int = 50) -> List[dict]:
        result = self.client.execute(self.posts_query, variable_values={
            "orderBy": "MOST_RECENT",
            "keywords": [],
            "tagSlugs": ["compensation"],
            "skip": skip,
            "first": first
        })
        return result["ugcArticleDiscussionArticles"]["edges"]

    @retry_with_exp_backoff(retries=3)
    def fetch_post_details(self, topic_id: str) -> dict:
        result = self.client.execute(self.details_query, variable_values={
            "topicId": topic_id
        })
        return result["ugcArticleDiscussionArticle"]

    def parse_post_data(self, post_data: dict) -> LeetCodePost:
        upvotes=[r for r in post_data["reactions"] if r["reactionType"] == "UPVOTE"][0]["count"] if [r for r in post_data["reactions"] if r["reactionType"] == "UPVOTE"] else 0
        downvotes=[r for r in post_data["reactions"] if r["reactionType"] == "DOWNVOTE"][0]["count"] if [r for r in post_data["reactions"] if r["reactionType"] == "DOWNVOTE"] else 0
        
        creation_date = datetime.fromisoformat(post_data["createdAt"].replace('Z', '+00:00'))
        formatted_date = creation_date.strftime(config["app"]["date_fmt"])
        
        return LeetCodePost(
            id=post_data["topic"]["id"],
            title=post_data["title"],
            content=post_data["content"],
            vote_count=upvotes - downvotes,
            comment_count=post_data["topic"]["topLevelCommentCount"],
            view_count=post_data["hitCount"],
            creation_date=formatted_date
        )

    def should_parse_post(self, post: LeetCodePost) -> bool:
        if "|" not in post.title:
            return False
        if post.vote_count < 0:
            return False
        return True

def has_crossed_till_date(creation_date: str, till_date) -> bool:
    if till_date is None:
        return False
    dt = datetime.strptime(creation_date, config["app"]["date_fmt"])
    return dt <= till_date

def is_within_lag_period(creation_date: str) -> bool:
    post_date = datetime.strptime(creation_date, config["app"]["date_fmt"])
    lag_cutoff = datetime.now() - timedelta(days=LAG_DAYS)
    return post_date > lag_cutoff

def get_existing_ids(filepath: str) -> set:
    if not os.path.exists(filepath):
        return set()
    
    existing_ids = set()
    with open(filepath, "r") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                existing_ids.add(data["id"])
    return existing_ids

def refresh_posts(output_file: str, max_posts: int = 100):
    fetcher = LeetCodeFetcher()
    existing_ids = get_existing_ids(output_file)
    till_date = latest_parsed_date(output_file)
    
    skip = 0
    first = 50
    new_posts_count = 0
    skipped_due_to_lag = 0
    
    with open(output_file, "a") as f:
        while new_posts_count < max_posts:
            posts_list = fetcher.fetch_posts_list(skip, first)
            
            if not posts_list:
                break
                
            for post_edge in posts_list:
                topic_id = post_edge["node"]["topicId"]
                
                if topic_id in existing_ids:
                    continue
                
                try:
                    post_details = fetcher.fetch_post_details(topic_id)
                    post = fetcher.parse_post_data(post_details)
                    
                    if has_crossed_till_date(post.creation_date, till_date):
                        print(f"Reached posts older than {till_date}, stopping...")
                        break
                    
                    if is_within_lag_period(post.creation_date):
                        skipped_due_to_lag += 1
                        continue
                    
                    if fetcher.should_parse_post(post):
                        f.write(json.dumps(asdict(post)) + "\n")
                        f.flush()
                        new_posts_count += 1
                        print(f"Fetched post {topic_id} from {post.creation_date}: {post.title[:50]}...")
                        
                        if new_posts_count >= max_posts:
                            break
                
                except Exception as e:
                    print(f"Error fetching post {topic_id}: {e}")
                    continue
            
            skip += first
            
            if len(posts_list) < first:
                break
    
    print(f"Fetched {new_posts_count} new posts")
    if skipped_due_to_lag > 0:
        print(f"Skipped {skipped_due_to_lag} posts due to {LAG_DAYS}-day lag period")
    sort_and_truncate(output_file)

if __name__ == "__main__":
    output_file = config["app"]["data_dir"] / "raw_comps.jsonl"
    refresh_posts(str(output_file))