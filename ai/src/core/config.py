from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Device = Literal["auto", "cpu", "cuda", "mps"]
Strategy = Literal["fixed", "overlap", "paragraph", "heading", "page"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", validate_default=True, hide_input_in_errors=True
    )
    app_name: str = "Enterprise Search AI"
    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    debug: bool = False
    api_prefix: str = Field("/api/v1", pattern=r"^/(?:[a-zA-Z0-9_-]+/)*v1$")
    internal_api_key: SecretStr = Field(min_length=16)
    ai_device: Device = "auto"
    ai_allow_device_fallback: bool = True
    ai_lazy_model_loading: bool = True
    ai_required_models: list[Literal["text", "colpali"]] = []
    ai_model_cache_dir: Path = Path("model-cache")
    ai_offline: bool = True
    text_embedding_model_id: str = "sentence-transformers/all-MiniLM-L6-v2"
    text_embedding_revision: str = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    text_embedding_device: Device = "auto"
    text_embedding_batch_size: int = Field(16, ge=1, le=128)
    text_embedding_normalize: bool = True
    colpali_model_id: str = "vidore/colpali-v1.3-merged"
    colpali_revision: str = "c24894ff88e82f6e11d92e89a62572d324969bbc"
    colpali_device: Device = "auto"
    colpali_precision: Literal["fp32", "fp16", "bf16"] = "fp32"
    colpali_max_query_tokens: int = Field(512, ge=16, le=4096)
    colpali_batch_size: int = Field(1, ge=1, le=16)
    ai_max_concurrent_inferences: int = Field(1, ge=1, le=8)
    ai_inference_timeout_seconds: float = Field(300, gt=0)
    max_request_bytes: int = Field(2_000_000, gt=0)
    max_upload_bytes: int = Field(50_000_000, gt=0)
    max_pages: int = Field(200, gt=0)
    max_image_pixels: int = Field(25_000_000, gt=0)
    max_image_side: int = Field(2400, ge=128)
    supported_mime_types: set[str] = {"application/pdf", "image/png", "image/jpeg"}
    render_dpi: int = Field(150, ge=36, le=600)
    render_format: Literal["PNG", "JPEG"] = "PNG"
    ocr_languages: str = Field("eng", pattern=r"^[a-zA-Z0-9_]+(\+[a-zA-Z0-9_]+)*$")
    ocr_deskew: bool = True
    ocr_psm: int = Field(6, ge=1, le=13)
    ocr_min_confidence: float = Field(55, ge=0, le=100)
    ocr_timeout_seconds: int = Field(45, ge=1)
    native_min_chars: int = Field(20, ge=1)
    chunk_strategy: Strategy = "heading"
    chunk_size: int = Field(1000, ge=8)
    chunk_overlap: int = Field(100, ge=0)
    storage_backend: Literal["local", "s3"] = "local"
    storage_root: Path = Path("objects")
    storage_endpoint: str | None = None
    storage_bucket: str | None = None
    storage_region: str = "us-east-1"
    storage_access_key: SecretStr | None = None
    storage_secret_key: SecretStr | None = None
    storage_timeout: int = Field(15, ge=1)
    presign_seconds: int = Field(300, ge=1, le=604800)
    llm_provider: Literal["disabled", "openai-compatible"] = "disabled"
    llm_endpoint: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_response_format: Literal["json_schema", "json_object"] = "json_schema"
    llm_timeout: float = Field(30, gt=0)
    llm_retries: int = Field(2, ge=0, le=5)

    @model_validator(mode="after")
    def validate_settings(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.storage_backend == "s3" and not self.storage_bucket:
            raise ValueError("storage_bucket is required for S3")
        if bool(self.storage_access_key) != bool(self.storage_secret_key):
            raise ValueError("configure both storage credentials or use the SDK credential chain")
        if self.llm_provider != "disabled" and not (self.llm_endpoint and self.llm_model):
            raise ValueError("llm_endpoint and llm_model are required for candidate extraction")
        return self
