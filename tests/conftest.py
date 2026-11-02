import importlib.util
from pathlib import Path

import httpx
import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """A missed mock must fail rather than contact PubMed or a paid API."""

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in the test suite")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", blocked)
    monkeypatch.setattr(httpx.Client, "send", blocked)
    monkeypatch.setenv("CGC_WORKERS", "2")
    monkeypatch.delenv("CGC_GENE_ALIASES", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)


@pytest.fixture
def evaluator():
    def load(folder, filename):
        spec = importlib.util.spec_from_file_location(
            filename.removesuffix(".py"), ROOT / "Evaluators" / folder / filename
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load
