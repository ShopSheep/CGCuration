import csv
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import cgc_utils as utils


def response(text, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text), finish_reason=finish_reason
            )
        ]
    )


def http_response(
    status=200,
    html='<div class="abstract-content"><p>One <b>two</b>.</p><p>Three.</p></div>',
):
    result = requests.Response()
    result.status_code = status
    result._content = html.encode()
    result._content_consumed = True
    return result


def test_abstract_keeps_word_boundaries_and_tls_verification(monkeypatch):
    get = Mock(return_value=http_response())
    monkeypatch.setattr(utils.requests, "get", get)
    assert utils.check_abstract("123") == ("123", "One two . Three.")
    get.assert_called_once_with("https://pubmed.ncbi.nlm.nih.gov/123/", timeout=(5, 20))


@pytest.mark.parametrize("status", [400, 403, 404])
def test_permanent_http_error_is_not_retried(monkeypatch, status):
    get = Mock(return_value=http_response(status))
    monkeypatch.setattr(utils.requests, "get", get)
    with pytest.raises(utils.AbstractError, match=str(status)):
        utils.check_abstract("123")
    assert get.call_count == 1


@pytest.mark.parametrize("html", ["", '<div class="abstract-content"> </div>'])
def test_no_abstract_fails_instead_of_sending_error_text_to_model(monkeypatch, html):
    monkeypatch.setattr(
        utils.requests, "get", Mock(return_value=http_response(html=html))
    )
    with pytest.raises(utils.AbstractError, match="abstract"):
        utils.check_abstract("123")


def test_transient_errors_recover_with_bounded_backoff(monkeypatch):
    get = Mock(side_effect=[requests.Timeout(), http_response(429), http_response()])
    sleep = Mock()
    monkeypatch.setattr(utils.requests, "get", get)
    monkeypatch.setattr(utils.time, "sleep", sleep)
    assert utils.check_abstract("123")[0] == "123"
    assert get.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


def test_retry_exhaustion_raises_without_sleeping_again(monkeypatch):
    get = Mock(side_effect=requests.ConnectionError("offline"))
    sleep = Mock()
    monkeypatch.setattr(utils.requests, "get", get)
    monkeypatch.setattr(utils.time, "sleep", sleep)
    with pytest.raises(utils.AbstractError, match="3 attempts"):
        utils.check_abstract("123")
    assert get.call_count == 3
    assert sleep.call_count == 2


@pytest.mark.parametrize("pmid", [None, "", "../other", "0", "-1", "１２３"])
def test_invalid_pmids_are_rejected_before_network(pmid):
    with pytest.raises(ValueError, match="PMID"):
        utils.check_abstract(pmid)


def test_duplicate_pmids_fetched_once_and_row_order_preserved(monkeypatch):
    fetch = Mock(side_effect=lambda pmid: (pmid, f"abstract {pmid}"))
    monkeypatch.setattr(utils, "check_abstract", fetch)
    result = utils.process_abstracts(["2", "1", "2", 1])
    assert result == [
        ("2", "abstract 2"),
        ("1", "abstract 1"),
        ("2", "abstract 2"),
        (1, "abstract 1"),
    ]
    assert fetch.call_count == 2


def test_client_is_reused_and_has_explicit_timeouts(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(utils, "_client", None)
    monkeypatch.setattr(utils, "OpenAI", factory)
    monkeypatch.setattr(utils.atexit, "register", Mock())
    clients = utils.parallel_map(lambda _: utils.get_client(), range(10))
    assert all(client is clients[0] for client in clients)
    factory.assert_called_once_with(timeout=60.0, max_retries=2)


def test_complete_preserves_model_default_and_can_override(monkeypatch):
    client = Mock()
    client.chat.completions.create.return_value = response(" yes ")
    monkeypatch.setattr(utils, "get_client", lambda: client)
    assert utils.complete("question", model="historical") == "yes"
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "historical"
    assert kwargs["messages"] == [{"role": "user", "content": "question"}]
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")
    utils.complete("question")
    assert (
        client.chat.completions.create.call_args.kwargs["model"] == "configured-model"
    )


@pytest.mark.parametrize("finish", ["length", "content_filter", "tool_calls"])
def test_incomplete_responses_are_rejected(finish):
    with pytest.raises(ValueError, match="Incomplete"):
        utils.response_text(response("partial", finish))


def test_missing_response_text_is_rejected():
    with pytest.raises(ValueError, match="no text"):
        utils.response_text(response(None))
    with pytest.raises(ValueError, match="no choices"):
        utils.response_text(SimpleNamespace(choices=[]))


def test_alias_index_prefers_approved_symbols_and_preserves_ambiguity(
    tmp_path, monkeypatch
):
    path = tmp_path / "aliases.csv"
    with path.open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerows(
            [
                ["Approved symbol", "Alias symbol", "Previous symbol"],
                ["NEW1", "OLD", "PREV"],
                ["NEW2", "OLD", "NEW1"],
                ["NEW1", "UNIQUE", ""],
            ]
        )
    monkeypatch.setenv("CGC_GENE_ALIASES", str(path))
    assert utils.aliasCheck(" PREV ") == "NEW1"
    assert utils.aliasCheck("UNIQUE") == "NEW1"
    assert utils.aliasCheck("NEW1") == "NEW1"
    assert utils.aliasCheck("OLD") == "OLD"
    assert utils.aliasCheck("unknown") == "unknown"
    assert utils._alias_index(str(path)) is utils._alias_index(str(path))


def test_bundled_alias_table_is_readable_and_resolves_known_alias():
    assert utils.aliasCheck("A1BG") == "A1BG"
    assert utils.aliasCheck("NCRNA00181") == "A1BG-AS1"


def test_sampling_is_repeatable_and_filters_before_stride(tmp_path):
    rows = [
        {
            "PUBMED_PMID": str(i),
            "HALLMARK": "topic" if i % 2 else "other",
            "CELL_TYPE": "cell",
        }
        for i in range(8)
    ]
    path = tmp_path / "records.json"
    path.write_text(json.dumps(rows))
    expected = [rows[1], rows[5]]
    assert (
        utils.select_records(path, 2, 2, hallmark="TOPIC", field="CELL_TYPE")
        == expected
    )
    assert (
        utils.select_records(path, 2, 2, hallmark="TOPIC", field="CELL_TYPE")
        == expected
    )
    assert utils.select_records(path, 0) == []


@pytest.mark.parametrize("limit,step", [(-1, 1), (2, 0), (2, -1)])
def test_invalid_sampling_rejected(limit, step):
    with pytest.raises(ValueError):
        utils.select_records(utils.DATA_PATH, limit, step)


def test_alignment_mismatch_cannot_silently_truncate():
    with pytest.raises(ValueError, match="different lengths"):
        utils.aligned_data(["topic"], [])
    with pytest.raises(ValueError, match="different lengths"):
        utils.partition_results(["1"], [], [], [])


def test_successful_write_and_failed_write_preserve_output(tmp_path):
    path = tmp_path / "output.json"
    utils.write_records(path, [{"x": 1}])
    with pytest.raises(TypeError):
        utils.write_records(path, [object()])
    assert json.loads(path.read_text()) == [{"x": 1}]
    assert list(tmp_path.iterdir()) == [path]


def test_name_and_boolean_parsing_are_explicit():
    assert utils.split_names("A,B\n A, \"C\", ''") == ["A", "B", "C"]
    assert utils.parse_boolean(' "YES".') is True
    assert utils.parse_boolean(" no ") is False
    with pytest.raises(ValueError):
        utils.parse_boolean("probably yes")


def test_worker_configuration_and_empty_batches(monkeypatch):
    monkeypatch.setenv("CGC_WORKERS", "0")
    with pytest.raises(ValueError):
        utils.parallel_map(str, [1])
    assert utils.parallel_map(str, []) == []


def test_concurrent_alias_lookups_build_only_one_index(tmp_path, monkeypatch):
    path = tmp_path / "concurrent.csv"
    path.write_text("Approved symbol,Alias symbol,Previous symbol\nNEW,OLD,\n")
    utils._load_alias_index.cache_clear()
    original_open = open
    opened = Mock(side_effect=original_open)
    monkeypatch.setattr("builtins.open", opened)
    assert all(
        index["OLD"] == "NEW"
        for index in utils.parallel_map(
            lambda _: utils._alias_index(str(path)), range(20)
        )
    )
    assert opened.call_count == 1
