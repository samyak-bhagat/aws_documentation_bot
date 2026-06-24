"""Unit tests for services/sync/whats_new.py — no network required."""

from services.sync.whats_new import (
    WhatsNewItem,
    extract_services,
    items_to_service_updates,
)


def _item(title: str, description: str = "") -> WhatsNewItem:
    return WhatsNewItem(
        title=title, link="https://aws.amazon.com/new/", description=description, pub_date=""
    )


class TestExtractServices:
    def test_s3_keyword(self):
        item = _item("Amazon S3 now supports object expiration")
        assert "s3" in extract_services(item)

    def test_lambda_keyword(self):
        item = _item("AWS Lambda increases timeout limit")
        assert "lambda" in extract_services(item)

    def test_multiple_services(self):
        item = _item("Amazon S3 and Lambda integration update")
        services = extract_services(item)
        assert "s3" in services
        assert "lambda" in services

    def test_no_known_service(self):
        item = _item("AWS announces new pricing for everything")
        assert extract_services(item) == []

    def test_case_insensitive(self):
        item = _item("AMAZON S3 BUCKET POLICY UPDATE")
        assert "s3" in extract_services(item)

    def test_iam_keyword(self):
        item = _item("Identity and Access Management policy changes")
        assert "iam" in extract_services(item)

    def test_description_also_searched(self):
        item = _item("New feature", "Affects Amazon DynamoDB tables")
        assert "dynamodb" in extract_services(item)


class TestItemsToServiceUpdates:
    def test_deduplicates_same_service(self):
        items = [
            _item("S3 update 1"),
            _item("S3 update 2"),
        ]
        updates = items_to_service_updates(items)
        services = [u.service_name for u in updates]
        assert services.count("s3") == 1

    def test_empty_items(self):
        assert items_to_service_updates([]) == []

    def test_returns_correct_fields(self):
        items = [_item("AWS Lambda concurrency update")]
        updates = items_to_service_updates(items)
        assert len(updates) == 1
        assert updates[0].service_name == "lambda"
        assert updates[0].headline == "AWS Lambda concurrency update"
