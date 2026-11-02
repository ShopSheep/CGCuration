import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

import cgc_utils as utils

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "folder,filename,field",
    [
        ("Cell Type", "CellTypeEval.py", "CELL_TYPE"),
        ("Cell Line", "CellLineEval.py", "CELL_LINE"),
        ("Impact", "ImpactEval.py", "IMPACT"),
    ],
)
def test_sampling_returns_aligned_reference_answers_without_global_target(
    evaluator, tmp_path, folder, filename, field
):
    module = evaluator(folder, filename)
    rows = [
        {"PUBMED_PMID": str(i), "HALLMARK": "topic", field: f"value{i}"}
        for i in range(6)
    ]
    rows.insert(0, {"PUBMED_PMID": "100", "HALLMARK": "other", field: "excluded"})
    path = tmp_path / "data.json"
    path.write_text(json.dumps(rows))
    assert module.extract_pubmed_ids(path, 2, 2, hallmark="topic") == (
        ["0", "2"],
        ["topic", "topic"],
    )
    assert module.extract_impactlist(path, 2, 2, hallmark="topic") == [
        "value0",
        "value2",
    ]


def test_gene_evaluation_splits_prediction_commas_and_has_no_accumulated_state(
    evaluator, tmp_path
):
    module = evaluator("Gene Name", "GeneNameEval.py")
    assert module.check_alias(["A1BG, A1CF\nA1BG"]) == [["A1BG", "A1CF"]]
    path = tmp_path / "genes.json"
    path.write_text(json.dumps([{"PUBMED_PMID": "1", "GENE_NAME": "A1BG"}]))
    assert (
        module.extract_infos(path, 10, 1)
        == module.extract_infos(path, 10, 1)
        == (["1"], ["A1BG"])
    )
    assert module.compare_genes([["A1BG"]], [["A1BG", "A1CF"]]) == []
    assert module.compare_genes([["A1BG"]], [["A1CF"]], ["1"]) == [
        ("index: 0", "1", ["A1BG"], ["A1CF"])
    ]
    with pytest.raises(ValueError):
        module.compare_genes([["A1BG"]], [])


def test_hallmark_evaluation_uses_runtime_target_and_normalizes_answers(
    evaluator, tmp_path, monkeypatch
):
    module = evaluator("Hallmark", "HallmarkEval.py")
    complete = Mock(return_value=" Yes. ")
    monkeypatch.setattr(module, "complete", complete)
    assert module.check_hallmark(("1", "abstract"), "angiogenesis") == "yes"
    assert "angiogenesis" in complete.call_args.args[0][0]["content"]
    path = tmp_path / "data.json"
    path.write_text(json.dumps([{"PUBMED_PMID": "1", "HALLMARK": "angiogenesis"}]))
    assert module.extract_pubmed_ids(path, "angiogenesis", 5, 1) == ["1"]
    assert module.extract_pubmed_ids(path, "angiogenesis", 5, 1) == ["1"]
    assert module.extract_hallmark([("1", "abstract")], "angiogenesis") == ["yes"]
    assert module.extract_hallmark([("1", "abstract")], "angiogenesis") == ["yes"]


def test_impact_prompt_uses_selected_hallmark_and_gene_context(evaluator, monkeypatch):
    module = evaluator("Impact", "ImpactEval.py")
    complete = Mock(return_value="SuppResses")
    monkeypatch.setattr(module, "complete", complete)
    assert (
        module.check_impact(
            ("cell replicative immortality", "abstract", "TP53", "lung cells")
        )
        == "suppresses"
    )
    prompt = complete.call_args.args[0][0]["content"]
    assert "cell replicative immortality" in prompt
    assert "TP53" in prompt and "lung cells" in prompt
    assert "cellular energetics" not in prompt
    with pytest.raises(ValueError, match="Invalid hallmark"):
        module.check_impact(("garbage", "abstract"))
    complete.return_value = "maybe"
    with pytest.raises(ValueError, match="Invalid impact"):
        module.check_impact(("angiogenesis", "abstract"))


def test_cell_type_uses_equality_instead_of_substring_for_skipping(
    evaluator, monkeypatch
):
    module = evaluator("Cell Type", "CellTypeEval.py")
    complete = Mock(side_effect=["analysis", "lung"])
    monkeypatch.setattr(module, "complete", complete)
    assert module.check_line(("function summary", "abstract")) == ""
    assert complete.call_count == 0
    assert module.check_line(("function", "abstract")) == "lung"


def test_cell_line_prompt_requires_evidence_instead_of_guesses(evaluator, monkeypatch):
    module = evaluator("Cell Line", "CellLineEval.py")
    complete = Mock(return_value="")
    monkeypatch.setattr(module, "complete", complete)
    assert module.check_line(("angiogenesis", "abstract")) == ""
    prompt = complete.call_args.args[0][0]["content"]
    assert "Do not guess" in prompt
    assert "best guess for three" not in prompt


def test_semantic_matches_partition_duplicates_without_removing_wrong_rows(monkeypatch):
    item = ("1", "topic", "answer", "equivalent")
    bad = ("2", "topic", "answer", "wrong")
    errors, good = [item, bad, item], []
    utils.promote_matches(
        errors, good, lambda row: row if row[3] == "equivalent" else None
    )
    assert errors == [bad]
    assert good == [item, item]


@pytest.mark.parametrize(
    "folder,filename",
    [("Cell Type", "CellTypeEval.py"), ("Cell Line", "CellLineEval.py")],
)
def test_semantic_judges_accept_case_and_punctuation(
    evaluator, monkeypatch, folder, filename
):
    module = evaluator(folder, filename)
    monkeypatch.setattr(module, "complete", Mock(return_value=" YES. "))
    row = ("1", "topic", "expected", "related")
    assert module.process_item(row) == row


def test_description_matching_requires_same_cell_context_and_reports_unmatched(
    evaluator, monkeypatch
):
    module = evaluator("Description", "DescriptionEval.py")
    base = {
        "PUBMED_PMID": "1",
        "GENE_NAME": "A1BG",
        "HALLMARK": "role in cancer",
        "CELL_TYPE": "lung",
        "DESCRIPTION": "oncogene",
    }
    wrong_cell = dict(base, CELL_TYPE="liver", DESCRIPTION="TSG")
    generated = [dict(base, PUBMED_PMID=1), dict(base, PUBMED_PMID="missing")]
    assert module.evaluate_descriptions(generated, [wrong_cell, base]) == {
        "correct": 1,
        "compared": 1,
        "unmatched": 1,
    }


def test_description_exact_match_avoids_api_and_semantic_reply_is_validated(
    evaluator, monkeypatch
):
    module = evaluator("Description", "DescriptionEval.py")
    complete = Mock(side_effect=["reasoning", " TRUE. "])
    monkeypatch.setattr(module, "complete", complete)
    assert module.descriptions_match(" same ", "SAME", "topic")
    assert complete.call_count == 0
    assert module.descriptions_match("longer description", "description", "topic")
    assert complete.call_count == 2
    assert not module.descriptions_match("TSG", "oncogene", "role in cancer")
    assert module.evaluate_descriptions([], []) == {
        "correct": 0,
        "compared": 0,
        "unmatched": 0,
    }


def test_imports_have_no_network_file_reads_or_tls_side_effects(tmp_path):
    # Import every script from a directory with no data, credentials, or generated output.
    script = """
import importlib.util
import pathlib
import ssl
import sys
sys.path.insert(0, sys.argv[1])
original = ssl._create_default_https_context
root = pathlib.Path(sys.argv[1])
for path in [root / 'CGCExtract.py', *root.glob('Evaluators/*/*.py')]:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
assert ssl._create_default_https_context is original
"""
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "path",
    [
        "CGCExtract.py",
        *[str(p.relative_to(ROOT)) for p in sorted(ROOT.glob("Evaluators/*/*.py"))],
    ],
)
def test_all_standalone_commands_show_help_from_any_directory(path, tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / path), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_zero_limit_extraction_writes_valid_empty_output_without_api(tmp_path):
    output = tmp_path / "output.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "CGCExtract.py"),
            "--limit",
            "0",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text()) == []
