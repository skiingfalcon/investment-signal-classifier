"""Make simple-jev's engine-independent ``common`` package importable.

``common/`` has no pyproject of its own (see hf-server/pyproject.toml, which bundles it the
same way via ``package-dir``). An editable install already resolves it through the mapping in
this project's pyproject.toml; this shim additionally covers running straight from a checkout
without installing, mirroring hf_server.py's own sys.path insertion.
"""

from __future__ import annotations

import sys
from pathlib import Path

_checkout_root = Path(__file__).resolve().parents[3]
if (_checkout_root / "common" / "prompt_builder.py").is_file():
    sys.path.insert(0, str(_checkout_root))

from common import (  # noqa: E402
    ClassifierRequest,
    PromptPlan,
    ScoringQuestion,
    build_answers,
    build_response,
    prepare_prompt,
)
from common.prompt_builder import DEFAULT_TEMPLATE_VERSION, canonical  # noqa: E402

__all__ = [
    "DEFAULT_TEMPLATE_VERSION",
    "ClassifierRequest",
    "PromptPlan",
    "ScoringQuestion",
    "build_answers",
    "build_response",
    "canonical",
    "prepare_prompt",
]
