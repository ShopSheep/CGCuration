from unittest.mock import Mock

import pytest

import CGCExtract as extract


def test_gene_names_split_on_commas_and_newlines_then_deduplicate(monkeypatch):
    monkeypatch.setattr(
        extract, "complete", Mock(side_effect=["analysis", "A,B\nA, C"])
    )
    monkeypatch.setattr(
        extract, "aliasCheck", lambda gene: "A" if gene == "C" else gene
    )
    assert extract.check_gene(("1", "abstract")) == ["1", "A", "B"]


def test_empty_cell_type_still_allows_context_free_hallmark_checks(monkeypatch):
    monkeypatch.setattr(extract, "complete", Mock(side_effect=["analysis", "'', ''"]))
    assert extract.check_cell_type(("1", "abstract")) == ["1", ""]


def test_all_gene_cell_pairs_survive_hallmark_and_description_stages(monkeypatch):
    monkeypatch.setattr(extract, "complete", lambda *args, **kwargs: "yes")
    monkeypatch.setattr(
        extract, "gptdesc", lambda abstract, gene, cell, hallmark: f"{gene} in {cell}"
    )
    data = ("1", "abstract", ("A", "B"), ("X", "Y"), "angiogenesis")
    records = extract.process_desc(extract.process_hallmarks([data]))
    assert {(r[2], r[3], r[5]) for r in records} == {
        ("A", "X", "A in X"),
        ("A", "Y", "A in Y"),
        ("B", "X", "B in X"),
        ("B", "Y", "B in Y"),
    }


def test_programmed_cell_death_has_a_description(monkeypatch):
    monkeypatch.setattr(extract, "gptdesc", lambda *args: "finding")
    data = ("1", "abstract", "A", "X", "escaping programmed cell death")
    assert extract.check_desc(data) == [(*data, "finding")]


def test_fusion_partners_are_json_names_not_characters(monkeypatch):
    monkeypatch.setattr(
        extract, "complete", Mock(side_effect=["analysis", '["BCR", "ETV6", "BCR"]'])
    )
    data = ("1", "abstract", "ABL1", "X", "fusion partner")
    assert extract.check_desc(data) == [(*data, "BCR, ETV6")]


@pytest.mark.parametrize("value", ["[]", '["", " "]'])
def test_no_fusion_partner_emits_no_record(monkeypatch, value):
    monkeypatch.setattr(extract, "complete", Mock(side_effect=["analysis", value]))
    assert extract.check_desc(("1", "abstract", "A", "X", "fusion partner")) == []


@pytest.mark.parametrize("value", ['"BCR"', "[1]", '{"partner": "BCR"}'])
def test_invalid_fusion_shapes_fail(monkeypatch, value):
    monkeypatch.setattr(extract, "complete", Mock(side_effect=["analysis", value]))
    with pytest.raises(ValueError):
        extract.check_desc(("1", "abstract", "A", "X", "fusion partner"))


def test_no_cancer_role_emits_no_record(monkeypatch):
    monkeypatch.setattr(extract, "complete", Mock(side_effect=["analysis", "''"]))
    assert extract.check_desc(("1", "abstract", "A", "X", "role in cancer")) == []


def test_pipeline_retains_every_output_record_and_deduplicates_pmids(monkeypatch):
    monkeypatch.setattr(extract, "extract_pubmed_ids", lambda *args: ["1", "1"])
    fetch = Mock(return_value=[("1", "abstract")])
    monkeypatch.setattr(extract, "process_abstracts", fetch)
    monkeypatch.setattr(extract, "process_genes", lambda *args: [["1", "A", "B"]])
    monkeypatch.setattr(extract, "process_cell_type", lambda *args: [["1", "X", "Y"]])
    monkeypatch.setattr(extract, "complete", lambda *args, **kwargs: "yes")
    monkeypatch.setattr(extract, "gptdesc", lambda *args: "finding")
    result = extract.extract_records(hallmarks=["angiogenesis", "angiogenesis"])
    fetch.assert_called_once_with(["1"])
    assert len(result) == 4
    assert all(r["DESCRIPTION"] == "finding" for r in result)
    assert {(r["GENE_NAME"], r["CELL_TYPE"]) for r in result} == {
        ("A", "X"),
        ("A", "Y"),
        ("B", "X"),
        ("B", "Y"),
    }


def test_invalid_target_fails_before_fetching_any_evidence(monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(extract, "process_abstracts", fetch)
    with pytest.raises(ValueError, match="Invalid hallmarks"):
        extract.extract_records(hallmarks=["unknown"])
    fetch.assert_not_called()
