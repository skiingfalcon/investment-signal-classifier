"""Runtime settings, read from the environment (prefix ``ISC_``) or a ``.env`` file."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ISC_", env_file=".env", extra="ignore")

    # llama-cpp-spark checkout: source of the 10-K corpus and prior extraction runs.
    spark_repo: Path = Field(
        default_factory=lambda: Path("~/projects/llama-cpp-spark").expanduser()
    )

    # Simple Jev logit-classifier backend (llama-server /completion, /tokenize, /apply-template).
    # The Spark keeps one large model resident at a time, so this is the only local server.
    jev_base_url: str = "http://127.0.0.1:8084"
    jev_model: str = "qwen3.8-27b"

    # Generative arbiter for escalated disagreements. Default is a hosted frontier model, not a
    # second local server: it only fires on disputed questions, and llama-cpp-spark /
    # jev-email-cascade already establish this exact convention (bare OPENAI_API_KEY /
    # OPENAI_BASE_URL env vars, no ISC_ prefix, so one .env serves every project in the family).
    # Set gen_provider="local" + ISC_GEN_BASE_URL to point this at a second llama-server instead,
    # on a box with spare capacity.
    gen_provider: Literal["openai", "local"] = "openai"
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    gen_base_url: str = Field(
        default="https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL"
    )
    gen_model: str = "gpt-5.6-terra"
    gen_reasoning_effort: str = "low"
    gen_max_tokens: int = 1500

    facts_path: Path = Path("data/facts.jsonl")
    runs_dir: Path = Path("runs")
    timeout_s: float = 600.0

    @property
    def sec_data_dir(self) -> Path:
        return self.spark_repo / "evals" / "data" / "sec"

    @property
    def sec_state_dir(self) -> Path:
        return self.spark_repo / "state" / "evals" / "sec"

    @property
    def evals_toml(self) -> Path:
        return self.spark_repo / "evals.toml"


def get_settings() -> Settings:
    return Settings()
