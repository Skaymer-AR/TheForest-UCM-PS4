#!/usr/bin/env python3
"""Fail-closed offline gate for proposing (never authorizing) a PS4 test.

The manifest references private PKGs by local path and SHA-256. It must stay
outside Git. Evidence reports must be committed, non-commercial metadata files
inside the repository and are checked by hash. This script checks policy
completeness and byte identity; it cannot prove that a report's claims are
true, validate a PKG cryptographically, authorize an installation, or replace
human review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TEXT_EVIDENCE_SUFFIXES = {".md", ".json", ".txt", ".yaml", ".yml"}
BASE_CHECKS = (
    "target_identity",
    "package_structure",
    "independent_package_inspection",
    "source_diff_audit",
    "recovery_plan",
)
MENU_CHECKS = BASE_CHECKS + (
    "base_compatibility",
    "unity_asset_graph",
    "unity_render_host",
    "l1_r1_input_logic",
)


class GateError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise GateError(f"{label}: expected a lowercase SHA-256 digest")
    return value


def _check_artifact(record: object, repo_root: Path, label: str) -> Path:
    if not isinstance(record, dict):
        raise GateError(f"{label}: artifact record is missing")
    raw_path = record.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise GateError(f"{label}: private artifact path is missing")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise GateError(f"{label}: private artifact path must be absolute")
    if path.is_symlink() or not path.is_file():
        raise GateError(f"{label}: artifact is not a regular file")
    resolved = path.resolve()
    if _is_within(resolved, repo_root):
        raise GateError(f"{label}: private package must remain outside the Git tree")
    if path.suffix.lower() != ".pkg":
        raise GateError(f"{label}: artifact must have a .pkg extension")
    expected = _validate_digest(record.get("sha256"), f"{label} SHA-256")
    try:
        actual = sha256_file(resolved)
    except OSError as exc:
        raise GateError(f"{label}: artifact cannot be read ({exc.strerror})") from None
    if actual != expected:
        raise GateError(f"{label}: artifact SHA-256 does not match the manifest")
    return resolved


def _check_evidence(checks: object, required: tuple[str, ...], repo_root: Path) -> list[str]:
    if not isinstance(checks, dict):
        raise GateError("offline_checks must be an object")
    missing: list[str] = []
    for name in required:
        record = checks.get(name)
        if not isinstance(record, dict) or record.get("result") != "PASS":
            missing.append(name)
            continue
        raw_path = record.get("report")
        if not isinstance(raw_path, str) or not raw_path:
            missing.append(name)
            continue
        report = Path(raw_path)
        if report.is_absolute():
            missing.append(name)
            continue
        parts = report.parts
        if any(part in ("", ".", "..") for part in parts):
            missing.append(name)
            continue
        report_path = repo_root / report
        if report_path.is_symlink() or not report_path.is_file():
            missing.append(name)
            continue
        if report_path.suffix.lower() not in TEXT_EVIDENCE_SUFFIXES:
            missing.append(name)
            continue
        try:
            if not _is_within(report_path.resolve(), repo_root):
                missing.append(name)
                continue
            expected = _validate_digest(record.get("sha256"), f"{name} evidence SHA-256")
            if sha256_file(report_path) != expected:
                missing.append(name)
        except (OSError, GateError):
            missing.append(name)
    return missing


def evaluate(manifest: object, repo_root: Path) -> dict:
    """Return eligibility for human review. This never grants install approval."""
    result = {"schema": 1, "decision": "BLOCKED", "install_authorized": False,
              "reasons": []}
    try:
        if not isinstance(manifest, dict) or manifest.get("schema") != 1:
            raise GateError("manifest schema must be 1")
        kind = manifest.get("test_kind")
        if kind not in ("first_menu", "indispensable_intermediate"):
            raise GateError("test_kind must be first_menu or indispensable_intermediate")
        artifact = _check_artifact(manifest.get("package"), repo_root, "candidate package")
        del artifact  # Keep private paths out of the report.
        package = manifest["package"]
        if not isinstance(package.get("function"), str) or not package["function"].strip():
            raise GateError("package function must be stated")

        if kind == "first_menu":
            if package.get("contains_graphical_ucm") is not True:
                raise GateError("candidate does not declare the first graphical UCM")
            if package.get("contains_l1_r1_open_close") is not True:
                raise GateError("candidate does not declare the L1+R1 menu path")
            for field in ("physical_question", "expected_result", "failure_recovery"):
                value = manifest.get(field)
                if not isinstance(value, str) or len(value.strip()) < 30:
                    raise GateError(f"physical-test proposal requires a concrete {field}")
            missing = _check_evidence(manifest.get("offline_checks"), MENU_CHECKS, repo_root)
            if missing:
                raise GateError("offline evidence is missing or stale: " + ", ".join(missing))
        else:
            intermediate = manifest.get("intermediate")
            if not isinstance(intermediate, dict):
                raise GateError("intermediate-test rationale is missing")
            for field in ("why_indispensable", "why_offline_cannot_answer",
                          "measurable_result", "failure_recovery"):
                value = intermediate.get(field)
                if not isinstance(value, str) or len(value.strip()) < 30:
                    raise GateError(f"intermediate rationale requires a concrete {field}")
            if intermediate.get("direct_next_step") != "first_menu_graphics_test":
                raise GateError("the direct next step must be the first menu graphics test")
            if intermediate.get("menu_candidate_ready") is not True:
                raise GateError("the direct-next menu package is not declared ready")
            _check_artifact(intermediate.get("menu_package"), repo_root,
                            "direct-next menu package")
            missing = _check_evidence(manifest.get("offline_checks"), BASE_CHECKS, repo_root)
            missing += _check_evidence(intermediate.get("menu_offline_checks"), MENU_CHECKS,
                                       repo_root)
            if missing:
                raise GateError("offline evidence is missing or stale: " + ", ".join(missing))

        result["decision"] = "ELIGIBLE_FOR_EXPLICIT_USER_REVIEW"
        result["reasons"] = [
            "manifest and referenced evidence files passed integrity/policy checks",
            "this result is not permission to install or run the package",
        ]
    except (GateError, KeyError, OSError) as exc:
        result["reasons"] = [str(exc)]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repo-root", type=Path,
                        default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    try:
        repo_root = args.repo_root.resolve()
        manifest_path = args.manifest.expanduser().resolve()
        if _is_within(manifest_path, repo_root):
            raise GateError("private manifest must remain outside the Git tree")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        report = evaluate(manifest, repo_root)
    except GateError as exc:
        report = {"schema": 1, "decision": "BLOCKED", "install_authorized": False,
                  "reasons": [str(exc)]}
    except (OSError, json.JSONDecodeError) as exc:
        report = {"schema": 1, "decision": "BLOCKED", "install_authorized": False,
                  "reasons": [f"cannot read manifest ({type(exc).__name__})"]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["decision"] == "ELIGIBLE_FOR_EXPLICIT_USER_REVIEW" else 2


if __name__ == "__main__":
    sys.exit(main())
