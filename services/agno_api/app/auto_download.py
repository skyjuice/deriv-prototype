from __future__ import annotations

import asyncio
import inspect
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DOWNLOADS_PATH = os.getenv("AUTO_DOWNLOADS_PATH", os.path.expanduser("~/Downloads/tmp"))


def _latest_download_path() -> str | None:
    path = Path(DOWNLOADS_PATH)
    if not path.exists():
        return None

    files = [item for item in path.iterdir() if item.is_file()]
    if not files:
        return None

    latest = max(files, key=lambda item: item.stat().st_mtime)
    return str(latest)


async def run_download(task: str | None = None) -> str | None:
    try:
        from browser_use import Agent, Browser
        from browser_use.llm import ChatOpenAI
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "browser_use is not installed. Install required libs in agno_api env: pip install browser-use"
        ) from exc

    Path(DOWNLOADS_PATH).mkdir(parents=True, exist_ok=True)

    model = os.getenv("AUTO_DOWNLOAD_MODEL") or os.getenv("OPENROUTER_MODEL") or "gpt-5-mini"
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key and openrouter_key:
        llm = ChatOpenAI(
            model=model,
            api_key=openrouter_key,
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        )
    else:
        llm = ChatOpenAI(model=model)
    browser = Browser(downloads_path=DOWNLOADS_PATH)

    default_task = (
        'Go to "https://payflow-p2p.vercel.app/" '
        "Find csv document and download it. "
        "Once files are downloaded, stop the browser and return the path to the downloaded file."
    )

    agent = Agent(
        task=task or default_task,
        llm=llm,
        browser=browser,
    )

    try:
        await agent.run(max_steps=2)
    finally:
        close_fn = getattr(browser, "close", None)
        if callable(close_fn):
            maybe_result = close_fn()
            if inspect.isawaitable(maybe_result):
                await maybe_result

    return _latest_download_path()


def download_file(task: str | None = None) -> str | None:
    """Sync wrapper that downloads a file and returns the local path."""
    return asyncio.run(run_download(task=task))


if __name__ == "__main__":
    path = download_file()
    print("Downloaded file:", path)
