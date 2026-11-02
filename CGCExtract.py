"""Extract CGC records from PubMed abstracts using the original two-stage prompts."""

import argparse
import json
import logging
from pathlib import Path

from cgc_utils import (
    DATA_PATH,
    aliasCheck,
    complete,
    parallel_map,
    parse_boolean,
    process_abstracts,
    select_records,
    split_names,
    write_records,
)

hallmark_list = [
    "invasion and metastasis",
    "change of cellular energetics",
    "proliferative signalling",
    "genome instability and mutations",
    "escaping immune response to cancer",
    "cell replicative immortality",
    "angiogenesis",
    "suppression of growth",
    "tumour promoting inflammation",
    "escaping programmed cell death",
    "clinical impact",
    "role in cancer",
    "mouse model",
    "fusion partner",
    "senescence",
    "interaction with pathogen",
    "global regulation of gene expression",
    "types of alteration in cancer",
    "impact of mutation on function",
    "function summary",
    "differentiation and development",
    "cell division control",
]
subcategory_list = [
    "clinical impact",
    "role in cancer",
    "mouse model",
    "fusion partner",
    "senescence",
    "interaction with pathogen",
    "global regulation of gene expression",
    "types of alteration in cancer",
    "impact of mutation on function",
    "function summary",
    "differentiation and development",
    "cell division control",
]

logger = logging.getLogger(__name__)

json_file_path = DATA_PATH


def extract_pubmed_ids(json_file_path, numData):
    return [row["PUBMED_PMID"] for row in select_records(json_file_path, numData)]


def check_gene(data):
    pmid, abstract = data
    ctd = "I will provide you an abstract from PubMed. Your job is to return the name of the gene that is being discussed in the abstract. Think step by step, and explain your reasoning steps. Look for two possible genes that are being discussed. First and most importantly, look for phosphorylation: if a protein is phosphorylating, extract the name of the gene that codes for the protein that phosphorylates, and end the analysis. If the abstract mentions a protein but not gene, identify and return the corresponding gene name for that protein. If the abstract does not explicitly mention a gene name but discusses a protein, respond with the name of the gene that encodes for the protein mentioned in the context of the abstract. If the role of a protein is the main focus of the abstract, first identify the protein that is the main point of discussion since there could be multiple proteins mentioned in the abstract, and second, extract the name of the gene that codes for the protein. Ensure that you focus on the primary subject of the study, which is often the protein or gene whose function or characteristics are being most extensively explored or characterized in the abstract. Make sure you are returning the name of gene, not protein. Try to return the symbol for the extracted gene names, not the outdated ones."
    result1 = complete(
        [{"role": "user", "content": ctd + "\n\n" + abstract}],
        model="gpt-4-0125-preview",
    )
    response = complete(
        [
            {
                "role": "user",
                "content": f"Read {result1}. Extract the gene symbols that were extracted from that text. No descriptions required, only return the gene symbols, comma separated.",
            }
        ],
        model="gpt-4-0125-preview",
    )
    result = response.replace("\n", ", ")
    corrected = [aliasCheck(name) for name in split_names(result)]
    return [pmid] + list(dict.fromkeys(corrected))


def check_cell_type(data):
    pmid, abstract = data
    ctd = "I will provide you with an abstract from PubMed. Your job is to return the cell type that is being described in the abstract to be affected. Think step by step, and explain your reasoning steps. Look for two possible cell types that are being discussed. If only one cell type is being discussed, then extract the same cell type twice. If no particular cell type is being discussed, extract '' twice."
    result1 = complete(
        [{"role": "user", "content": ctd + "\n\n" + abstract}],
        model="gpt-4-0125-preview",
    )
    response = complete(
        [
            {
                "role": "user",
                "content": f"Read {result1}. Extract the cell type names that were extracted from that text. No descriptions required, only return the cell type names, comma separated.",
            }
        ],
        model="gpt-4-0125-preview",
    )
    result2 = response.replace("\n", ", ")
    return [pmid] + (split_names(result2) or [""])


def check_hallmark(data):
    pmid, abstract, gene_names, cell_types, target = data
    applicable_hallmark = []
    for gene in gene_names:
        for cell in cell_types:
            logger.info(
                f"Checking if abstract for PMID {pmid} is related to {target}..."
            )
            if target in subcategory_list:
                ctd = f"I will provide you an abstract from PubMed. Your job is to check if the abstract's information can describe {gene}'s effects on {cell} for the topic of {target}. Think step-by-step, break down the abstract into smaller problems, and explain your reasoning process. At the end, make a final decision; if the abstract information can describe the {gene}'s effects on {cell} for the topic of {target} say 'yes.'"
            else:
                ctd = f"I will provide you an abstract from PubMed. Your job is to check if the abstract's information suggest that {gene} has the effect(s) described by the Hallmark {target} on {cell}. Think step-by-step, break down the abstract into smaller problems, and explain your reasoning process. At the end, make a final decision; if abstract's information suggest that {gene} has the effect(s) described by the Hallmark {target} on {cell}, say 'yes.'"
            result1 = complete(
                [{"role": "user", "content": ctd + "\n\n" + abstract}],
                model="gpt-4-0125-preview",
            )
            result2 = complete(
                [
                    {
                        "role": "user",
                        "content": f"Read a response from a GPT: {result1}. Extract 'yes' or 'no' based on what the GPT had answered to the question. Only extract 'yes' or 'no'. No descriptions required.",
                    }
                ],
                model="gpt-4-1106-preview",
            )
            if parse_boolean(result2):
                applicable_hallmark.append((pmid, abstract, gene, cell, target))
    return applicable_hallmark


def gptdesc(abstract, gene, cell, hallmark):
    ques = f"For gene: {gene}, cell: {cell}, and hallmark: {hallmark}, generate a one or two sentence summary of the abstract's finding, focused on {hallmark}.  Only include sentences of your findings, not things like 'The study demonstrates that,' or 'The study you've described', or any phrases like that."
    logger.info(f"Checking descriptions for hallmark {hallmark}...")
    description = complete(
        [{"role": "user", "content": ques + "\n\n" + abstract}],
        model="gpt-4-0125-preview",
    )
    return description


def process_genes(abstracts):
    return parallel_map(check_gene, abstracts)


def process_cell_type(abstracts):
    return parallel_map(check_cell_type, abstracts)


def process_hallmarks(hallmark_input):
    return [
        record
        for group in parallel_map(check_hallmark, hallmark_input)
        for record in group
    ]


def check_desc(data):
    pmid, abstract, gene, cell, hallmark = data
    topic = hallmark.casefold()
    if topic == "role in cancer":
        question = f"Based on the given abstract, determine the role in cancer of gene: {gene} for cell: {cell}. You have three options to choose from, and multiple options may be applicable: A) TSG, B) Oncogene, C) Fusion. If no evidence is presented, extract: D) No evidence. Think step-by-step and explain your reasoning process along the way."
        followup = "Based on your response above, extract the answer only. For example, if you chose both A) TSG and B) Oncogene, return 'TSG, Oncogene'. If you chose D because there was no evidence, return an empty string. No descriptions required."
    elif topic == "fusion partner":
        question = (
            f"Extract the fusion partner(s) of gene: {gene} based on the abstract: "
        )
        followup = "Extract the fusion partners as a JSON array of strings. Return only the array, nothing more. If none are identified, return []."
    else:
        if topic not in {name.casefold() for name in hallmark_list}:
            raise ValueError(f"Invalid hallmark: {hallmark}")
        if topic in {
            "proliferative signalling",
            "suppression of growth",
            "change of cellular energetics",
        }:
            question = f"For gene: {gene}, cell: {cell}, and hallmark: {hallmark}, generate a one or two sentence summary of the abstract's finding, focused on how {gene} promotes {hallmark}. Only include sentences of your findings, not introductory phrases."
            return [(*data, complete(question + "\n\n" + abstract))]
        return [(*data, gptdesc(abstract, gene, cell, hallmark))]
    messages = [{"role": "user", "content": question + "\n\n" + abstract}]
    first = complete(messages)
    messages.extend(
        [{"role": "assistant", "content": first}, {"role": "user", "content": followup}]
    )
    description = complete(messages)
    if topic == "fusion partner":
        partners = json.loads(description)
        if not isinstance(partners, list) or any(
            (not isinstance(p, str) for p in partners)
        ):
            raise ValueError("Fusion partners must be a JSON array of strings")
        description = ", ".join(
            dict.fromkeys((p.strip() for p in partners if p.strip()))
        )
    else:
        description = description.strip("\"'")
    return [(*data, description)] if description else []


def process_desc(hallmarked_input):
    return [
        record
        for group in parallel_map(check_desc, hallmarked_input)
        for record in group
    ]


def extract_records(input_path=DATA_PATH, limit=2, hallmarks=None):
    targets = (
        hallmark_list
        if hallmarks is None
        else list(dict.fromkeys(name.strip().casefold() for name in hallmarks))
    )
    invalid = set(targets).difference(hallmark_list)
    if invalid:
        raise ValueError(f"Invalid hallmarks: {sorted(invalid)}")
    pubmed_ids = list(
        dict.fromkeys(
            str(pmid).strip() for pmid in extract_pubmed_ids(input_path, limit)
        )
    )
    abstracts = process_abstracts(pubmed_ids)
    genes = process_genes(abstracts)
    cells = process_cell_type(abstracts)
    if len({len(abstracts), len(genes), len(cells)}) != 1:
        raise ValueError("Extraction stages returned different numbers of rows")
    inputs = [
        (pmid, abstract, tuple(gene[1:]), tuple(cell[1:]), hallmark)
        for hallmark in targets
        for (pmid, abstract), gene, cell in zip(abstracts, genes, cells)
    ]
    output = process_desc(process_hallmarks(inputs))
    return [
        {
            "GENE_NAME": gene,
            "CELL_TYPE": cell,
            "PUBMED_PMID": pmid,
            "HALLMARK": hallmark,
            "DESCRIPTION": description,
        }
        for pmid, abstract, gene, cell, hallmark, description in output
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATH)
    parser.add_argument("--output", type=Path, default=Path("final_results.json"))
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument(
        "--hallmark", action="append", type=str.casefold, choices=hallmark_list
    )
    args = parser.parse_args()
    records = extract_records(args.input, args.limit, args.hallmark)
    write_records(args.output, records)
    print(f"Wrote {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()
