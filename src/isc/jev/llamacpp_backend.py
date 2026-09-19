"""Render Simple Jev prompts against a llama-server model, read label logits, score them.

Per branch (one per question, sharing everything up to the question text):

1. Build system/user messages exactly like hf-server's ``PromptCompiler`` (state -> user =
   ``"State:\n" + canonical(state) + "\n\n" + suffix + question.instruction``).
2. Render with ``/apply-template`` using the model's ``chat_template_kwargs`` (Qwen:
   ``enable_thinking: false``), which should close the think block before the answer boundary;
   patch it if the server ignored the kwarg (see ``model_profiles.py``).
3. Append ``question.answer_prefix`` (``{"answer": "`` or ``{"answer": ``); tokenize; verify each
   output label is single-token stable at that exact boundary (hf_server's own check, run
   against llama-server's tokenizer).
4. ``/completion`` with the token-id prompt, ``n_predict: 1``, ``n_probs`` wide enough to cover
   every label; read ``top_logprobs`` for each label by token id.
5. Feed the label -> logprob maps into ``common.build_response`` -- softmax is shift-invariant,
   so log-probabilities score identically to raw logits.

Branches share a token prefix through the state and reminder text; llama-server's
longest-common-prefix slot selection keeps that prefix warm across calls on the same slot
(``cache_prompt: true``, default ``id_slot: -1``, sequential by default).
"""

from __future__ import annotations

from dataclasses import dataclass

from isc._common import (
    ClassifierRequest,
    PromptPlan,
    ScoringQuestion,
    build_response,
    canonical,
    prepare_prompt,
)
from isc.jev.llama_server import LlamaServerClient
from isc.jev.model_profiles import ModelProfile


def common_prefix(sequences: list[list[int]]) -> list[int]:
    """Longest identical token prefix of a nonempty sequence group (hf_server.common_prefix)."""
    first = sequences[0]
    end = min(map(len, sequences))
    for other in sequences[1:]:
        for i in range(end):
            if first[i] != other[i]:
                end = i
                break
    return first[:end]


def unique_prompt_tokens(sequences: list[list[int]]) -> int:
    """Distinct token-tree edges across all sequences (hf_server.unique_prompt_tokens)."""
    total = 0
    previous: list[int] = []
    for sequence in sorted(sequences):
        shared = 0
        for left, right in zip(previous, sequence, strict=False):  # deliberately unequal lengths
            if left != right:
                break
            shared += 1
        total += len(sequence) - shared
        previous = sequence
    return total


def build_messages(
    plan: PromptPlan, request: ClassifierRequest, question: ScoringQuestion
) -> list[dict]:
    """Text-only, state-based message assembly, matching hf_server.PromptCompiler.compile."""
    if request.state is None:
        raise ValueError("llamacpp_backend supports state-based requests only")
    system = plan.system_prompt_prefix + plan.prefix_instruction
    content = plan.suffix_instruction + question.instruction
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"State:\n{canonical(request.state)}\n\n" + content},
    ]


def _apply_boundary(prompt_text: str, profile: ModelProfile) -> tuple[str, str]:
    if prompt_text.endswith(profile.expected_boundary):
        return prompt_text, "asis"
    if profile.patchable_boundary:
        old, new = profile.patchable_boundary
        if prompt_text.endswith(old):
            return prompt_text[: -len(old)] + new, "patched"
    raise ValueError(
        f"Unexpected assistant boundary for profile {profile.name!r}: {prompt_text[-60:]!r}"
    )


@dataclass(frozen=True)
class Branch:
    branch_id: str
    question_id: str
    token_ids: list[int]
    label_ids: dict[str, int]  # output_label -> token id, at the rendered boundary
    prompt_text: str


@dataclass
class CompiledRequest:
    plan: PromptPlan
    branches: list[Branch]
    thinking_block: str  # "asis" | "patched", diagnostic


class LlamaCppCompiler:
    def __init__(
        self, client: LlamaServerClient, profile: ModelProfile, *, max_tokens: int | None = None
    ):
        self.client = client
        self.profile = profile
        self.max_tokens = max_tokens

    def compile(self, request: ClassifierRequest | dict) -> CompiledRequest:
        if not isinstance(request, ClassifierRequest):
            request = ClassifierRequest.model_validate(request)
        if request.tools or request.mm_processor_kwargs or request.media_io_kwargs:
            raise ValueError("llamacpp_backend does not support tools or media options")
        if request.messages is not None:
            raise ValueError("llamacpp_backend supports state-based requests only")

        plan = prepare_prompt(request)
        branches: list[Branch] = []
        thinking_block = "asis"
        for question in plan.questions:
            messages = build_messages(plan, request, question)
            rendered = self.client.apply_template(messages, self.profile.chat_template_kwargs)
            rendered, mode = _apply_boundary(rendered, self.profile)
            if mode == "patched":
                thinking_block = "patched"
            text = rendered + self.profile.assistant_prefill + question.answer_prefix

            ids = self.client.tokenize(text, add_special=False, parse_special=True)
            if not ids or (self.max_tokens and len(ids) > self.max_tokens):
                raise ValueError(f"Branch for {question.question_id!r} has {len(ids)} tokens")

            label_ids: dict[str, int] = {}
            for label in question.output_labels:
                extended = self.client.tokenize(text + label, add_special=False, parse_special=True)
                if len(extended) != len(ids) + 1 or extended[: len(ids)] != ids:
                    raise ValueError(f"Answer label {label!r} is not single-token stable")
                label_ids[label] = extended[-1]
            if len(set(label_ids.values())) != len(label_ids):
                raise ValueError("Output labels must map to distinct token IDs")

            branches.append(Branch(question.branch_id, question.question_id, ids, label_ids, text))
        return CompiledRequest(plan, branches, thinking_block)


def _completion_body(branch: Branch, *, n_probs: int, id_slot: int) -> dict:
    return {
        "prompt": branch.token_ids,
        "n_predict": 1,
        "n_probs": n_probs,
        "post_sampling_probs": False,
        "cache_prompt": True,
        "id_slot": id_slot,
        "temperature": 0,
        "stream": False,
    }


def _label_logprobs(
    response: dict, label_ids: dict[str, int], n_probs: int
) -> tuple[dict[str, float], list[str]]:
    probs = response.get("completion_probabilities") or []
    top = probs[0].get("top_logprobs", []) if probs else []
    by_id = {entry["id"]: entry["logprob"] for entry in top}
    floor = min(by_id.values()) - 1.0 if by_id else -100.0
    out: dict[str, float] = {}
    missing: list[str] = []
    for label, token_id in label_ids.items():
        if token_id in by_id:
            out[label] = by_id[token_id]
        else:
            out[label] = floor
            missing.append(label)
    return out, missing


class LlamaCppBackend:
    """Implements ``isc.backends.RawJevClient`` (``classify(request) -> envelope``)."""

    def __init__(
        self,
        client: LlamaServerClient,
        profile: ModelProfile,
        *,
        n_probs: int = 64,
        parallel: int = 1,
        id_slot: int = -1,
    ) -> None:
        self.client = client
        self.profile = profile
        self.n_probs = n_probs
        self.parallel = parallel
        self.id_slot = id_slot
        self.compiler = LlamaCppCompiler(client, profile)

    def _score_one(self, branch: Branch) -> tuple[str, dict[str, float], list[str], dict]:
        n_probs = max(self.n_probs, len(branch.label_ids) + 32)
        body = _completion_body(branch, n_probs=n_probs, id_slot=self.id_slot)
        response = self.client.completion(body)
        values, missing = _label_logprobs(response, branch.label_ids, n_probs)
        if missing:
            winner = max(values, key=values.get)
            if winner in missing:
                raise ValueError(
                    f"Branch {branch.branch_id!r} ({branch.question_id!r}): label "
                    f"{winner!r} fell outside the top {n_probs} logprobs and would have won "
                    "on its floor value; raise n_probs or investigate the prompt"
                )
        return branch.branch_id, values, missing, response

    def score(self, compiled: CompiledRequest) -> tuple[dict[str, dict[str, float]], dict]:
        logits: dict[str, dict[str, float]] = {}
        prompt_n_total = 0
        cached_total = 0
        missing_labels: dict[str, list[str]] = {}
        id_slots_used: set[int] = set()

        if self.parallel > 1 and len(compiled.branches) > 1:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=self.parallel) as pool:
                results = list(pool.map(self._score_one, compiled.branches))
        else:
            results = [self._score_one(b) for b in compiled.branches]

        for branch_id, values, missing, response in results:
            if missing:
                missing_labels[branch_id] = missing
            logits[branch_id] = values
            timings = response.get("timings", {})
            prompt_n_total += timings.get("prompt_n", 0)
            cached_total += response.get("tokens_cached", 0)
            if "id_slot" in response:
                id_slots_used.add(response["id_slot"])
        metrics = {
            "engine_calls": len(compiled.branches),
            "prompt_n_total": prompt_n_total,
            "cached_tokens_total": cached_total,
            "prefix_tokens": len(common_prefix([b.token_ids for b in compiled.branches]))
            if compiled.branches
            else 0,
            "id_slots_used": sorted(id_slots_used),
            "thinking_block": compiled.thinking_block,
            "missing_labels": missing_labels,
        }
        return logits, metrics

    def classify(self, request: ClassifierRequest | dict, *, advanced: bool = False) -> dict:
        compiled = self.compiler.compile(request)
        logits, metrics = self.score(compiled)
        input_tokens = unique_prompt_tokens([b.token_ids for b in compiled.branches])
        response = build_response(
            compiled.plan, logits, input_tokens=input_tokens, advanced=advanced
        )
        response["metrics"] = metrics
        return response
