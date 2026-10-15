"""Compare frozen synthetic matching cases without exposing labels to the matcher.

A dataset is an ignored local directory containing manifest.json and labels.json.
The manifest hashes every input and the labels before either implementation runs.
This measures a synthetic control set; it is not independent business accuracy and
does not qualify or activate AI review.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import ModuleType
import uuid


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _within(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Dataset path escapes its root.")
    return path


def verify_dataset(directory: str | Path) -> tuple[dict, dict]:
    root = Path(directory).resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "hsd-matching-generalization-1":
        raise ValueError("Unsupported frozen dataset schema.")
    if not manifest.get("frozen_at") or not manifest.get("cases"):
        raise ValueError("Dataset was not frozen with cases.")
    inputs = manifest.get("sha256")
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError("Frozen input hashes are required.")
    for relative, expected in inputs.items():
        path = _within(root, relative)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Frozen input has changed: {relative}")
    label_relative = manifest.get("labels", "labels.json")
    if label_relative not in inputs:
        raise ValueError("Labels must be hashed before matching.")
    labels = json.loads(_within(root, label_relative).read_text(encoding="utf-8"))
    records = labels.get("rows", [])
    label_keys = [(row["case_id"], row["row_id"]) for row in records]
    planned = [(case["id"], row["id"]) for case in manifest["cases"] for row in case["rows"]]
    if len(label_keys) != len(set(label_keys)) or set(label_keys) != set(planned):
        raise ValueError("Every planned row needs exactly one frozen label.")
    if len(planned) != len(set(planned)):
        raise ValueError("Case/row identities must be unique.")
    for case in manifest["cases"]:
        source = _within(root, case["source"])
        if not source.is_dir():
            raise ValueError("Each case needs a source folder.")
        for path in source.rglob("*"):
            if path.is_file() and path.relative_to(root).as_posix() not in inputs:
                raise ValueError("Unhashed source file.")
        for row in case["rows"]:
            image = row.get("image")
            if image and image not in inputs:
                raise ValueError("Every supplied query must be hashed.")
    return manifest, labels


def implementation_files(code_root: str | Path) -> dict[str, str | None]:
    """Bind both the entry point and its verification dependency, including absence."""
    root = Path(code_root).resolve()
    paths = ["hsd_tool/matching.py", "hsd_tool/matching_verification.py"]
    if not (root / paths[0]).is_file():
        raise ValueError("Cannot find hsd_tool/matching.py.")
    return {relative: digest(root / relative) if (root / relative).is_file() else None
            for relative in paths}


def _load_source(module_name: str, source: Path):
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {source.name}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    # Read the frozen source directly, avoiding an unrelated or stale .pyc cache.
    exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
    return module


def load_matching(code_root: str | Path):
    source = Path(code_root).resolve() / "hsd_tool" / "matching.py"
    package_name = "_hsd_generalization_" + uuid.uuid4().hex
    package = ModuleType(package_name)
    package.__path__ = [str(source.parent)]
    package.__package__ = package_name
    package.__spec__ = importlib.util.spec_from_loader(package_name, loader=None, is_package=True)
    sys.modules[package_name] = package
    try:
        helper = source.with_name("matching_verification.py")
        if helper.is_file():
            _load_source(package_name + ".matching_verification", helper)
        module = _load_source(package_name + ".matching", source)
    except Exception:
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_name + "."):
                del sys.modules[name]
        raise
    return module, source


def assess_match(match: dict, file_by_id: dict, label: dict) -> dict:
    """Apply labels only after production matching has completed."""
    status = match.get("status", "error")
    identity = match.get("file_id")
    selected = file_by_id.get(identity, {}).get("relative_path") if identity else None
    allowed = label.get("expected_files", [])
    positive = bool(allowed) and not label.get("auto_forbidden", False)
    false_auto = status == "auto" and (not positive or selected not in allowed)
    return {
        "status": status,
        "selected": selected,
        "positive": positive,
        "false_auto": false_auto,
        "correct_positive_auto": status == "auto" and positive and selected in allowed,
        "top_candidate": file_by_id.get(
            (match.get("candidates") or [{}])[0].get("file_id"), {}
        ).get("relative_path"),
        "reason": match.get("reason"),
        "evidence": match.get("evidence"),
        "diagnostics": match.get("diagnostics"),
    }


def run_dataset(directory: str | Path, code_root: str | Path, output: str | Path) -> dict:
    root = Path(directory).resolve()
    output = Path(output).resolve()
    # Results must not become a source file or overwrite frozen evidence.
    manifest, labels = verify_dataset(root)
    if output == root / "manifest.json" or output == root / manifest.get("labels", "labels.json"):
        raise ValueError("Output cannot overwrite frozen evidence.")
    if output.is_relative_to(root) and output.relative_to(root).as_posix() in manifest["sha256"]:
        raise ValueError("Output cannot overwrite a frozen input.")
    before_implementation = implementation_files(code_root)
    matching, source_path = load_matching(code_root)
    if implementation_files(code_root) != before_implementation:
        raise ValueError("Implementation changed during loading; results are invalid.")
    source_hash = hashlib.sha256(json.dumps(before_implementation, sort_keys=True).encode()).hexdigest()
    label_map = {(row["case_id"], row["row_id"]): row for row in labels["rows"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    work = output.parent / (output.stem + "_work")
    work.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    case_results = []
    for case in manifest["cases"]:
        # Families, controls, labels and expected identities never enter this call.
        rows = [{
            "id": row["id"], "row_number": index + 2, "number": "", "issue": row.get("issue"),
            "image_path": str(_within(root, row["image"])) if row.get("image") else None,
        } for index, row in enumerate(case["rows"])]
        case_started = time.perf_counter()
        try:
            result = matching.scan_and_match(
                str(_within(root, case["source"])), rows, str(work / case["id"])
            )
            files = {file["id"]: file for file in result["files"]}
            matches = {match["row_id"]: match for match in result["matches"]}
            case_error = None
        except Exception as exc:
            files, matches = {}, {}
            case_error = f"{type(exc).__name__}: {exc}"
        records = []
        for row in case["rows"]:
            label = label_map[(case["id"], row["id"])]
            record = assess_match(matches.get(row["id"], {"status": "error"}), files, label)
            record.update(row_id=row["id"])
            records.append(record)
        case_results.append({
            "case_id": case["id"], "family": case.get("family"), "batch_id": case.get("batch_id"),
            "control": case.get("control"), "seconds": round(time.perf_counter() - case_started, 6),
            "error": case_error, "rows": records,
        })
    seconds = time.perf_counter() - started
    # Mutation invalidates the complete run instead of silently changing labels.
    verify_dataset(root)
    if implementation_files(code_root) != before_implementation:
        raise ValueError("Implementation changed during validation; results are invalid.")
    rows = [row for case in case_results for row in case["rows"]]
    counts = Counter(row["status"] for row in rows)
    result = {
        "schema": "hsd-matching-generalization-result-1",
        "scope": "frozen_synthetic_controls_not_independent_business_accuracy",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "frozen_at": manifest["frozen_at"], "manifest_sha256": digest(root / "manifest.json"),
        "labels_sha256": manifest["sha256"][manifest.get("labels", "labels.json")],
        "implementation_sha256": source_hash,
        "implementation_fingerprint": "sha256_sorted_matching_and_verification_file_hashes_v1",
        "implementation_files": before_implementation,
        "cases": len(case_results), "rows": len(rows),
        "summary": {
            "auto": counts["auto"], "review": counts["review"], "unmatched": counts["unmatched"],
            "errors": counts["error"], "case_errors": sum(bool(case["error"]) for case in case_results),
            "false_auto": sum(row["false_auto"] for row in rows),
            "positive_rows": sum(row["positive"] for row in rows),
            "correct_positive_auto": sum(row["correct_positive_auto"] for row in rows),
            "seconds": round(seconds, 6),
        },
        "results": case_results,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Frozen local dataset directory")
    parser.add_argument("--code-root", default=".", help="Root containing hsd_tool/matching.py")
    parser.add_argument("--output", required=True, help="Local output JSON")
    args = parser.parse_args(argv)
    result = run_dataset(args.dataset, args.code_root, args.output)
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0 if result["summary"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
