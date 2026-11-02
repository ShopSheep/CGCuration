"""Evaluate CELL_TYPE extraction against CGC reference rows."""

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
    if hallmark.lower() == "function summary":
        return ""
    else:
        ctd = "I will provide you with an abstract from PubMed. Your job is to extract cancer cell type discussed in relation to the given abstract: the specific types of cells or tissues that are associated with a particular disease or condition. Think step-by-step and explain your reasoning process. Look for two best cell types. If you are sure that only one cell type is applicable, only return that cell type."
        result1 = complete(
            [{"role": "user", "content": ctd + "\n\n" + abstract}],
            model="gpt-4-0125-preview",
        )
        result2 = complete(
            [
                {
                    "role": "user",
                    "content": f"A GPT responded: {result1} for a question asking to identify cell types mentioned in PubMed abstract. Extract comma separated list of cell types from GPT response. No descriptions required, extract only the cell types.",
                }
            ],
            model="gpt-4-0125-preview",
        )
        return result2


def process_item(item):
    PMID, hallmark, answer, extracted_result = item
    if extracted_result != answer and extracted_result != "":
        response = complete(
            [
                {
                    "role": "user",
                    "content": f"Using your medical knowledge and reasoning skills, check if the any of the cells in list: {extracted_result.replace(' cells', '')} are equal to, are subsets of, or (broadly) includes the cells in list : {answer.lower().replace(' and ', ', ')}, or vice versa. There could be only one element in the list, if so, check if the smaller list is a subset of the bigger list. If both lists have only one element, check if they are referring to same cell type. The two lists do not have to be exactly equal, but at least one element from both lists should be closely related. \n\nRespond 'Yes', if it does, and 'No' if it does not. The lists of cell types that are being compared may be in a different format such as uppercase/lowercase and spacing. Be careful with those.",
                }
            ],
            model="gpt-4-0125-preview",
        )
        result = response.lower()
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
        field="CELL_TYPE",
    )


def extract_pubmed_ids(json_file_path, numData, step, hallmark=None):
    rows = _select(json_file_path, numData, step, hallmark)
    return ([r["PUBMED_PMID"] for r in rows], [r["HALLMARK"] for r in rows])


def extract_impactlist(json_file_path, numData, step, hallmark=None):
    return [r["CELL_TYPE"] for r in _select(json_file_path, numData, step, hallmark)]


def prepare_data_for_multiprocessing(hallmarks, abstracts):
    return aligned_data(hallmarks, abstracts)


def process_data_with_multiprocessing(combined_data):
    return parallel_map(check_line, combined_data)


def list_check(errorlist, goodlist):
    promote_matches(errorlist, goodlist, process_item)


if __name__ == "__main__":
    run_field_evaluation(check_line, "CELL_TYPE", judge=process_item)
