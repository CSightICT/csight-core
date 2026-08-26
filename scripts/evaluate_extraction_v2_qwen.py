"""Fail honestly when the real Qwen extraction endpoint is not configured."""

from app.bootstrap.settings import Settings


def main() -> None:
    settings = Settings()
    if settings.llm_provider != "vllm" or settings.llm_base_url_value is None:
        print("SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE")
        return
    raise SystemExit(
        "External Qwen endpoint is configured; run the approved qualification harness before Test."
    )


if __name__ == "__main__":
    main()
