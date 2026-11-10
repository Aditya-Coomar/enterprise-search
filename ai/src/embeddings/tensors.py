import hmac
from io import BytesIO

import numpy as np

from src.core.runtime import ServiceError, digest


def validate_tensor(array: np.ndarray, rank: int) -> np.ndarray:
    data = np.asarray(array, dtype="<f4", order="C")
    if data.ndim != rank or not all(data.shape) or not np.isfinite(data).all():
        raise ServiceError(
            "invalid_model_output", "Model returned invalid dimensions or values.", "inference", 502
        )
    return data


def serialize(array: np.ndarray) -> bytes:
    with BytesIO() as stream:
        np.save(stream, validate_tensor(array, 2), allow_pickle=False)
        return stream.getvalue()


def deserialize(data: bytes, checksum: str, shape: list[int]) -> np.ndarray:
    if not hmac.compare_digest(digest(data), checksum):
        raise ServiceError("checksum_mismatch", "Embedding checksum mismatch.", "deserialize")
    with BytesIO(data) as stream:
        result = np.load(stream, allow_pickle=False)
        if result.dtype.str != "<f4" or list(result.shape) != shape or stream.tell() != len(data):
            raise ServiceError("invalid_tensor", "Tensor metadata mismatch.", "deserialize")
        return validate_tensor(result, 2)
