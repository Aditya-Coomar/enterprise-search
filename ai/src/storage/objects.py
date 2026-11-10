import os
import re
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.core.config import Settings
from src.core.runtime import ServiceError, digest, now
from src.schemas.contracts import Artifact


def safe_key(key: str) -> str:
    parts = key.split("/")
    if len(key) > 1024 or any(
        not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}", p)
        or p.endswith(".")
        or p.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        for p in parts
    ):
        raise ServiceError("invalid_key", "Invalid storage key.", "storage")
    return key


def derived(key: str) -> str:
    safe_key(key)
    parts = key.split("/")
    if not (
        len(parts) >= 8
        and parts[0] == "tenant"
        and parts[2] == "documents"
        and parts[4] == "versions"
        and parts[6] == "derived"
        or len(parts) >= 5
        and parts[0] == "tenant"
        and parts[2:4] == ["queries", "derived"]
    ):
        raise ServiceError("protected_key", "Writes require a derived artifact key.", "storage")
    return key


class Store(Protocol):
    def read(self, key: str, limit: int) -> bytes: ...
    def put(self, key: str, data: bytes, mime: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str) -> str: ...
    def ready(self) -> bool: ...
    def close(self) -> None: ...


def limit_read(stream, limit: int) -> bytes:
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ServiceError("file_too_large", "Object exceeds the byte limit.", "storage", 413)
    return data


class LocalStore:
    def __init__(self, settings: Settings):
        self.root = settings.storage_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        path = self.root
        for part in safe_key(key).split("/"):
            # Encode uppercase in a reserved alphabet so case-insensitive volumes preserve S3 identity.
            encoded = re.sub(r"[A-Z]", lambda m: "~" + m.group().lower(), part)
            path = path / (encoded if len(encoded) <= 200 else "~h~" + digest(part.encode()))
            if path.is_symlink():
                raise ServiceError(
                    "invalid_path", "Object paths cannot contain symbolic links.", "storage"
                )
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ServiceError("invalid_path", "Object outside storage root.", "storage")
        return path

    def read(self, key: str, limit: int) -> bytes:
        try:
            with self.path(key).open("rb") as f:
                return limit_read(f, limit)
        except FileNotFoundError as exc:
            raise ServiceError("missing_source", "Object does not exist.", "storage", 404) from exc

    def put(self, key: str, data: bytes, mime: str) -> None:
        path = self.path(derived(key))
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            name = Path(tmp.name)
        try:
            name.write_bytes(data)
            os.replace(name, path)
        finally:
            name.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def delete(self, key: str) -> None:
        self.path(derived(key)).unlink(missing_ok=True)

    def signed_url(self, key: str) -> str:
        raise ServiceError("signed_url_unavailable", "Signed URLs require S3.", "storage", 501)

    def ready(self) -> bool:
        return self.root.is_dir() and os.access(self.root, os.R_OK | os.W_OK)

    def close(self) -> None:
        pass


class S3Store:
    def __init__(self, settings: Settings):
        self.bucket = settings.storage_bucket
        self.ttl = settings.presign_seconds
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            region_name=settings.storage_region,
            aws_access_key_id=settings.storage_access_key.get_secret_value()
            if settings.storage_access_key
            else None,
            aws_secret_access_key=settings.storage_secret_key.get_secret_value()
            if settings.storage_secret_key
            else None,
            config=Config(
                connect_timeout=settings.storage_timeout,
                read_timeout=settings.storage_timeout,
                retries={"mode": "standard", "total_max_attempts": 3},
            ),
        )

    def call(self, method: str, **kwargs):
        try:
            return getattr(self.client, method)(Bucket=self.bucket, **kwargs)
        except ClientError as exc:
            status = exc.response["ResponseMetadata"]["HTTPStatusCode"]
            if status == 404:
                raise ServiceError("missing_source", "Object does not exist.", "storage", 404) from exc
            raise ServiceError(
                "storage_error",
                "Object storage request failed.",
                "storage",
                502,
                status >= 500 or status in (408, 429),
            ) from exc
        except BotoCoreError as exc:
            raise ServiceError(
                "storage_unavailable", "Object storage is unavailable.", "storage", 503, True
            ) from exc

    def read(self, key: str, limit: int) -> bytes:
        response = self.call("get_object", Key=safe_key(key))
        with closing(response["Body"]) as stream:
            if response["ContentLength"] > limit:
                raise ServiceError("file_too_large", "Object exceeds the byte limit.", "storage", 413)
            return limit_read(stream, limit)

    def put(self, key: str, data: bytes, mime: str) -> None:
        self.call(
            "put_object",
            Key=derived(key),
            Body=data,
            ContentType=mime,
            Metadata={"sha256": digest(data)},
        )

    def exists(self, key: str) -> bool:
        try:
            self.call("head_object", Key=safe_key(key))
        except ServiceError as exc:
            if exc.status == 404:
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        self.call("delete_object", Key=derived(key))

    def signed_url(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": safe_key(key)}, ExpiresIn=self.ttl
        )

    def ready(self) -> bool:
        self.call("head_bucket")
        return True

    def close(self) -> None:
        self.client.close()


def save(store: Store, stem: str, extension: str, data: bytes, mime: str, **metadata) -> Artifact:
    checksum = digest(data)
    key = f"{stem}-{checksum}.{extension}"
    store.put(key, data, mime)
    parts = stem.split("/")
    if parts[2] == "documents":
        metadata.update(
            tenant_id=parts[1],
            document_id=parts[3],
            document_version_id=parts[5],
            pipeline_version=parts[7],
            processing_run_id=parts[8],
            artifact_type=parts[-1],
        )
    return Artifact(
        key=key, sha256=checksum, size=len(data), media_type=mime, created_at=now(), metadata=metadata
    )
