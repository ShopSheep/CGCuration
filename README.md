# COSMIC Cancer Genome Census Data Curation using GPT-4

- The original experiments reported 79% accuracy for curating the COSMIC CGC dataset using GPT-4.
- We utilized Zero-shot Chain-Of-Thought (CoT) approach, and Retrieval-Augmented Generation (RAG) to automate the curation process for COSMIC CGC Dataset.

Contact: David Roh, [Youngmok Jung](https://quito418.github.io/quito418/)

Email: shwlsdud16@icloud.com, youngmok.jung@inocras.com

---

## Contents
* [Extraction Accuracy](#extraction-accuracy)
* [Setup](#setup)
* [Extraction](#extraction)
* [Evaluators](#evaluators)
* [Development](#development)
---
## Extraction Accuracy

These are the original experiment results, not fresh measurements of the cleaned-up code.

- We have evaluated GPT-4's extraction performance for the following categories in COSMIC CGC data: Gene Name, Cell Type, Hallmark, and Description.
- For Gene Name, Cell Type, and Hallmark extractions, we utilized Retrieval-Augmented Generation by providing the LLM with PubMed abstracts.
- For Gene Name and Hallmark evaluations, we used text comparison.
- For Cell Type and Description evaluations, we used semantic comparison using GPT-4.
- Gene Name extraction showed 93% accuracy using 0-Shot CoT approach.
- Cell Type extraction showed 92.4% accuracy using 0-shot CoT approach.
- Hallmark extraction showed 96.7% accuracy using 0-shot CoT approach.
- Description extraction showed 92.7% accuracy using 0-shot approach.
---
## Setup

Requires Python 3.10 or newer. From the repository directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`. Optionally set `OPENAI_MODEL` to a Chat Completions model accessible to your account and compatible with the experiment's sampling parameters. Without an override, the scripts retain the historical `gpt-4-0125-preview` and `gpt-4-1106-preview` IDs; this cleanup does not verify their availability. Keep the model choice fixed and recorded when comparing experiments.

`CGC_WORKERS` controls concurrent I/O tasks (default: 4). The shared SDK client has a 60-second request timeout and two retries, following the [official OpenAI SDK documentation](https://developers.openai.com/api/reference/python). PubMed retrieval uses three attempts for transient failures, with finite timeouts and backoff. Missing abstracts and permanent HTTP failures stop a run instead of becoming model input. TLS verification remains enabled.

Gene normalization reads the bundled `geneAlias.csv` once per process and uses an in-memory lookup. MySQL is no longer required. Approved symbols take precedence over aliases; ambiguous aliases and unknown symbols remain unchanged. The CSV is a historical HGNC snapshot, not a live source of current gene nomenclature. To supply another CSV with the same column names, set `CGC_GENE_ALIASES`. Original source: [HGNC custom downloads](https://www.genenames.org/download/custom/).

## Extraction

```sh
python CGCExtract.py --limit 2 --output final_results.json
python CGCExtract.py --limit 2 --hallmark 'role in cancer' --output final_results.json
```

`--input` accepts another CGC JSON array. `--limit` selects input rows before duplicate PMIDs are removed. Repeat `--hallmark` to select several topics; by default all 22 topics are checked. Each distinct PMID is fetched and extracted once per run. All accepted gene/cell/hallmark combinations are retained. Output keeps the original five fields: `GENE_NAME`, `CELL_TYPE`, `PUBMED_PMID`, `HALLMARK`, and `DESCRIPTION`.

The pipeline retains the original two-stage gene, cell type, and hallmark prompts. A full run can therefore make many paid requests even for a small input. Use a small limit and selected hallmarks for initial runs. Output is replaced atomically only after all stages succeed.

## Evaluators

Each original script path remains runnable. All scripts accept `--help`, use the bundled reference data by default, and can run from any working directory. Output paths are relative to your working directory; default input and `.env` paths are relative to the repository.

```sh
python 'Evaluators/Gene Name/GeneNameEval.py' --limit 20 --step 1
python 'Evaluators/Cell Type/CellTypeEval.py' --hallmark 'invasion and metastasis' --limit 20
python 'Evaluators/Cell Line/CellLineEval.py' --hallmark 'invasion and metastasis' --limit 20
python 'Evaluators/Impact/ImpactEval.py' --hallmark 'cell replicative immortality' --limit 20
python 'Evaluators/Hallmark/HallmarkEval.py' --hallmark 'angiogenesis' --limit 20
python 'Evaluators/Description/DescriptionEval.py' --generated final_results.json
```

Sampling is deterministic: filter by hallmark and nonempty evaluated field, select every `--step`th eligible row, then apply `--limit`. Repeated calls do not accumulate rows. An empty selection reports that the metric is undefined.

- Gene evaluation checks whether the normalized expected genes are included in the extracted candidates.
- Cell type and cell line evaluations use case-insensitive exact comparison first, then the original broad semantic comparison prompts. Cell line extraction now requires evidence in the abstract and no longer invents candidate lines.
- Impact evaluation asks about the selected hallmark and supplied gene/cell context. The original category rules are retained: non-directional categories return an empty impact, while proliferative signalling, suppression of growth, and change of cellular energetics return `promotes`.
- Hallmark evaluation reports positive-label agreement. Since it samples known positive records, it does not estimate specificity or overall classification accuracy.
- Description evaluation indexes references by PMID, normalized gene, hallmark, and cell type. It reports matched comparisons separately from generated records without a matching reference context. Multiple reference descriptions for one context are counted as separate comparisons.

Model-judged agreement is not independent evidence of biological correctness. The original accuracy figures must be remeasured before applying them to this version, especially because incorrect prompts, missing results, and matching rules were repaired.

## Development

```sh
python -m pip install -r requirements-dev.txt
pytest -q
ruff check .
ruff format --check .
```

Tests mock external services and block unexpected HTTP requests. They cover result retention, fusion JSON parsing, alias ambiguity, sampling and alignment, scoring, retrieval failures, client reuse, atomic output, import safety, and standalone command execution. The included GitHub Actions workflow is configured to run the same checks on Python 3.10 and 3.14. Live API accuracy is not part of the offline test suite.
