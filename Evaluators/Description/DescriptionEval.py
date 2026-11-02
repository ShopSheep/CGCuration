"""Compare generated descriptions with matching CGC reference contexts."""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cgc_utils import (  # noqa: E402
    DATA_PATH,
    aliasCheck,
    complete,
    parse_boolean,
    read_records,
)


def _key(record):
    return (
        str(record["PUBMED_PMID"]).strip(),
        aliasCheck(record["GENE_NAME"]),
        record["HALLMARK"].strip().casefold(),
        record.get("CELL_TYPE", "").strip().casefold(),
    )


def descriptions_match(actual, expected, hallmark):
    if actual.strip().casefold() == expected.strip().casefold():
        return True
    if (
        hallmark.casefold() == "role in cancer"
        or not actual.strip()
        or (not expected.strip())
    ):
        return False
    messages = [
        {
            "role": "user",
            "content": f"Compare description 1: {actual} and description 2: {expected}. If description 1 conveys the same information, or the same information and additional information compared to description 2, return 'True', and if not, return 'False'. Think step-by-step.",
        }
    ]
    first = complete(messages)
    result = complete(
        [
            {
                "role": "user",
                "content": f"Read {first} and return 'True' or 'False' based on the given text. Only return True or False. No other information required.",
            }
        ]
    )
    return parse_boolean(result, true="true", false="false")


def evaluate_descriptions(generated, reference):
    index = defaultdict(list)
    for row in reference:
        index[_key(row)].append(row)
    correct = compared = unmatched = 0
    for row in generated:
        matches = index.get(_key(row), [])
        if not matches:
            unmatched += 1
        for expected in matches:
            compared += 1
            correct += descriptions_match(
                row["DESCRIPTION"], expected["DESCRIPTION"], row["HALLMARK"]
            )
    return {"correct": correct, "compared": compared, "unmatched": unmatched}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path, default=Path("final_results.json"))
    parser.add_argument("--reference", type=Path, default=DATA_PATH)
    args = parser.parse_args()
    result = evaluate_descriptions(
        read_records(args.generated), read_records(args.reference)
    )
    print(f"Correct matched comparisons: {result['correct']}/{result['compared']}")
    print(
        f"Generated records without a matching reference context: {result['unmatched']}"
    )
    if not result["compared"]:
        print("No matching contexts; accuracy is undefined.")


if __name__ == "__main__":
    main()
