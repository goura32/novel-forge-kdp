from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import print

from .llm import LLMClientError, OllamaOpenAIClient
from .workflow import NovelForge

app = typer.Typer(help="Local-LLM assisted autonomous novel planning, drafting, reviewing, and revision.")


def forge(workspace: Path, ollama_url: str, model: str, timeout: int) -> NovelForge:
    llm = OllamaOpenAIClient(base_url=ollama_url, model=model, timeout_seconds=timeout)
    return NovelForge(workspace=workspace, llm=llm)


@app.command()
def plan_series(
    keyword: Annotated[str, typer.Argument(help="企画の起点キーワード")],
    workspace: Annotated[Path, typer.Option(help="シリーズ作業フォルダの親")]=Path("workspace"),
    ollama_url: str = "http://ws1.local:11434",
    model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
    timeout: int = 3600,
) -> None:
    state = forge(workspace, ollama_url, model, timeout).plan_series(keyword)
    print(f"[green]created[/green] {workspace / state.series.slug}")


@app.command()
def write_volume(
    slug: Annotated[str, typer.Argument(help="シリーズslug")],
    workspace: Path = Path("workspace"),
    volume: int | None = None,
    ollama_url: str = "http://ws1.local:11434",
    model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
    timeout: int = 3600,
    max_scenes: Annotated[int | None, typer.Option(help="検証・スモーク用に処理するシーン数を制限。通常運用では未指定")]=None,
) -> None:
    state = forge(workspace, ollama_url, model, timeout).write_volume(slug, volume, max_scenes=max_scenes)
    print(f"[green]volume complete[/green] {state.series.slug} volume={volume or state.current_volume}")


@app.command()
def status(slug: str, workspace: Path = Path("workspace")) -> None:
    state = NovelForge(workspace=workspace).status(slug)
    print(state.model_dump_json(indent=2))


@app.command()
def probe_model(
    ollama_url: str = "http://ws1.local:11434",
    model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
    timeout: int = 3600,
) -> None:
    client = OllamaOpenAIClient(base_url=ollama_url, model=model, timeout_seconds=timeout, log_dir=Path("probe_logs"))
    schema = {"type": "object", "required": ["ok", "note"], "properties": {"ok": {"type": "boolean"}, "note": {"type": "string"}}}
    try:
        result = client.complete_json(task="probe", messages=[{"role": "system", "content": "Return only JSON."}, {"role": "user", "content": "JSONで {ok: true, note: 日本語の短文} を返して。"}], schema=schema, max_tokens=1024)
    except LLMClientError as exc:
        raise typer.Exit(f"probe failed: {exc}") from exc
    print(result)
