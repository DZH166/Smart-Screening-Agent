"""Prepare frozen synthetic AI-first probes, without any network or API call.

Private experiment helper. Run once; an existing destination is never replaced.
These controls are not an independent business validation or an AI qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageOps
import pymupdf

from tools.run_ai_evaluation import _ambiguous_pair, _pattern, _pdf_ai

DEFAULT_OUT = ROOT / "tmp" / "deepseek_workflow_compare_01" / "synthetic-controls"
SEEDS = (684739, 927161, 358219, 792653, 143987, 561703, 831419)
SHUFFLE_SEED = 67183429
KINDS = ("scaled_positive", "reasonable_margin_positive", "colour_negative",
         "local_replacement_negative", "extra_content_negative",
         "shared_subset_negative", "low_resolution_ambiguous")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixel_sha(image):
    image = image.convert("RGB")
    prefix = json.dumps({"mode": image.mode, "size": image.size}, sort_keys=True).encode()
    return hashlib.sha256(prefix + image.tobytes()).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def definitions():
    """Every query has its own seed; absent-match originals stay out of the library."""
    cases = []
    for kind, seed in zip(KINDS, SEEDS):
        base = _pattern(seed)
        if kind == "scaled_positive":
            query = base.resize((768, 192), Image.Resampling.LANCZOS)
            candidates, expected_index = [base], 0
        elif kind == "reasonable_margin_positive":
            reduced = base.resize((768, 192), Image.Resampling.LANCZOS)
            query = ImageOps.expand(reduced, border=(24, 16, 24, 16), fill="white")
            candidates, expected_index = [base], 0
        elif kind == "colour_negative":
            query = base
            changed = Image.merge("RGB", (base.getchannel("B"), base.getchannel("R"), base.getchannel("G")))
            assert changed.tobytes() != base.tobytes()
            candidates, expected_index = [changed], None
        elif kind == "local_replacement_negative":
            query = base
            changed = base.copy()
            ImageDraw.Draw(changed).rectangle((430, 55, 585, 205), fill=(105, 105, 105),
                                             outline=(25, 25, 25), width=4)
            assert changed.tobytes() != base.tobytes()
            candidates, expected_index = [changed], None
        elif kind == "extra_content_negative":
            query = base
            changed = Image.new("RGB", (1024, 336), "white")
            changed.paste(base, (0, 0))
            ImageDraw.Draw(changed).polygon(((370, 270), (654, 270), (512, 326)), fill=(240, 30, 25))
            candidates, expected_index = [changed], None
        elif kind == "shared_subset_negative":
            query = base
            changed = _pattern(seed + 103)
            changed.paste(base.crop((0, 0, 256, 256)), (0, 0))
            assert changed.crop((0, 0, 256, 256)).tobytes() == base.crop((0, 0, 256, 256)).tobytes()
            assert changed.crop((256, 0, 1024, 256)).tobytes() != base.crop((256, 0, 1024, 256)).tobytes()
            candidates, expected_index = [changed], None
        else:
            query, first, second = _ambiguous_pair(base)
            assert first.tobytes() != second.tobytes()
            assert query.tobytes() == first.resize(query.size, Image.Resampling.BOX).tobytes()
            assert query.tobytes() == second.resize(query.size, Image.Resampling.BOX).tobytes()
            candidates, expected_index = [first, second], None
        cases.append((kind, seed, query, candidates, expected_index))
    return cases


def prepare(out):
    out = out.resolve()
    # Refuse reuse before writing anything, preserving previously frozen inputs.
    out.mkdir(parents=True, exist_ok=False)
    images_dir, sources_dir = out / "images", out / "sources"
    images_dir.mkdir()
    sources_dir.mkdir()
    rng = random.Random(SHUFFLE_SEED)
    identities = set()

    def identity(prefix):
        while True:
            value = prefix + f"{rng.getrandbits(64):016x}"
            if value not in identities:
                identities.add(value)
                return value

    queries, candidates, expected, controls, private_seeds = [], [], {}, {}, {}
    query_digests, candidate_digests, negative_query_digests = [], [], []
    ambiguous_check = None
    for kind, seed, query, pictures, expected_index in definitions():
        query_id = identity("q")
        query_path = images_dir / (query_id + ".png")
        query.save(query_path)
        queries.append({"id": query_id, "image_path": str(query_path)})
        query_digests.append(pixel_sha(query))
        controls[query_id], private_seeds[query_id] = kind, seed
        candidate_ids = []
        for picture in pictures:
            candidate_id = identity("c")
            candidate_ids.append(candidate_id)
            preview, source = images_dir / (candidate_id + ".png"), sources_dir / (candidate_id + ".ai")
            picture.save(preview)
            _pdf_ai(picture, source)
            with pymupdf.open(source) as document:
                assert len(document) == 1
                embedded = document.get_page_images(0, full=True)
                assert len(embedded) == 1
                pixmap = pymupdf.Pixmap(document, embedded[0][0])
                if pixmap.alpha:
                    pixmap = pymupdf.Pixmap(pixmap, 0)
                if pixmap.n != 3:
                    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
                embedded_picture = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                assert pixel_sha(embedded_picture) == pixel_sha(picture)
            digest = sha(source)
            assert len(digest) == 64 and source.is_file()
            candidates.append({"id": candidate_id, "image_path": str(preview), "source_path": str(source),
                               "source_sha256": digest, "page_count": 1, "issue": None})
            candidate_digests.append(pixel_sha(picture))
        expected[query_id] = candidate_ids[expected_index] if expected_index is not None else None
        if expected_index is None:
            negative_query_digests.append(pixel_sha(query))
        if kind == "low_resolution_ambiguous":
            ambiguous_check = {"query_id": query_id, "candidate_ids": candidate_ids,
                               "different_original_pixels": True,
                               "query_equals_both_box_reductions": True}

    assert len(queries) == 7 and len(candidates) == 8
    assert len(set(query_digests)) == len(query_digests)
    assert len(set(candidate_digests)) == len(candidate_digests)
    assert not set(query_digests).intersection(candidate_digests)
    assert not set(negative_query_digests).intersection(candidate_digests)
    assert len(set(expected.values()) - {None}) == 2
    rng.shuffle(queries)
    rng.shuffle(candidates)
    manifest = {"queries": queries, "candidates": candidates}
    labels = {"origin": "synthetic_known_truth", "expected": expected, "controls": controls}
    manifest_path, labels_path = out / "input-manifest.json", out / "labels.json"
    write_json(manifest_path, manifest)
    write_json(labels_path, labels)
    frozen_files = [path for path in out.rglob("*") if path.is_file()]
    freeze = {"schema_version": 1, "origin": "synthetic_known_truth", "real_api_calls": 0,
              "purpose": "AI-first negative probes; not independent business validation or qualification",
              "generator_sha256": sha(__file__),
              "shared_generator_sha256": sha(ROOT / "tools" / "run_ai_evaluation.py"),
              "shuffle_seed": SHUFFLE_SEED, "query_seeds": private_seeds,
              "checks": {"unique_query_pixels": True, "unique_candidate_pixels": True,
                         "no_exact_query_preview_duplicates": True, "valid_source_sha256": True,
                         "source_embedded_pixels_equal_preview": True, "negative_original_not_in_library": True,
                         "queries": 7, "candidates": 8, "positive_queries": 2,
                         "negative_queries": 4, "ambiguous_queries": 1,
                         "ambiguous": ambiguous_check},
              "files": {path.relative_to(out).as_posix(): sha(path) for path in sorted(frozen_files)}}
    write_json(out / "input-freeze.json", freeze)
    # Verify the completed freeze immediately; do not regenerate on later model outcomes.
    assert all(sha(out / name) == digest for name, digest in freeze["files"].items())
    print(json.dumps({"ok": True, "real_api_calls": 0, "queries": 7, "candidates": 8,
                      "manifest": str(manifest_path), "labels": str(labels_path),
                      "freeze": str(out / "input-freeze.json")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    prepare(parser.parse_args().out)
