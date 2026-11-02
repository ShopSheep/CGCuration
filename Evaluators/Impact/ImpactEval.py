"""Evaluate IMPACT extraction against CGC reference rows."""

import sys
from pathlib import Path

# Keep the original standalone script paths runnable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cgc_utils import (  # noqa: E402
    DATA_PATH,
    aligned_data,
    complete,
    parallel_map,
    run_field_evaluation,
    select_records,
)

json_file_path = DATA_PATH

from CGCExtract import hallmark_list  # noqa: E402


def check_impact(data):
    hallmark, abstract, *context = data
    topic = hallmark.casefold()
    if topic not in {name.casefold() for name in hallmark_list}:
        raise ValueError(f"Invalid hallmark: {hallmark}")
    if topic in {
        "cell division control",
        "clinical impact",
        "differentiation and development",
        "function summary",
        "fusion partner",
        "global regulation of gene expression",
        "impact of mutation on function",
        "interaction with pathogen",
        "mouse model",
        "types of alteration in cancer",
    }:
        return ""
    if topic in {
        "proliferative signalling",
        "suppression of growth",
        "change of cellular energetics",
    }:
        return "promotes"
    subject = (
        f"gene {context[0]} in {context[1] or 'the cells discussed'}"
        if context
        else "the main gene discussed"
    )
    if topic == "role in cancer":
        question = f"Determine the role in cancer of {subject} using only the abstract. Return oncogene, TSG, or fusion, or a comma separated list if several apply. Return an empty string if there is no evidence. No descriptions required."
    else:
        question = f"Determine whether the wildtype gene product of {subject} promotes or suppresses {hallmark}, using only the abstract. Return only 'promotes', 'suppresses', 'promotes and suppresses', or an empty string if there is no evidence. For escaping programmed cell death, assess escape from death, not death itself."
    result = complete([{"role": "user", "content": question + "\n\n" + abstract}])
    if topic != "role in cancer":
        result = result.strip("\"'").casefold()
        if result not in {"", "promotes", "suppresses", "promotes and suppresses"}:
            raise ValueError(f"Invalid impact response: {result!r}")
    return result


# Compatibility helpers for callers of the original scripts.
hallm = ""


def _select(path, numData, step, hallmark=None):
    return select_records(
        path,
        numData,
        step,
        hallmark=hallmark if hallmark is not None else hallm,
        field="IMPACT",
    )


def extract_pubmed_ids(json_file_path, numData, step, hallmark=None):
    rows = _select(json_file_path, numData, step, hallmark)
    return ([r["PUBMED_PMID"] for r in rows], [r["HALLMARK"] for r in rows])


def extract_impactlist(json_file_path, numData, step, hallmark=None):
    return [r["IMPACT"] for r in _select(json_file_path, numData, step, hallmark)]


def prepare_data_for_multiprocessing(hallmarks, abstracts):
    return aligned_data(hallmarks, abstracts)


def process_data_with_multiprocessing(combined_data):
    return parallel_map(check_impact, combined_data)


if __name__ == "__main__":
    run_field_evaluation(check_impact, "IMPACT")
