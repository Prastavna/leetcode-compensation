from dataclasses import asdict, dataclass
import datetime
import json
import os
from typing import Optional, List
from utils import config
from pydantic import BaseModel, Field, field_validator
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from openai import OpenAI

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.getenv("GITHUB_TOKEN"),
)

class CompensationOffer(BaseModel):
    company: str = Field(description="Company name")
    role: str = Field(description="Job role/title")
    yoe: float = Field(description="Years of experience", ge=0, le=50)
    base_offer: float = Field(description="Base salary offer")
    total_offer: float = Field(description="Total compensation offer")
    location: Optional[str] = Field(default="n/a", description="Job location")
    non_indian: Optional[str] = Field(
        default=None, description="Non-Indian candidate flag"
    )

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

        # Check if original value is in valid range
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

        # Check if original value is in valid range
        if min_total <= v <= max_total:
            return v

        raise ValueError(
            f"total_offer {v} is out of range [{min_total}, {max_total}] even after conversion"
        )

    @classmethod
    def validate_non_indian(cls, v: str) -> str:
        if v == "yes":
            raise ValueError("non_indian cannot be 'yes'")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if "intern" in v.lower():
            raise ValueError("intern roles are not supported")
        if not v.strip():
            raise ValueError("empty roles are not supported")
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

@dataclass
class LeetCodePost:
    id: str
    title: str
    content: str
    vote_count: int
    comment_count: int
    view_count: int
    creation_date: datetime

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
            response_format=CompensationOffer,
        )

        return response.choices[0].message.parsed
    except Exception as e:
        print(f" x OpenAI parsing error: {str(e)}")
        return None


def main():
    transport = RequestsHTTPTransport(url=LEETCODE_GRAPHQL_URL)
    client = Client(transport=transport)
    with open("queries/discussion_post_items.gql", "r") as f:
        query_string = f.read()

    posts=[]
    query = gql(query_string)
    try:
        result = client.execute(query, variable_values={
            "orderBy": "MOST_RECENT",
            "keywords": [],
            "tagSlugs": ["compensation"],
            "skip": 0,
            "first": 1
        })
        # print(json.dumps(result, indent=2))
        postId = result["ugcArticleDiscussionArticles"]["edges"][0]["node"]["topicId"]
        with open("queries/post_details.gql", "r") as f:
            query_string = f.read()

        query = gql(query_string)
        try:
            result = client.execute(query, variable_values={
                "topicId": postId
            })
            print(json.dumps(result, indent=2))
            posts.append(asdict(LeetCodePost(
                id=result["ugcArticleDiscussionArticle"]["topic"]["id"],
                title=result["ugcArticleDiscussionArticle"]["title"],
                content=result["ugcArticleDiscussionArticle"]["content"],
    # "reactions": [
    #   {
    #     "count": 6,
    #     "reactionType": "UPVOTE"
    #   }
    # ],
                # vote_count=len(list(filter(lambda x: x["reactionType"] == "UPVOTE", result
                # ["ugcArticleDiscussionArticle"]["reactions"]))) - len(list(filter(lambda x: x["reactionType"] == "DOWNVOTE", result["ugcArticleDiscussionArticle"]["reactions"]))) ,
                
                # filter out the count of obj with reactionType = UPVOTE and get the count
                vote_count=[r for r in result["ugcArticleDiscussionArticle"]["reactions"] if r["reactionType"] == "UPVOTE"][0]["count"] if [r for r in result["ugcArticleDiscussionArticle"]["reactions"] if r["reactionType"] == "UPVOTE"] else 0,
                comment_count=result["ugcArticleDiscussionArticle"]["topic"]["topLevelCommentCount"],
                view_count=result["ugcArticleDiscussionArticle"]["hitCount"],
                creation_date=result["ugcArticleDiscussionArticle"]["createdAt"]
            )))

            print("Vote count: ", posts[0]["vote_count"])

            # print(posts[0])
            # compensation_offers = parse_compensation_with_openai(
            #     posts[0]["content"]
            # )
            # if compensation_offers:
            #     print(json.dumps(asdict(compensation_offers), indent=2))
        except Exception as e:
            print(f"Error executing query: {e}")

    except Exception as e:
        print(f"Error executing query: {e}")


if __name__ == "__main__":
    main()
