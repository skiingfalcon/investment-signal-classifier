"""Per-model quirks needed to force Simple Jev's answer boundary on a llama-server chat template.

Qwen3.x's template closes its think block when ``enable_thinking`` is false
(``<think>\n\n</think>\n\n``); an older/misconfigured server that ignores the kwarg instead
leaves it open (``<think>\n``), which would score a next-token distribution inside a reasoning
block instead of at the answer. ``patchable_boundary`` lets the compiler fix that up rather than
fail outright, while still recording that it had to.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    name: str
    default_port: int
    chat_template_kwargs: dict
    expected_boundary: str
    patchable_boundary: tuple[str, str] | None = None
    assistant_prefill: str = ""
    supported: bool = True
    unsupported_reason: str = ""


PROFILES: dict[str, ModelProfile] = {
    "qwen3.8-27b": ModelProfile(
        name="qwen3.8-27b",
        default_port=8084,
        chat_template_kwargs={"enable_thinking": False},
        expected_boundary="<|im_start|>assistant\n<think>\n\n</think>\n\n",
        patchable_boundary=(
            "<|im_start|>assistant\n<think>\n",
            "<|im_start|>assistant\n<think>\n\n</think>\n\n",
        ),
    ),
    "gpt-oss-120b": ModelProfile(
        name="gpt-oss-120b",
        default_port=8082,
        chat_template_kwargs={"reasoning_effort": "low"},
        expected_boundary="<|start|>assistant",
        assistant_prefill="<|channel|>final<|message|>",
        supported=False,
        unsupported_reason=(
            "harmony forces an analysis channel before the final answer; forcing the final "
            "channel directly is off-distribution and letter labels may not be single-token "
            "stable there. Use gpt-oss-120b as the generative arbiter instead (isc.verify), "
            "where it decodes normally."
        ),
    ),
}


def resolve_profile(model: str, *, allow_experimental: bool = False) -> ModelProfile:
    try:
        profile = PROFILES[model]
    except KeyError:
        raise ValueError(f"No JEV model profile for {model!r}; known: {sorted(PROFILES)}") from None
    if not profile.supported and not allow_experimental:
        raise ValueError(
            f"{model!r} is experimental as a JEV backend: {profile.unsupported_reason} "
            "(pass allow_experimental=True to override)"
        )
    return profile
