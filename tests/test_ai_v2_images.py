"""Measured-coordinate image aids never replace complete source evidence."""
import base64
from io import BytesIO
import json

import numpy as np
from PIL import Image, ImageDraw
import pytest

from hsd_tool.ai_images import _alignment_content, prepare_content
from test_ai_policy import make_job
from hsd_tool.ai_policy import select_review_case


def decoded(content):
    return [Image.open(BytesIO(base64.b64decode(block["image_url"]["url"].split(",", 1)[1]))).convert("RGB")
            for block in content if block["type"] == "image_url"]


def test_neutral_prompt_does_not_prime_model_with_old_failure_reason(tmp_path):
    row, rows, files = make_job(tmp_path)
    row["reason"] = "untrusted-local-verdict: colour differs therefore reject"
    case = select_review_case(row, rows, files)
    content = prepare_content(case, row, files)
    instruction = json.loads(content[0]["text"])
    text = " ".join(block["text"] for block in content if block["type"] == "text")
    assert "untrusted-local-verdict" not in text and "local_question" not in instruction
    assert instruction["candidate_ids"] == case["candidate_ids"]
    assert "candidate_reviews" in text and "其它候选" in text
    assert len(decoded(content)) <= 40 and len(content) <= 80
    assert "本机几何对照" in text


def test_same_scale_auxiliary_keeps_actual_content_differences(tmp_path):
    row, rows, files = make_job(tmp_path)
    candidate = Image.open(files[0]["preview_path"]).convert("RGB")
    ImageDraw.Draw(candidate).rectangle((10, 10, 30, 25), fill="blue")
    candidate.save(files[0]["preview_path"])
    case = select_review_case(row, rows, files)
    aids = decoded(_alignment_content(case, row, files[0]))
    pair = aids[0]
    # Query remains red; the mapped candidate's actual changed patch is blue.
    assert pair.getpixel((30, 45)) == (255, 0, 0)
    assert pair.getpixel((30, 190)) == (0, 0, 255)
    assert len(aids) == 2


@pytest.mark.parametrize("mutation", [
    {"geometry_verified": False}, {"direction": "query_to_candidate"},
    {"matrices": [[[0., 0., 0.], [0., 0., 0.]]]},
    {"candidate_size": [10, 1000]}, {"matrices": [[[float("nan"), 0., 0.], [0., 1., 0.]]]},
])
def test_unverified_or_malformed_geometry_never_generates_an_alignment_aid(tmp_path, mutation):
    row, rows, files = make_job(tmp_path)
    row["evidence"]["alignment"].update(mutation)
    case = select_review_case(row, rows, files)
    assert _alignment_content(case, row, files[0]) == []


def test_crop_cannot_hide_extra_art_even_if_metadata_calls_it_a_margin(tmp_path):
    row, rows, files = make_job(tmp_path)
    row["evidence"]["alignment"]["body_bounds"] = [10, 0, 240, 60]
    # Source outside the proposed crop is red artwork, not a white margin.
    case = select_review_case(row, rows, files)
    assert _alignment_content(case, row, files[0]) == []
    content = prepare_content(case, row, files)
    images = decoded(content)
    assert any(image.size == (240, 60) and image.getpixel((0, 0)) == (255, 0, 0) for image in images)


def test_only_explicit_supported_repeat_transforms_are_rendered(tmp_path):
    tile = Image.new("RGB", (200, 100), "white")
    ImageDraw.Draw(tile).rectangle((30, 25, 60, 50), fill="purple")
    query = Image.new("RGB", (400, 100), "white")
    query.paste(tile, (0, 0)); query.paste(tile, (200, 0))
    query_path, preview = tmp_path / "query.png", tmp_path / "tile.png"
    query.save(query_path); tile.save(preview)
    alignment = {"kind": "periodic", "direction": "candidate_to_query", "geometry_verified": True,
                 "query_size": [400, 100], "candidate_size": [200, 100],
                 "matrices": [[[1., 0., 0.], [0., 1., 0.]]],
                 "query_coverage": .5, "candidate_coverage": 1., "candidate_ink_coverage": 1.}
    case = {"image_digests": {"alignment_evidence": alignment}}
    row, file = {"image_path": str(query_path)}, {"id": "candidate", "preview_path": str(preview)}
    pair = decoded(_alignment_content(case, row, file))[0]
    assert pair.getpixel((240, 180)) == (220, 220, 220)  # no inferred second tile
    alignment["matrices"].append([[1., 0., 200.], [0., 1., 0.]])
    pair = decoded(_alignment_content(case, row, file))[0]
    assert pair.getpixel((240, 180)) == (128, 0, 128)
