from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compare_unity56_probe_runs import compare_runs  # noqa: E402
from package_unity56_editor_probe import extract, package  # noqa: E402
from validate_unity_editor_probe import (  # noqa: E402
    EXPECTED_VARIANTS,
    expected_snapshot,
    validate_editor_report,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_output(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "scenes").mkdir()
    (root / "prefabs").mkdir()
    (root / "bundles").mkdir()
    variants = []
    for name, changed in EXPECTED_VARIANTS.items():
        snapshot = expected_snapshot(name)
        yaml = (
            "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
            "--- !u!1 &1\nGameObject: UCM_SERIALIZATION_PROBE_ROOT\n"
            "--- !u!4 &2\nTransform: {}\n"
            "--- !u!114 &3\nMonoBehaviour:\n"
            f"  intValue: {snapshot['intValue']}\n"
            f"  boolValue: {int(snapshot['boolValue'])}\n"
            f"  floatValue: {snapshot['floatValue']}\n"
            f"  stringValue: {snapshot['stringValue']}\n"
            f"  mode: {snapshot['mode']}\n"
            "  vectorValue: {}\n  colorValue: {}\n"
            f"  referenceTarget: {snapshot['referenceTarget']}\n"
            "  states: []\n"
            f"  firstState: {snapshot['firstState']}\n"
            f"  nestedActionLabel: {snapshot['nestedActionLabel']}\n"
        )
        scene = root / "scenes" / (name + ".unity")
        prefab = root / "prefabs" / (name + ".prefab")
        bundle = root / "bundles" / ("ucm-probe-" + name)
        scene.write_text(yaml, encoding="utf-8")
        prefab.write_text(yaml, encoding="utf-8")
        (Path(str(scene) + ".meta")).write_text("fileFormatVersion: 2\n", encoding="ascii")
        (Path(str(prefab) + ".meta")).write_text("fileFormatVersion: 2\n", encoding="ascii")
        bundle.write_bytes(("synthetic bundle contract " + name).encode("ascii"))
        variants.append({
            "name": name,
            "changedField": changed,
            "scenePath": "scenes/" + name + ".unity",
            "sceneSha256": _sha(scene),
            "sceneBytes": scene.stat().st_size,
            "prefabPath": "prefabs/" + name + ".prefab",
            "prefabSha256": _sha(prefab),
            "prefabBytes": prefab.stat().st_size,
            "bundlePath": "bundles/ucm-probe-" + name,
            "bundleSha256": _sha(bundle),
            "bundleBytes": bundle.stat().st_size,
            "bundleDependencies": [],
            "snapshot": snapshot,
        })
    report = {
        "schemaVersion": 1,
        "generatedBy": "UnityEditor",
        "unityVersion": "5.6.6f2",
        "serializationMode": "ForceText",
        "buildTarget": "StandaloneWindows64",
        "syntheticOnly": True,
        "capturedAfterSaveAndReload": True,
        "expectedSerializedFileFormat": 17,
        "outputKinds": "Unity synthetic parser contract",
        "variants": variants,
    }
    (root / "unity-editor-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (root / "unity-editor.log").write_text("DO NOT TRANSFER: local-only log", encoding="utf-8")


class Unity56ProbeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_package_contains_allowlisted_synthetic_outputs_and_round_trips(self):
        source = self.root / "source"
        _write_output(source)
        archive = self.root / "probe.zip"
        digest = package(source, archive)
        self.assertEqual(_sha(archive), digest)
        self.assertTrue(Path(str(archive) + ".sha256").is_file())
        with zipfile.ZipFile(archive) as zipped:
            names = set(zipped.namelist())
        self.assertIn("probe-archive-manifest.json", names)
        self.assertIn("run-a/unity-editor-report.json", names)
        self.assertNotIn("run-a/unity-editor.log", names)
        destination = self.root / "restored"
        manifest = extract(archive, destination, digest)
        self.assertEqual(manifest["runCount"], 1)
        self.assertEqual(_sha(destination / "run-a/unity-editor-report.json"),
                         _sha(source / "unity-editor-report.json"))

    def test_repeat_package_compares_both_runs_exactly(self):
        first, second = self.root / "first", self.root / "second"
        _write_output(first)
        _write_output(second)
        archive = self.root / "repeat.zip"
        package(first, archive, second)
        destination = self.root / "repeat-restored"
        with zipfile.ZipFile(archive) as zipped:
            digest = _sha(archive)
            zipped.testzip()
        manifest = extract(archive, destination, digest)
        self.assertEqual(manifest["runCount"], 2)
        result = compare_runs(destination / "run-a", destination / "run-b")
        self.assertTrue(result["semanticEquivalent"])
        self.assertTrue(result["allArtifactHashesIdentical"])
        self.assertFalse(result["assetsToolsRowsCompared"])

    def test_comparison_reports_hash_difference_without_claiming_repeatability(self):
        first, second = self.root / "first", self.root / "second"
        _write_output(first)
        _write_output(second)
        target = second / "bundles" / "ucm-probe-baseline"
        target.write_bytes(b"different synthetic bundle bytes")
        report_path = second / "unity-editor-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["variants"][0]["bundleBytes"] = target.stat().st_size
        report["variants"][0]["bundleSha256"] = _sha(target)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        result = compare_runs(first, second)
        self.assertTrue(result["semanticEquivalent"])
        self.assertFalse(result["allArtifactHashesIdentical"])
        self.assertIn("bundles/ucm-probe-baseline", result["artifactHashDifferences"])

    def test_report_rejects_unresolved_assetbundle_dependency(self):
        source = self.root / "source"
        _write_output(source)
        path = source / "unity-editor-report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["variants"][0]["bundleDependencies"] = ["missing-bundle"]
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unresolved or self-referential"):
            validate_editor_report(source)

    def test_archive_rejects_wrong_digest_and_unlisted_member(self):
        source = self.root / "source"
        _write_output(source)
        archive = self.root / "probe.zip"
        package(source, archive)
        with self.assertRaisesRegex(ValueError, "differs from the supplied digest"):
            extract(archive, self.root / "bad-digest", "0" * 64)
        bad = self.root / "extra.zip"
        with zipfile.ZipFile(archive) as original, zipfile.ZipFile(bad, "w") as target:
            for info in original.infolist():
                target.writestr(info, original.read(info.filename))
            target.writestr("run-a/unity-editor.log", "not allowlisted")
        with self.assertRaisesRegex(ValueError, "archive contains missing or unlisted files"):
            extract(bad, self.root / "bad-extra", _sha(bad))

    def test_archive_rejects_path_traversal(self):
        archive = self.root / "traversal.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("../escaped", b"bad")
        with self.assertRaisesRegex(ValueError, "unsafe archive path"):
            extract(archive, self.root / "out", _sha(archive))


if __name__ == "__main__":
    unittest.main()
