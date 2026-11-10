"""Opt-in integration against a real, local S3-compatible HTTP service."""

import os
from urllib.parse import urlsplit
from uuid import uuid4

import boto3
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.runtime import digest
from tests.fixtures.documents import pdf
from tests.test_pipeline import AUTH, KEY, config, request_data


def test_local_s3_http(tmp_path):
    endpoint = os.environ.get("TEST_LOCAL_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("Set TEST_LOCAL_S3_ENDPOINT for the loopback S3 integration")
    assert urlsplit(endpoint).hostname in ("127.0.0.1", "localhost", "::1")
    bucket = "enterprise-ai-test-" + uuid4().hex
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    s3.create_bucket(Bucket=bucket)
    try:
        cfg = config(
            tmp_path,
            storage_backend="s3",
            storage_endpoint=endpoint,
            storage_bucket=bucket,
            storage_access_key="test",
            storage_secret_key="test",
        )
        s3.put_object(Bucket=bucket, Key=KEY, Body=pdf(("native", "table")))
        with TestClient(create_app(cfg)) as api:
            assert api.get("/health/ready").status_code == 200
            m = api.post("/api/v1/process", json=request_data(["render", "chunks"]), headers=AUTH).json()
            assert m["status"] == "success"
            ref = m["pages"][1]["artifacts"]["chunks"]
            assert digest(s3.get_object(Bucket=bucket, Key=ref["key"])["Body"].read()) == ref["sha256"]
    finally:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        s3.delete_bucket(Bucket=bucket)
