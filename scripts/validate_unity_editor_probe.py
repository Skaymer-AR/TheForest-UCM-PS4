#!/usr/bin/env python3
"""Validate output from the licensed Unity 5.6.6f2 serialization probe.

The fixture-only unit tests exercise the validators, not Unity. A real report
is accepted only when it says UnityEditor produced and reloaded the scene and
prefab, and all copied artifacts match their reported hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_unity_rewired_assets import Asset  # noqa: E402

UNITY_VERSION = "5.6.6f2"
CLASSDATA_SHA256 = "129e1f80f930415db6779fe6089afa75280cb51462bcee812beab6cd81a764c6"
EXPECTED_VARIANTS = {
    "baseline": "",
    "int-value": "intValue",
    "bool-value": "boolValue",
    "float-value": "floatValue",
    "string-value": "stringValue",
    "enum-value": "mode",
    "vector-value": "vectorValue",
    "color-value": "colorValue",
    "object-reference": "referenceTarget",
    "nested-state-field": "states[1].action.label",
}
SNAPSHOT_KEYS = {
    "intValue", "boolValue", "floatValue", "stringValue", "mode",
    "vectorX", "vectorY", "vectorZ", "colorR", "colorG", "colorB",
    "colorA", "rootX", "rootY", "rootZ", "referenceTarget", "targetAId",
    "targetBId", "stateCount", "firstState", "firstStateId",
    "firstTransitionEvent", "firstTransitionTarget", "firstActionKind",
    "firstActionLabel", "firstActionScalar", "secondState", "secondStateId",
    "secondTransitionEvent", "secondTransitionTarget", "nestedActionKind",
    "nestedActionLabel", "nestedActionScalar",
}
BASELINE = {
    "intValue": 101,
    "boolValue": True,
    "floatValue": 1.25,
    "stringValue": "baseline",
    "mode": "Closed",
    "vectorX": 1.25,
    "vectorY": -2.5,
    "vectorZ": 3.75,
    "colorR": 0.1,
    "colorG": 0.2,
    "colorB": 0.3,
    "colorA": 1.0,
    "rootX": 1.25,
    "rootY": -2.5,
    "rootZ": 3.75,
    "referenceTarget": "SyntheticTargetA",
    "targetAId": 1,
    "targetBId": 2,
    "stateCount": 2,
    "firstState": "Closed",
    "firstStateId": 0,
    "firstTransitionEvent": "Open",
    "firstTransitionTarget": "Main",
    "firstActionKind": "Input",
    "firstActionLabel": "SyntheticOpenAction",
    "firstActionScalar": 0.0,
    "secondState": "Main",
    "secondStateId": 1,
    "secondTransitionEvent": "Close",
    "secondTransitionTarget": "Closed",
    "nestedActionKind": "Display",
    "nestedActionLabel": "Observe",
    "nestedActionScalar": 2.5,
}
MUTATIONS = {
    "int-value": {"intValue": 202},
    "bool-value": {"boolValue": False},
    "float-value": {"floatValue": 9.5},
    "string-value": {"stringValue": "changed-string"},
    "enum-value": {"mode": "Open"},
    "vector-value": {"vectorX": 7.0, "vectorY": 8.0, "vectorZ": 9.0},
    "color-value": {"colorR": 0.9, "colorG": 0.8, "colorB": 0.7, "colorA": 0.6},
    "object-reference": {"referenceTarget": "SyntheticTargetB"},
    "nested-state-field": {"nestedActionLabel": "Navigate"},
}


def fail(message: str) -> None:
    raise ValueError(message)


def _safe_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        fail("artifact path escapes the output directory")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved == resolved_root or resolved_root not in resolved.parents:
        fail("artifact path escapes the output directory")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _float_equal(left: object, right: object) -> bool:
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and abs(left - right) <= 0.0001


def expected_snapshot(name: str) -> dict:
    if name not in EXPECTED_VARIANTS:
        fail("unknown probe variant")
    result = dict(BASELINE)
    result.update(MUTATIONS.get(name, {}))
    return result


def changed_snapshot_fields(before: dict, after: dict) -> set[str]:
    if set(before) != SNAPSHOT_KEYS or set(after) != SNAPSHOT_KEYS:
        fail("snapshot field set differs from the pinned probe schema")
    changed = set()
    for key in SNAPSHOT_KEYS:
        left, right = before[key], after[key]
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if not _float_equal(left, right):
                changed.add(key)
        elif left != right:
            changed.add(key)
    return changed


def _verify_unity_yaml(path: Path, snapshot: dict) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name} is not Unity text serialization") from exc
    if not text.startswith("%YAML 1.1\n") or "%TAG !u! tag:unity3d.com,2011:" not in text:
        fail(f"{path.name} is not a ForceText Unity scene/prefab")
    for marker in ("--- !u!1 &", "--- !u!4 &", "--- !u!114 &"):
        if marker not in text:
            fail(f"{path.name} is missing Unity document {marker}")
    for field in ("intValue:", "boolValue:", "floatValue:", "stringValue:",
                  "mode:", "vectorValue:", "colorValue:", "referenceTarget:", "states:"):
        if field not in text:
            fail(f"{path.name} is missing serialized probe field {field}")
    if "UCM_SERIALIZATION_PROBE_ROOT" not in text:
        fail(f"{path.name} is missing the synthetic root GameObject")
    for value in (snapshot["stringValue"], snapshot["firstState"],
                  snapshot["nestedActionLabel"], snapshot["referenceTarget"]):
        if str(value) not in text:
            fail(f"{path.name} does not contain a serialized expected string value")


def validate_editor_report(output_dir: Path) -> dict:
    report_path = output_dir / "unity-editor-report.json"
    if not report_path.is_file():
        fail("Unity Editor report is missing; no Editor result can be claimed")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("generatedBy") != "UnityEditor":
        fail("report is not marked as generated by Unity Editor")
    if report.get("unityVersion") != UNITY_VERSION:
        fail("Editor version is not exactly 5.6.6f2")
    if report.get("serializationMode") != "ForceText":
        fail("Unity Editor did not save text-mode scenes/prefabs")
    if report.get("syntheticOnly") is not True or report.get("capturedAfterSaveAndReload") is not True:
        fail("report does not attest a synthetic save/reload check")
    if report.get("expectedSerializedFileFormat") != 17:
        fail("report has an unexpected expected-format marker")
    if not report.get("buildTarget") or "PS4" in report.get("buildTarget", "").upper():
        fail("the generic serialization probe must not target a PS4 build")

    variants = report.get("variants")
    if not isinstance(variants, list) or [v.get("name") for v in variants] != list(EXPECTED_VARIANTS):
        fail("probe variants are incomplete, duplicated, or out of order")
    snapshots = {}
    for variant in variants:
        name = variant["name"]
        if variant.get("changedField") != EXPECTED_VARIANTS[name]:
            fail(f"{name} declares an unexpected changed field")
        snapshot = variant.get("snapshot")
        if not isinstance(snapshot, dict) or set(snapshot) != SNAPSHOT_KEYS:
            fail(f"{name} snapshot schema is incomplete")
        expected = expected_snapshot(name)
        for key in SNAPSHOT_KEYS:
            if isinstance(expected[key], (int, float)):
                if not _float_equal(snapshot[key], expected[key]):
                    fail(f"{name} snapshot value mismatch for {key}")
            elif snapshot[key] != expected[key]:
                fail(f"{name} snapshot value mismatch for {key}")
        snapshots[name] = snapshot

        for role, suffix in (("scene", ".unity"), ("prefab", ".prefab"), ("bundle", "")):
            relative = variant.get(role + "Path")
            digest = variant.get(role + "Sha256")
            size = variant.get(role + "Bytes")
            if not isinstance(relative, str) or not relative:
                fail(f"{name} {role} path is missing")
            artifact = _safe_file(output_dir, relative)
            if not artifact.is_file():
                fail(f"{name} {role} artifact does not exist")
            if not isinstance(size, int) or size <= 0 or artifact.stat().st_size != size:
                fail(f"{name} {role} byte count mismatch")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                fail(f"{name} {role} hash is malformed")
            if _sha256(artifact) != digest:
                fail(f"{name} {role} SHA-256 mismatch")
            if role in ("scene", "prefab"):
                _verify_unity_yaml(artifact, snapshot)
                meta = Path(str(artifact) + ".meta")
                if not meta.is_file():
                    fail(f"{name} {role} Unity .meta file is missing")

    baseline = snapshots["baseline"]
    for name, expected_field in EXPECTED_VARIANTS.items():
        if name == "baseline":
            continue
        changed = changed_snapshot_fields(baseline, snapshots[name])
        expected_snapshot_key = {
            "states[1].action.label": "nestedActionLabel",
        }.get(expected_field, expected_field)
        if expected_field in ("vectorValue", "colorValue"):
            expected_changed = {key for key in changed if key.startswith(
                "vector" if expected_field == "vectorValue" else "color")}
            other_changes = changed - expected_changed
            if not expected_changed or other_changes:
                fail(f"{name} did not isolate the {expected_field} mutation")
        elif changed != {expected_snapshot_key}:
            fail(f"{name} changed snapshot fields outside {expected_field}")

    return report


def _transform(asset: Asset, path_id: int) -> dict:
    blob = asset.obj(path_id)
    if len(blob) < 68:
        fail("AssetsTools extracted a short Transform object")
    go_file, go_id = struct.unpack_from("<iq", blob, 0)
    children = struct.unpack_from("<i", blob, 52)[0]
    if children < 0 or children > 128:
        fail("Transform child count is outside the probe limit")
    first_child = 56
    father_at = first_child + children * 12
    if father_at + 12 > len(blob):
        fail("Transform child PPtrs exceed the object")
    child_refs = [struct.unpack_from("<iq", blob, first_child + i * 12) for i in range(children)]
    father = struct.unpack_from("<iq", blob, father_at)
    return {"gameObject": (go_file, go_id), "children": child_refs, "father": father}


def compare_assetstools_file(extracted_path: Path, report_path: Path,
                             expected_bundle_sha256: str) -> dict:
    summary = json.loads(report_path.read_text(encoding="utf-8"))
    if summary.get("formatVersion") != 17 or summary.get("unityVersion") != UNITY_VERSION:
        fail("AssetsTools.NET did not read Unity 5.6.6f2 serialized format 17")
    if summary.get("typeTreeEnabled") is not False:
        fail("Editor probe bundle must contain a type-tree-free fixture for the pinned Python reader")
    if summary.get("bundleSha256") != expected_bundle_sha256:
        fail("AssetsTools.NET report does not describe the Editor-reported bundle bytes")
    if summary.get("assetFileBytes") != extracted_path.stat().st_size:
        fail("AssetsTools.NET extracted-file byte count differs from the file it wrote")

    asset = Asset(extracted_path)
    py_objects = [
        {"pathId": path_id, "classId": info.class_id,
         "sha256": hashlib.sha256(asset.obj(path_id)).hexdigest()}
        for path_id, info in sorted(asset.objects.items())
    ]
    if py_objects != summary.get("objects"):
        fail("Python format-17 parser and AssetsTools.NET object tables/raw hashes differ")
    if asset.version != summary.get("unityVersion"):
        fail("Python and AssetsTools.NET Unity version strings differ")

    py_game_objects = []
    for path_id in asset.ids(1):
        obj = asset.gameobject(path_id)
        components = [{"fileId": file_id, "pathId": target}
                      for file_id, target in obj["components"]]
        for link in components:
            if link["fileId"] != 0 or link["pathId"] not in asset.objects:
                fail("GameObject contains an unresolved local component PPtr")
        py_game_objects.append({"pathId": path_id, "name": obj["name"],
                                "active": obj["active"], "components": components})
    py_game_objects.sort(key=lambda item: item["pathId"])
    if py_game_objects != summary.get("gameObjects"):
        fail("Python and AssetsTools.NET GameObject records differ")
    if not any(row["name"] == "UCM_SERIALIZATION_PROBE_ROOT" for row in py_game_objects):
        fail("extracted asset file has no synthetic root GameObject")

    py_transforms = []
    for path_id in asset.ids(4):
        value = _transform(asset, path_id)
        go_file, go_id = value["gameObject"]
        if go_file != 0 or go_id not in asset.objects or asset.objects[go_id].class_id != 1:
            fail("Transform owner PPtr does not resolve to a GameObject")
        for file_id, child_id in value["children"]:
            if file_id != 0 or child_id not in asset.objects or asset.objects[child_id].class_id != 4:
                fail("Transform child PPtr does not resolve to a Transform")
        father_file, father_id = value["father"]
        if father_id and (father_file != 0 or father_id not in asset.objects or
                          asset.objects[father_id].class_id != 4):
            fail("Transform father PPtr does not resolve to a Transform")
        py_transforms.append({"pathId": path_id, "gameObjectFileId": go_file,
                              "gameObjectPathId": go_id,
                              "childPathIds": [item[1] for item in value["children"]],
                              "fatherFileId": father_file, "fatherPathId": father_id})
    py_transforms.sort(key=lambda item: item["pathId"])
    if py_transforms != summary.get("transforms"):
        fail("Python and AssetsTools.NET Transform ownership/hierarchy records differ")

    py_monos = []
    for path_id in asset.ids(114):
        value = asset.mono(path_id)
        if value["game_file"] != 0 or value["game_id"] not in asset.objects or \
                asset.objects[value["game_id"]].class_id != 1:
            fail("MonoBehaviour owner PPtr does not resolve to a GameObject")
        if value["script_file"] != 0 and asset.external(value["script_file"]) is None:
            fail("MonoBehaviour script PPtr has an invalid external file ID")
        py_monos.append({"pathId": path_id, "enabled": value["enabled"],
                         "gameObjectFileId": value["game_file"],
                         "gameObjectPathId": value["game_id"],
                         "scriptFileId": value["script_file"],
                         "scriptPathId": value["script_id"]})
    py_monos.sort(key=lambda item: item["pathId"])
    if py_monos != summary.get("monoBehaviours"):
        fail("Python and AssetsTools.NET MonoBehaviour base records differ")
    if not any(item["enabled"] for item in py_monos):
        fail("extracted asset file contains no enabled synthetic MonoBehaviour")

    return {"format": 17, "unityVersion": asset.version,
            "objectCount": len(asset.objects),
            "classCounts": {str(class_id): len(asset.ids(class_id))
                            for class_id in sorted(asset.byclass)},
            "pythonAssetToolsAgreement": True}


def run_assetstools(output_dir: Path, report: dict, classdata: Path,
                    validator_dll: Path, dotnet: str) -> list[dict]:
    if not classdata.is_file():
        fail("classdata.tpk is missing; obtain the pinned open UABEA v8 database")
    if _sha256(classdata) != CLASSDATA_SHA256:
        fail("classdata.tpk SHA-256 differs from the pinned UABEA v8 database")
    if not validator_dll.is_file():
        fail("AssetsTools.NET validator DLL is missing; build its project first")
    result_dir = output_dir / "assets-tools"
    extracted_dir = result_dir / "extracted"
    result_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in report["variants"]:
        name = variant["name"]
        bundle = _safe_file(output_dir, variant["bundlePath"])
        extracted = extracted_dir / (name + ".assets")
        summary_path = result_dir / (name + ".json")
        command = [dotnet, str(validator_dll), "editor-bundle", str(classdata),
                   str(bundle), str(extracted), str(summary_path)]
        subprocess.run(command, cwd=ROOT, check=True)
        result = compare_assetstools_file(extracted, summary_path, variant["bundleSha256"])
        result["variant"] = name
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--classdata-tpk", type=Path)
    parser.add_argument("--validator-dll", type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    args = parser.parse_args()
    try:
        output_dir = args.output_dir.resolve()
        report = validate_editor_report(output_dir)
        print("Unity Editor output: PASS (actual report marker, hashes, YAML, save/reload snapshots)")
        if args.classdata_tpk or args.validator_dll:
            if not args.classdata_tpk or not args.validator_dll:
                fail("both --classdata-tpk and --validator-dll are required for AssetsTools.NET comparison")
            results = run_assetstools(output_dir, report, args.classdata_tpk.resolve(),
                                      args.validator_dll.resolve(), args.dotnet)
            print("Python format-17 parser ↔ AssetsTools.NET: PASS (" +
                  str(len(results)) + " Unity Editor bundles)")
        else:
            print("AssetsTools.NET comparison: NOT RUN")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print("Unity Editor probe validation failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
