from src.core.runtime import ServiceError


def select(request: str, default: str, allow_fallback: bool, torch) -> tuple[str, bool]:
    requested = default if request == "auto" else request
    available = {
        "cpu": True,
        "cuda": torch.cuda.is_available(),
        "mps": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
    }
    if requested == "auto":
        return next(d for d in ("cuda", "mps", "cpu") if available[d]), False
    if available[requested]:
        return requested, False
    if allow_fallback:
        return "cpu", True
    raise ServiceError("device_unavailable", "Configured device is unavailable.", "model_load", 503)


def precision(device: str, value: str, torch):
    if device == "cpu" or (value == "bf16" and (device == "mps" or not torch.cuda.is_bf16_supported())):
        value = "fp32"
    return value, {"fp32": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}[value]
