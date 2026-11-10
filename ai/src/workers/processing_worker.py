import argparse
import sys
from pathlib import Path

import structlog
from pydantic import ValidationError

from src.core.config import Settings
from src.core.lifecycle import runtime
from src.core.runtime import ServiceError, configure_logging
from src.schemas.contracts import Process


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute one versioned processing request and emit its manifest"
    )
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    cfg = Settings()
    configure_logging(cfg.log_level)
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))
    try:
        request = Process.model_validate_json(args.request.read_bytes())
        with runtime(cfg) as rt:
            manifest = rt.pipeline.run(request)
        print(manifest.model_dump_json())
        return 0 if manifest.status == "success" else 2
    except (ServiceError, ValidationError, OSError) as exc:
        print(exc.detail if isinstance(exc, ServiceError) else type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
