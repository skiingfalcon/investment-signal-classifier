"""``isc`` command line: build the eval set, run the cascade, and report on it."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from isc import facts as facts_module
from isc import pipeline, questions, report
from isc import rules as rules_module
from isc import state as state_module
from isc.backends import JevBackend, MockBackend
from isc.config import Settings, get_settings
from isc.jev.llama_server import LlamaServerClient
from isc.jev.llamacpp_backend import LlamaCppBackend
from isc.jev.model_profiles import resolve_profile
from isc.jev.typesafe_backend import MissingKeyError, TypesafeJevClient
from isc.verify import GenerativeArbiter

app = typer.Typer(add_completion=False)
jev_app = typer.Typer(add_completion=False)
app.add_typer(jev_app, name="jev")
console = Console()


def _default_tickers(settings: Settings) -> list[str]:
    if not settings.sec_data_dir.is_dir():
        return []
    return sorted(
        p.name for p in settings.sec_data_dir.iterdir() if (p / "companyfacts.json").is_file()
    )


def _model_run_dirs(settings: Settings) -> list[Path]:
    base = settings.sec_state_dir
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob("*/*-extract-full") if p.is_dir())


def _collect_factsets(
    settings: Settings, sources: list[str], tickers: list[str] | None, years: int
) -> list:
    out = []
    tickers_set = set(tickers) if tickers else None
    for src in sources:
        if src == "xbrl":
            for ticker in tickers_set or _default_tickers(settings):
                facts = facts_module.load_companyfacts(settings.sec_data_dir, ticker)
                out += facts_module.xbrl_factsets(facts, ticker, years=years)
        elif src == "model:all":
            for run_dir in _model_run_dirs(settings):
                run_name = f"{run_dir.parent.name}/{run_dir.name}"
                fsets = facts_module.model_factsets(
                    run_dir / "results.jsonl", settings.sec_data_dir, run_name=run_name
                )
                out += [f for f in fsets if not tickers_set or f.ticker in tickers_set]
        elif src.startswith("model:"):
            run_name = src[len("model:") :]
            run_dir = settings.sec_state_dir / run_name
            fsets = facts_module.model_factsets(
                run_dir / "results.jsonl", settings.sec_data_dir, run_name=run_name
            )
            out += [f for f in fsets if not tickers_set or f.ticker in tickers_set]
        else:
            raise typer.BadParameter(
                f"Unknown --source {src!r} (use 'xbrl', 'model:<run>', or 'model:all')"
            )
    return out


@app.command()
def facts(
    source: list[str] = typer.Option(
        ["xbrl"], "--source", help="'xbrl', 'model:<run>', or 'model:all'"
    ),
    years: int = typer.Option(5, help="XBRL fiscal years per ticker"),
    tickers: str | None = typer.Option(None, help="Comma-separated ticker filter"),
    out: Path = typer.Option(Path("data/facts.jsonl")),
) -> None:
    """Build the FactSet eval set and write it to a jsonl file."""
    settings = get_settings()
    ticker_list = [t.strip().upper() for t in tickers.split(",")] if tickers else None
    factsets = _collect_factsets(settings, source, ticker_list, years)
    facts_module.write_facts(out, factsets)

    table = Table(title=f"{len(factsets)} FactSets -> {out}")
    for col in ("ticker", "fiscal_year_end", "source", "missing_current", "overall_signal"):
        table.add_column(col)
    for fs in factsets:
        labels = rules_module.label(fs)
        table.add_row(
            fs.ticker,
            fs.fiscal_year_end,
            fs.source,
            str(len(fs.quality.missing_current)),
            str(labels["overall_signal"]),
        )
    console.print(table)


@app.command()
def show(
    ticker: str,
    fy: str | None = typer.Option(
        None, help="Fiscal year end (YYYY-MM-DD); defaults to the latest"
    ),
    state_mode: str = typer.Option("derived"),
) -> None:
    """Print the rendered state and rule-engine labels for one company-year."""
    settings = get_settings()
    company_facts = facts_module.load_companyfacts(settings.sec_data_dir, ticker.upper())
    from isc import xbrl

    ends = xbrl.fiscal_year_ends(company_facts)
    fy_end = fy or (ends[0] if ends else None)
    if fy_end is None:
        raise typer.BadParameter(f"No 10-K fiscal years found for {ticker}")
    prior_end = next((e for e in ends if e < fy_end), None)
    fs = facts_module.xbrl_factset(company_facts, ticker.upper(), fy_end, prior_end)
    console.print_json(json.dumps(state_module.render(fs, state_mode)))
    console.print_json(json.dumps(rules_module.label(fs)))


@app.command(name="questions")
def questions_cmd() -> None:
    """Print the Simple Jev question set as sent in a request body."""
    console.print_json(json.dumps(questions.questions_json()))


def _build_backend(
    settings: Settings,
    backend_name: str,
    *,
    model: str | None,
    allow_experimental: bool,
    n_probs: int,
    parallel: int,
    id_slot: int,
):
    if backend_name == "mock":
        return MockBackend()
    if backend_name == "llamacpp":
        jev_model = model or settings.jev_model
        client = LlamaServerClient(settings.jev_base_url, timeout_s=settings.timeout_s)
        profile = resolve_profile(jev_model, allow_experimental=allow_experimental)
        raw = LlamaCppBackend(client, profile, n_probs=n_probs, parallel=parallel, id_slot=id_slot)
        return JevBackend(raw, jev_model, name="llamacpp")
    if backend_name == "typesafe":
        try:
            client = TypesafeJevClient.from_settings(settings)
        except MissingKeyError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if model:
            client.model = model  # e.g. pin a dated build echoed back in a prior run's run.json
        return JevBackend(client, client.model, name="typesafe")
    raise typer.BadParameter(f"Unknown --backend {backend_name!r}")


def _build_arbiter(settings: Settings, *, gen_model: str | None) -> GenerativeArbiter:
    if settings.gen_provider == "openai" and not settings.openai_api_key:
        raise typer.BadParameter(
            "OPENAI_API_KEY is not set. Export it, or set ISC_GEN_PROVIDER=local plus "
            "ISC_GEN_BASE_URL to point the arbiter at a second local llama-server instead."
        )
    return GenerativeArbiter(
        settings.gen_base_url,
        gen_model or settings.gen_model,
        provider=settings.gen_provider,
        api_key=settings.openai_api_key,
        reasoning_effort=settings.gen_reasoning_effort,
        max_tokens=settings.gen_max_tokens,
    )


@app.command(name="run")
def run_cmd(
    backend: str = typer.Option(
        "mock", help="'llamacpp' (local qwen), 'typesafe' (hosted Jev), or 'mock'"
    ),
    facts_path: Path = typer.Option(Path("data/facts.jsonl")),
    source_filter: str | None = typer.Option(
        None, "--source-filter", help="Substring match on FactSet.source"
    ),
    state_mode: str = typer.Option("derived"),
    verify: bool = typer.Option(True),
    escalate: bool = typer.Option(True),
    limit: int | None = typer.Option(None),
    parallel: int = typer.Option(1),
    n_probs: int = typer.Option(64),
    id_slot: int = typer.Option(-1, help="Pin every completion to one llama-server slot"),
    model: str | None = typer.Option(
        None, help="llamacpp: overrides ISC_JEV_MODEL; typesafe: pins a dated build id"
    ),
    gen_model: str | None = typer.Option(None, help="Overrides ISC_GEN_MODEL"),
    allow_experimental: bool = typer.Option(False),
) -> None:
    """Run the cascade over a facts.jsonl and write a run directory."""
    settings = get_settings()
    factsets = facts_module.read_facts(facts_path)
    if source_filter:
        factsets = [f for f in factsets if source_filter in f.source]

    decision_backend = _build_backend(
        settings,
        backend,
        model=model,
        allow_experimental=allow_experimental,
        n_probs=n_probs,
        parallel=parallel,
        id_slot=id_slot,
    )
    arbiter = None
    if escalate and backend != "mock":
        arbiter = _build_arbiter(settings, gen_model=gen_model)

    run_dir = pipeline.run(
        settings,
        backend=decision_backend,
        arbiter=arbiter,
        factsets=factsets,
        state_mode=state_mode,
        verify=verify,
        escalate=escalate,
        limit=limit,
    )
    console.print(f"[green]wrote {run_dir}[/green]")
    console.print((run_dir / "report.md").read_text())


@app.command(name="report")
def report_cmd(run_dir: Path, markdown: bool = typer.Option(False)) -> None:
    run_meta = json.loads((run_dir / "run.json").read_text())
    rows = [
        json.loads(line)
        for line in (run_dir / "results.jsonl").read_text().splitlines()
        if line.strip()
    ]
    text = report.render_markdown(run_meta, rows)
    if markdown:
        print(text)
    else:
        console.print(text)


@app.command(name="compare")
def compare_cmd(run_dirs: list[Path], markdown: bool = typer.Option(False)) -> None:
    runs = []
    for run_dir in run_dirs:
        run_meta = json.loads((run_dir / "run.json").read_text())
        run_meta["run_id"] = run_dir.name
        rows = [
            json.loads(line)
            for line in (run_dir / "results.jsonl").read_text().splitlines()
            if line.strip()
        ]
        runs.append((run_meta, rows))
    text = report.render_compare(runs)
    if markdown:
        print(text)
    else:
        console.print(text)


@jev_app.command(name="classify")
def jev_classify(
    request_path: Path,
    model: str = typer.Option("qwen3.8-27b"),
    base_url: str | None = typer.Option(None),
    advanced: bool = typer.Option(False),
    allow_experimental: bool = typer.Option(False),
    n_probs: int = typer.Option(64),
    id_slot: int = typer.Option(-1, help="Pin every completion to one llama-server slot"),
) -> None:
    """Send a raw ClassifierRequest JSON file straight to the llama.cpp JEV backend."""
    settings = get_settings()
    client = LlamaServerClient(base_url or settings.jev_base_url, timeout_s=settings.timeout_s)
    profile = resolve_profile(model, allow_experimental=allow_experimental)
    backend = LlamaCppBackend(client, profile, n_probs=n_probs, id_slot=id_slot)
    request = json.loads(request_path.read_text())
    request.setdefault("model", model)
    response = backend.classify(request, advanced=advanced)
    console.print_json(json.dumps(response))


if __name__ == "__main__":
    app()
