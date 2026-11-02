"""Evaluate CELL_LINE extraction against CGC reference rows."""

import sys
from pathlib import Path

# Keep the original standalone script paths runnable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cgc_utils import (  # noqa: E402
    DATA_PATH,
    aligned_data,
    complete,
    parallel_map,
    parse_boolean,
    promote_matches,
    run_field_evaluation,
    select_records,
)

json_file_path = DATA_PATH


def check_line(data):
    hallmark, abstract = data
    if hallmark.lower() in [
        "function summary",
        "role in cancer",
        "fusion partner",
        "mouse model",
        "types of alteration in cancer",
        "clinical impact",
    ]:
        line = ""
    else:
        ctd = "I will provide you with an abstract from PubMed. Your job is to extract cell lines: specific types of cells that are derived from a particular tissue or organism and can be grown and maintained in a laboratory setting. If multiple cell lines are applicable, return a comma separated list of those. If the abstract mentions no cell lines, return an empty string. Do not guess cell lines that are not supported by the abstract. Only return your answer. No descriptions required."
        line = complete(
            [{"role": "user", "content": ctd + "\n\n" + abstract}],
            model="gpt-4-0125-preview",
        )
    return line


def process_item(item):
    PMID, hallmark, answer, extracted_result = item
    if extracted_result != answer and extracted_result != "":
        result = complete(
            [
                {
                    "role": "user",
                    "content": f"Here is the first list of cells: {extracted_result}\n\nHere is the second list of cells: {answer.lower().replace(' and ', ', ')}\n\nUsing your medical knowledge, please determine if any of the object(s) in the first list is equal to, is a subset of, or (broadly) includes the second list. Respond 'Yes', if it does, and 'No' if it does not. The objects in the first and second list may be in a different format such as uppercase/lowercase and spacing. Be careful with those.",
                }
            ],
            model="gpt-4-0125-preview",
        )
        if parse_boolean(result):
            return (PMID, hallmark, answer, extracted_result)
    return None


# Compatibility helpers for callers of the original scripts.
hallmarkt = ""


def _select(path, numData, step, hallmark=None):
    return select_records(
        path,
        numData,
        step,
        hallmark=hallmark if hallmark is not None else hallmarkt,
        field="CELL_LINE",
    )


def extract_pubmed_ids(json_file_path, numData, step, hallmark=None):
    rows = _select(json_file_path, numData, step, hallmark)
    return ([r["PUBMED_PMID"] for r in rows], [r["HALLMARK"] for r in rows])


def extract_impactlist(json_file_path, numData, step, hallmark=None):
    return [r["CELL_LINE"] for r in _select(json_file_path, numData, step, hallmark)]


def prepare_data_for_multiprocessing(hallmarks, abstracts):
    return aligned_data(hallmarks, abstracts)


def process_data_with_multiprocessing(combined_data):
    return parallel_map(check_line, combined_data)


def list_check(errorlist, goodlist):
    promote_matches(errorlist, goodlist, process_item)


if __name__ == "__main__":
    run_field_evaluation(check_line, "CELL_LINE", judge=process_item)
