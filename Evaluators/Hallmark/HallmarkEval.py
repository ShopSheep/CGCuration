"""Measure positive-label consistency for a selected reference hallmark."""

import sys
from pathlib import Path

# Keep the original standalone script paths runnable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
from functools import partial

from cgc_utils import (  # noqa: E402
    DATA_PATH,
    complete,
    parallel_map,
    parse_boolean,
    process_abstracts,
    select_records,
)


def extract_pubmed_ids(json_file_path, hallmark_name, numData, evn):
    return [
        r["PUBMED_PMID"]
        for r in select_records(json_file_path, numData, evn, hallmark=hallmark_name)
    ]


def check_hallmark(abstract, target):
    pmid, text = abstract
    question = f"I will provide you an abstract from PubMed. Your job is to check if the abstract is related to '{target}'. Think step by step, although you do not have to explain to me your reasoning steps. If the abstract is related, respond with 'yes', and if not, 'no'. Do not tell me anything more than that."
    result = complete(
        [{"role": "user", "content": question + "\n\n" + text}],
        model="gpt-4-1106-preview",
    )
    return "yes" if parse_boolean(result) else "no"


def extract_hallmark(abstract_list, target):
    return parallel_map(partial(check_hallmark, target=target), abstract_list)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATH)
    parser.add_argument("--hallmark", required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--step", type=int, default=1)
    args = parser.parse_args()
    ids = extract_pubmed_ids(args.input, args.hallmark, args.limit, args.step)
    responses = extract_hallmark(process_abstracts(ids), args.hallmark)
    mismatches = [pmid for pmid, response in zip(ids, responses) if response == "no"]
    print(f"Positive-label agreement: {len(ids) - len(mismatches)}/{len(ids)}")
    print(f"Mismatched PMIDs: {mismatches}")
    if not ids:
        print("No matching records; agreement is undefined.")


if __name__ == "__main__":
    main()
