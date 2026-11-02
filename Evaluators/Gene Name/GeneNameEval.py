"""Evaluate gene extraction with local HGNC alias normalization."""

import sys
from pathlib import Path

# Keep the original standalone script paths runnable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse

from cgc_utils import (  # noqa: E402
    DATA_PATH,
    aliasCheck,
    parallel_map,
    process_abstracts,
    select_records,
    split_names,
)
from CGCExtract import check_gene  # noqa: E402


def extract_infos(json_file_path, numData, evn):
    rows = select_records(json_file_path, numData, evn)
    return [r["PUBMED_PMID"] for r in rows], [r["GENE_NAME"] for r in rows]


def process_genes(abstracts):
    return [", ".join(result[1:]) for result in parallel_map(check_gene, abstracts)]


def check_alias(gene_names):
    return [
        list(dict.fromkeys(aliasCheck(name) for name in split_names(text)))
        for text in gene_names
    ]


def compare_genes(expected_genes, actual_genes, pubmed_ids=None):
    if len(expected_genes) != len(actual_genes):
        raise ValueError("Expected and actual genes have different lengths")
    if pubmed_ids is not None and len(pubmed_ids) != len(expected_genes):
        raise ValueError("PMIDs and genes have different lengths")
    return [
        (
            f"index: {index}",
            pubmed_ids[index] if pubmed_ids is not None else index,
            expected,
            actual,
        )
        for index, (expected, actual) in enumerate(zip(expected_genes, actual_genes))
        if not expected or not set(expected).issubset(actual)
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATH)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--step", type=int, default=10)
    args = parser.parse_args()
    ids, expected = extract_infos(args.input, args.limit, args.step)
    actual = check_alias(process_genes(process_abstracts(ids)))
    differences = compare_genes(check_alias(expected), actual, ids)
    print(f"Correct: {len(ids) - len(differences)}/{len(ids)}")
    print(f"Mismatches: {differences}")
    if not ids:
        print("No matching records; accuracy is undefined.")


if __name__ == "__main__":
    main()
