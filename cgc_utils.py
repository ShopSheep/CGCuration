"""Shared I/O and parsing for extraction and evaluation scripts.

Imports do not load credentials, create clients, or make network requests.
"""

import atexit
import csv
import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "COSMIC_CGC_SAMPLE.json"
_client = None
_client_lock = threading.Lock()
_alias_lock = threading.Lock()


@lru_cache(maxsize=1)
def load_config():
    load_dotenv(ROOT / ".env")


def worker_count():
    load_config()
    count = int(os.getenv("CGC_WORKERS", "4"))
    if count < 1:
        raise ValueError("CGC_WORKERS must be positive")
    return count


def parallel_map(function, items):
    """Run I/O tasks with bounded concurrency, preserving input order."""
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(worker_count(), len(items))) as pool:
        return list(pool.map(function, items))


def get_client():
    """Share a connection pool across workers; bound request time and retries."""
    global _client
    with _client_lock:
        if _client is None:
            load_config()
            _client = OpenAI(timeout=60.0, max_retries=2)
            atexit.register(_client.close)
        return _client


def get_model(default="gpt-4-0125-preview"):
    load_config()
    return os.getenv("OPENAI_MODEL") or default


def response_text(response):
    if not response.choices:
        raise ValueError("The model returned no choices")
    choice = response.choices[0]
    if choice.finish_reason != "stop":
        raise ValueError(f"Incomplete model response: {choice.finish_reason}")
    content = choice.message.content
    if not isinstance(content, str):
        raise ValueError("The model returned no text")
    return content.strip()


def complete(messages, *, model="gpt-4-0125-preview"):
    """Use the experiment's sampling settings and reject incomplete responses."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    response = get_client().chat.completions.create(
        model=get_model(model),
        messages=messages,
        temperature=0,
        max_tokens=4095,
        top_p=0,
        frequency_penalty=0,
        presence_penalty=0,
    )
    return response_text(response)


def split_names(text):
    """Handle both comma and newline delimited names without duplicates."""
    names = (name.strip().strip("\"'") for name in re.split(r"[,\n]+", text))
    return list(dict.fromkeys(name for name in names if name))


def parse_boolean(text, true="yes", false="no"):
    value = text.strip("\"'. \t\r\n").casefold()
    if value == true.casefold():
        return True
    if value == false.casefold():
        return False
    raise ValueError(f"Expected {true!r} or {false!r}, got {text!r}")


def read_records(path):
    with open(path, encoding="utf-8") as source:
        records = json.load(source)
    if not isinstance(records, list) or any(
        not isinstance(row, dict) for row in records
    ):
        raise ValueError("Expected a JSON array of records")
    return records


def select_records(path, limit, step=1, *, hallmark=None, field=None):
    limit, step = int(limit), int(step)
    if limit < 0 or step < 1:
        raise ValueError("limit must be nonnegative and step must be positive")
    records = read_records(path)
    if hallmark is not None:
        records = [
            r
            for r in records
            if r.get("HALLMARK", "").casefold() == hallmark.casefold()
        ]
    if field:
        records = [r for r in records if r.get(field)]
    return records[::step][:limit]


@lru_cache(maxsize=4)
def _load_alias_index(path):
    approved = set()
    candidates = {}
    with open(path, newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            symbol = row["Approved symbol"].strip()
            approved.add(symbol)
            for column in ("Alias symbol", "Previous symbol"):
                alias = row[column].strip()
                if alias:
                    candidates.setdefault(alias, set()).add(symbol)
    # Ambiguous aliases are kept unchanged instead of choosing an arbitrary gene.
    index = {
        alias: next(iter(symbols))
        for alias, symbols in candidates.items()
        if len(symbols) == 1
    }
    index.update({symbol: symbol for symbol in approved})
    return index


def _alias_index(path):
    # lru_cache alone can build the same index concurrently on initial misses.
    with _alias_lock:
        return _load_alias_index(path)


def aliasCheck(gene_name):
    load_config()
    gene_name = gene_name.strip()
    path = os.getenv("CGC_GENE_ALIASES", str(ROOT / "geneAlias.csv"))
    return _alias_index(path).get(gene_name, gene_name)


def write_records(path, records):
    """Replace output atomically so a failed write preserves the previous run."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as target:
            temporary = Path(target.name)
            json.dump(records, target, indent=2)
            target.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class AbstractError(RuntimeError):
    """A PMID could not supply usable evidence for extraction."""


def check_abstract(pubmed_id, *, attempts=3):
    pmid = str(pubmed_id).strip()
    if not pmid.isascii() or not pmid.isdecimal() or int(pmid) < 1:
        raise ValueError(f"Invalid PMID: {pubmed_id!r}")
    if attempts < 1:
        raise ValueError("attempts must be positive")
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    for attempt in range(attempts):
        try:
            with requests.get(url, timeout=(5, 20)) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                elif response.status_code != 200:
                    raise AbstractError(f"PMID {pmid}: HTTP {response.status_code}")
                soup = BeautifulSoup(response.content, "html.parser")
                abstract = soup.find("div", class_="abstract-content")
                if abstract is None:
                    raise AbstractError(f"PMID {pmid}: no abstract content")
                text = abstract.get_text(" ", strip=True)
                if not text:
                    raise AbstractError(f"PMID {pmid}: empty abstract")
                return pubmed_id, text
        except (
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,
            requests.HTTPError,
        ) as error:
            if attempt == attempts - 1:
                raise AbstractError(
                    f"PMID {pmid}: retrieval failed after {attempts} attempts"
                ) from error
        time.sleep(min(2**attempt, 8))


def process_abstracts(pubmed_ids):
    """Fetch each distinct PMID once, then restore row order and duplicates."""
    pubmed_ids = list(pubmed_ids)
    unique = list(dict.fromkeys(str(pmid).strip() for pmid in pubmed_ids))
    fetched = dict(parallel_map(check_abstract, unique))
    return [(pmid, fetched[str(pmid).strip()]) for pmid in pubmed_ids]


def aligned_data(hallmarks, abstracts):
    if len(hallmarks) != len(abstracts):
        raise ValueError("Hallmarks and abstracts have different lengths")
    return [(hallmark, abstract[1]) for hallmark, abstract in zip(hallmarks, abstracts)]


def partition_results(pubmed_ids, hallmarks, expected, actual):
    if len({len(pubmed_ids), len(hallmarks), len(expected), len(actual)}) != 1:
        raise ValueError("Evaluation inputs have different lengths")
    errors, good = [], []
    for pmid, hallmark, answer, result in zip(pubmed_ids, hallmarks, expected, actual):
        item = (pmid, hallmark, answer, result)
        (
            good if answer.strip().casefold() == result.strip().casefold() else errors
        ).append(item)
    return errors, good


def promote_matches(errors, good, judge):
    """Partition in linear time without repeatedly removing list elements."""
    matches = parallel_map(judge, errors)
    remaining = []
    for item, match in zip(errors, matches):
        (good if match is not None else remaining).append(item)
    errors[:] = remaining


def run_field_evaluation(extract, field, *, judge=None):
    """Command-line workflow shared by cell type, cell line, and impact checks."""
    import argparse

    parser = argparse.ArgumentParser(description=f"Evaluate {field} extraction")
    parser.add_argument("--input", type=Path, default=DATA_PATH)
    parser.add_argument("--hallmark", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--step", type=int, default=1)
    args = parser.parse_args()
    rows = select_records(
        args.input, args.limit, args.step, hallmark=args.hallmark, field=field
    )
    ids = [r["PUBMED_PMID"] for r in rows]
    hallmarks = [r["HALLMARK"] for r in rows]
    expected = [r[field] for r in rows]
    abstracts = process_abstracts(ids)
    if field == "IMPACT":
        inputs = [
            (r["HALLMARK"], abstract[1], r["GENE_NAME"], r.get("CELL_TYPE", ""))
            for r, abstract in zip(rows, abstracts)
        ]
    else:
        inputs = aligned_data(hallmarks, abstracts)
    actual = parallel_map(extract, inputs)
    errors, good = partition_results(ids, hallmarks, expected, actual)
    if judge:
        promote_matches(errors, good, judge)
    print(f"Correct: {len(good)}/{len(rows)}")
    print(f"Mismatches: {errors}")
    if not rows:
        print("No matching records; accuracy is undefined.")
