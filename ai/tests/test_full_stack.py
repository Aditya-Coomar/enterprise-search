"""Opt-in acceptance test with real pretrained models, local S3 HTTP and a configured LLM."""

import json
import os
from urllib.parse import urlsplit
from uuid import uuid4

import boto3
import pymupdf
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.embeddings.tensors import deserialize
from tests.fixtures.documents import scan
from tests.test_pipeline import AUTH, KEY, config, request_data


@pytest.mark.model
def test_all_stages_in_one_http_request(tmp_path):
    if os.getenv("RUN_FULL_STACK_TEST") != "1":
        pytest.skip("Requires pinned weights, loopback S3 and a configured LLM")
    endpoint = os.environ["TEST_LOCAL_S3_ENDPOINT"]
    assert urlsplit(endpoint).hostname in {"localhost", "127.0.0.1", "::1"}
    bucket = "enterprise-ai-acceptance-" + uuid4().hex
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    s3.create_bucket(Bucket=bucket)
    try:
        with pymupdf.open() as source:
            p = source.new_page(width=540, height=360)
            p.insert_text((24, 65), "Project Mercury was approved by Ada Patel.", fontsize=13)
            p.insert_image(pymupdf.Rect(10, 140, 530, 270), stream=scan())
            s3.put_object(Bucket=bucket, Key=KEY, Body=source.tobytes())
        cfg = config(
            tmp_path,
            ai_device="cpu",
            ai_inference_timeout_seconds=600,
            storage_backend="s3",
            storage_endpoint=endpoint,
            storage_bucket=bucket,
            storage_access_key="test",
            storage_secret_key="test",
        )
        with TestClient(create_app(cfg)) as api:
            request = request_data(
                [
                    "render",
                    "extraction",
                    "chunks",
                    "text_embeddings",
                    "visual_embeddings",
                    "entities",
                    "relationships",
                ]
            )
            m = api.post("/api/v1/process", json=request, headers=AUTH).json()
            assert m["status"] == "success", m
            artifacts = m["pages"][0]["artifacts"]

            def read(name):
                return s3.get_object(Bucket=bucket, Key=artifacts[name]["key"])["Body"].read()

            page = json.loads(read("extraction"))
            assert page["extraction_method"] == "native+ocr" and "fifty monitors" in page["text"].lower()
            assert "image_1" in artifacts
            vectors = json.loads(read("text_embeddings"))
            assert vectors[0]["metadata"]["dimensions"] == len(vectors[0]["vector"])
            ref = artifacts["visual_embeddings"]
            array = deserialize(read("visual_embeddings"), ref["sha256"], ref["metadata"]["shape"])
            assert array.shape[0] > 100 and array.shape[1] > 1
            candidates = json.loads(read("relationships"))
            assert any(
                r["relationship_type"] == "APPROVED_BY"
                and "Mercury" in r["source"]
                and "Ada" in r["target"]
                for item in candidates
                for r in item["relationships"]
            ), candidates
            assert api.post("/api/v1/process", json=request, headers=AUTH).json() == m
    finally:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        s3.delete_bucket(Bucket=bucket)
