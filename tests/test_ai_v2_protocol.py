"""General pair-review controls; all responses and artwork are artificial."""
import copy
import json

import pytest

from hsd_tool.ai_client import DeepSeekClient, PAIR_CHECKS, ReviewError
from test_ai_client import KEY, CONTENT, Opener, response


def pair(identity, verdict="same", **changes):
    item = {"candidate_id": identity, "verdict": verdict, "reason": "逐对核对的直接证据",
            "checks": {key: verdict == "same" for key in PAIR_CHECKS},
            "differences": [] if verdict == "same" else ["本候选的色块位置不同"]}
    item.update(changes)
    return item


def parse(items, expected=("one", "two")):
    return DeepSeekClient(KEY)._decision({"candidate_reviews": items}, list(expected))


def test_other_candidates_differences_do_not_invalidate_direct_positive_pair():
    selected = pair("one")
    result = parse([pair("two", "different"), selected])
    assert result["verdict"] == "same" and result["candidate_id"] == "one"
    assert all(result["checks"].values()) and result["differences"] == []
    assert not result["protocol_diagnostics"]["inconsistent"]
    assert result["protocol_diagnostics"]["raw_decision"]["candidate_reviews"] == [selected, pair("two", "different")]


@pytest.mark.parametrize("change", [
    {"verdict": "different", "checks": {key: True for key in PAIR_CHECKS}, "differences": ["contradiction"]},
    {"verdict": "different", "differences": []},
    {"verdict": "same", "checks": {key: False for key in PAIR_CHECKS}},
    {"verdict": "same", "differences": ["A real extra mark"]},
])
def test_semantic_conflicts_only_downgrade_and_preserve_bounded_original_fields(change):
    raw = pair("one", **change)
    result = parse([raw, pair("two", "different")])
    assert result["verdict"] == "uncertain" and result["candidate_id"] is None
    assert not any(result["checks"].values())
    diagnostic = result["protocol_diagnostics"]
    assert diagnostic["inconsistent"] and diagnostic["issues"][0]["candidate_id"] == "one"
    assert diagnostic["raw_decision"]["candidate_reviews"][0] == raw
    assert "response" not in diagnostic and "usage" not in diagnostic


@pytest.mark.parametrize("items", [[pair("one"), pair("two")], [pair("one"), pair("two", "uncertain")]])
def test_multiple_matches_or_unresolved_competitor_never_become_unique(items):
    result = parse(items)
    assert result["verdict"] == "uncertain" and not result["checks"]["unique_candidate"]


@pytest.mark.parametrize("items", [[pair("one")], [pair("one"), pair("one")],
                                    [pair("one"), pair("outside")], [pair("one"), pair("two"), pair("extra")]])
def test_response_must_cover_exact_local_candidate_set(items):
    with pytest.raises(ValueError):
        parse(items)


def test_candidate_names_in_later_blocks_cannot_replace_local_transport_ids():
    opener = Opener([response({"candidate_reviews": [pair("one")]})])
    content = copy.deepcopy(CONTENT)
    content.append({"type": "text", "text": json.dumps({"candidate_ids": ["one"]})})
    with pytest.raises(ReviewError) as error:
        DeepSeekClient(KEY, opener=opener).review(content)
    assert error.value.code == "invalid_decision" and len(opener.calls) == 1


def test_no_transport_metadata_means_no_network_call():
    opener = Opener([])
    with pytest.raises(ReviewError) as error:
        DeepSeekClient(KEY, opener=opener).review([{"type": "text", "text": "candidate IDs are in an image"}, *CONTENT[1:]])
    assert error.value.code == "invalid_input" and not opener.calls


def test_raw_pair_diagnostics_redact_key_even_when_response_is_inconsistent():
    result = parse([pair("one", reason=KEY, differences=[KEY]), pair("two", "different")])
    assert result["verdict"] == "uncertain" and KEY not in json.dumps(result)


def test_old_ambiguous_global_verdict_schema_cannot_be_used_as_v2_pair_evidence():
    with pytest.raises(ValueError):
        DeepSeekClient(KEY)._decision({"verdict": "different", "candidate_id": "one", "reason": "one is identical",
            "checks": {**{key: True for key in PAIR_CHECKS}, "unique_candidate": True},
            "differences": ["two is different"]}, ["one", "two"])
