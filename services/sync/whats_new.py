"""Fetch and parse the AWS What's New RSS feed to identify recently updated services."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
from pydantic import BaseModel

from core.logging import get_logger

logger = get_logger(__name__)

_WHATS_NEW_RSS = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"
_REQUEST_TIMEOUT = 15.0


@dataclass
class WhatsNewItem:
    title: str
    link: str
    description: str
    pub_date: str


class ServiceUpdate(BaseModel):
    service_name: str  # e.g. "s3", "lambda", "ec2"
    headline: str
    source_url: str


async def fetch_whats_new(limit: int = 20) -> list[WhatsNewItem]:
    """Fetch the AWS What's New RSS feed and return the most recent items."""
    logger.info("Fetching AWS What's New RSS feed")
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(_WHATS_NEW_RSS)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    channel = root.find("channel")
    if channel is None:
        logger.warning("No <channel> element found in RSS feed")
        return []

    items: list[WhatsNewItem] = []
    for item in channel.findall("item")[:limit]:
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        description = item.findtext("description", "")
        pub_date = item.findtext("pubDate", "")
        items.append(
            WhatsNewItem(title=title, link=link, description=description, pub_date=pub_date)
        )

    logger.info("Fetched What's New items", extra={"count": len(items)})
    return items


# ── Keyword → canonical service name mapping ─────────────────────────────────
_SERVICE_KEYWORDS: dict[str, str] = {
    "s3": "s3",
    "simple storage": "s3",
    "lambda": "lambda",
    "ec2": "ec2",
    "elastic compute": "ec2",
    "rds": "rds",
    "relational database": "rds",
    "aurora": "aurora",
    "dynamodb": "dynamodb",
    "cloudfront": "cloudfront",
    "cloudwatch": "cloudwatch",
    "iam": "iam",
    "identity and access": "iam",
    "vpc": "vpc",
    "virtual private cloud": "vpc",
    "eks": "eks",
    "elastic kubernetes": "eks",
    "ecs": "ecs",
    "elastic container": "ecs",
    "fargate": "fargate",
    "sqs": "sqs",
    "simple queue": "sqs",
    "sns": "sns",
    "simple notification": "sns",
    "api gateway": "apigateway",
    "cloudformation": "cloudformation",
    "bedrock": "bedrock",
    "sagemaker": "sagemaker",
    "glue": "glue",
    "athena": "athena",
    "redshift": "redshift",
    "kinesis": "kinesis",
    "step functions": "stepfunctions",
    "route 53": "route53",
    "elastic load": "elb",
    "secrets manager": "secretsmanager",
    "kms": "kms",
    "key management": "kms",
    "waf": "waf",
    "shield": "shield",
}


def extract_services(item: WhatsNewItem) -> list[str]:
    """Return a deduplicated list of AWS service names mentioned in the item."""
    text = f"{item.title} {item.description}".lower()
    found: set[str] = set()
    for keyword, service in _SERVICE_KEYWORDS.items():
        if keyword in text:
            found.add(service)
    return sorted(found)


def items_to_service_updates(items: list[WhatsNewItem]) -> list[ServiceUpdate]:
    """Convert RSS items to ServiceUpdate objects, one per service mentioned."""
    updates: list[ServiceUpdate] = []
    seen: set[str] = set()
    for item in items:
        for service in extract_services(item):
            if service not in seen:
                seen.add(service)
                updates.append(
                    ServiceUpdate(
                        service_name=service,
                        headline=item.title,
                        source_url=item.link,
                    )
                )
    logger.info("Services identified from What's New", extra={"count": len(updates)})
    return updates
