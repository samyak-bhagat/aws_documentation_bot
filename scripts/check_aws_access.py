"""Ping AWS services required for deployment. Uses default AWS credential chain."""

from __future__ import annotations

import json
import sys

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

REGION = "us-east-1"
SERVICES = [
    ("sts", lambda s: s.client("sts").get_caller_identity()),
    ("ecr", lambda s: s.client("ecr").describe_repositories(maxResults=1)),
    ("rds", lambda s: s.client("rds").describe_db_instances(MaxRecords=20)),
    ("ecs", lambda s: s.client("ecs").list_clusters(maxResults=10)),
    ("opensearch", lambda s: s.client("opensearch").list_domain_names()),
    ("secretsmanager", lambda s: s.client("secretsmanager").list_secrets(MaxResults=5)),
    ("bedrock", lambda s: s.client("bedrock").list_foundation_models(byOutputModality="TEXT")),
]


def main() -> int:
    results: dict[str, object] = {}
    try:
        session = boto3.Session(region_name=REGION)
        for name, fn in SERVICES:
            try:
                fn(session)
                results[name] = {"ok": True}
            except ClientError as exc:
                err = exc.response["Error"]
                results[name] = {
                    "ok": False,
                    "code": err.get("Code"),
                    "message": err.get("Message", ""),
                }
            except Exception as exc:  # noqa: BLE001
                results[name] = {"ok": False, "error": str(exc)}

        try:
            br = session.client("bedrock-runtime", region_name=REGION)
            br.invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=json.dumps({"inputText": "ping"}).encode(),
                contentType="application/json",
                accept="application/json",
            )
            results["bedrock_invoke"] = {"ok": True, "model": "amazon.titan-embed-text-v2:0"}
        except ClientError as exc:
            err = exc.response["Error"]
            results["bedrock_invoke"] = {
                "ok": False,
                "code": err.get("Code"),
                "message": err.get("Message", ""),
            }
        except Exception as exc:  # noqa: BLE001
            results["bedrock_invoke"] = {"ok": False, "error": str(exc)}

        ident = session.client("sts").get_caller_identity()
        results["account"] = ident["Account"]
        results["arn"] = ident["Arn"]
    except NoCredentialsError:
        print(json.dumps({"error": "No AWS credentials found. Run: aws configure"}, indent=2))
        return 1

    print(json.dumps(results, indent=2))
    failed = [k for k, v in results.items() if isinstance(v, dict) and v.get("ok") is False]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
