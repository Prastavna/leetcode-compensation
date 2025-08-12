import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from .config import config
from .helpers import retry_with_exp_backoff

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"
LAG_DAYS = 5

# OpenAI client for parsing
openai_client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.getenv("GITHUB_TOKEN"),
)


@dataclass
class LeetCodePost:
    """Data class for LeetCode post."""
    id: str
    title: str
    content: str
    vote_count: int
    comment_count: int
    view_count: int
    creation_date: str


class CompensationOffer(BaseModel):
    """Pydantic model for compensation offer validation."""
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
            return "N/A"
        return v


class CompensationOffers(BaseModel):
    """Container for multiple compensation offers."""
    offers: List[CompensationOffer] = Field(description="List of compensation offers")

    @field_validator("offers")
    @classmethod
    def validate_offers(cls, v: List[CompensationOffer]) -> List[CompensationOffer]:
        if not v:
            raise ValueError("At least one offer must be provided")
        return v


class LeetCodeFetcher:
    """LeetCode API client for fetching posts."""
    
    def __init__(self):
        transport = RequestsHTTPTransport(url=LEETCODE_GRAPHQL_URL)
        self.client = Client(transport=transport)
        
        with open("queries/discussion_post_items.gql", "r") as f:
            self.posts_query = gql(f.read())
        
        with open("queries/post_details.gql", "r") as f:
            self.details_query = gql(f.read())

    @retry_with_exp_backoff(retries=3)
    def fetch_posts_list(self, skip: int = 0, first: int = 50) -> List[dict]:
        """Fetch list of posts from LeetCode."""
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
        """Fetch detailed post data from LeetCode."""
        result = self.client.execute(self.details_query, variable_values={
            "topicId": topic_id
        })
        return result["ugcArticleDiscussionArticle"]

    def parse_post_data(self, post_data: dict) -> LeetCodePost:
        """Parse raw post data into LeetCodePost object."""
        upvotes = [r for r in post_data["reactions"] if r["reactionType"] == "UPVOTE"][0]["count"] if [r for r in post_data["reactions"] if r["reactionType"] == "UPVOTE"] else 0
        downvotes = [r for r in post_data["reactions"] if r["reactionType"] == "DOWNVOTE"][0]["count"] if [r for r in post_data["reactions"] if r["reactionType"] == "DOWNVOTE"] else 0
        
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
        """Determine if a post should be parsed based on criteria."""
        if "|" not in post.title:
            return False
        if post.vote_count < 0:
            return False
        return True


def is_within_lag_period(creation_date: str) -> bool:
    """Check if post is within the lag period."""
    post_date = datetime.strptime(creation_date, config["app"]["date_fmt"])
    lag_cutoff = datetime.now() - timedelta(days=LAG_DAYS)
    return post_date > lag_cutoff


def parse_compensation_with_openai(post_content: str) -> Optional[CompensationOffers]:
    """Parse compensation information from post content using OpenAI."""
    try:
        response = openai_client.chat.completions.parse(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that extracts compensation information from LeetCode posts. Extract all compensation offers mentioned in the post. If some role or company is not mentioned, return empty string for that field and not something like 'n/a' or startup. A post can also contain interview experience. Interview experience will always be a link to a leetcode post that can start with 'https://leetcode.com/discuss/post/'. If no interview experience is mentioned or it is mentinoed within the post, return empty string for that field. You need to determine whether the post is India based/Remote or not. If it is not India based, return empty string for that field.",
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