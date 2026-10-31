#!/usr/bin/env python3
"""Run the real Unity 5.6.6f2 Editor stage without requiring .NET.

This is the machine-local stage for licensed Windows/macOS installations. It
creates and reloads the synthetic scene/prefab outputs through Unity itself,
then checks the report, YAML and hashes with the repository's Python parser.
AssetsTools.NET remains pending and must be run on a compatible .NET host.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "prototype" / "Unity56SerializationProject"
EXPECTED_VERSION = "5.6.6f2"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--editor", default=os.environ.get("UNITY_566F2_EDITOR"),
                        help="licensed Unity 5.6.6f2 Editor executable")
    parser.add_argument("--output", type=Path, required=True,
                        help="new or empty directory outside this repository")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    try:
        if not args.editor:
            raise ValueError("set UNITY_566F2_EDITOR or pass --editor")
        editor = Path(args.editor).expanduser().resolve()
        if not editor.is_file():
            raise ValueError("Unity Editor executable does not exist")
        if os.name != "nt" and not os.access(editor, os.X_OK):
            raise ValueError("Unity Editor path is not executable")
        project_version = (PROJECT / "ProjectSettings" / "ProjectVersion.txt").read_text(encoding="utf-8")
        if "m_EditorVersion: " + EXPECTED_VERSION not in project_version:
            raise ValueError("synthetic project is not pinned to Unity " + EXPECTED_VERSION)
        output = args.output.expanduser().resolve()
        if output == ROOT or ROOT in output.parents:
            raise ValueError("Editor output must be outside the repository")
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise ValueError("Editor output directory must be empty")
        if args.timeout_seconds < 60 or args.timeout_seconds > 7200:
            raise ValueError("timeout must be between 60 and 7200 seconds")

        staged_project = output / "project"
        generated = output / "generated"
        shutil.copytree(PROJECT, staged_project)
        generated.mkdir()
        environment = os.environ.copy()
        environment["UCM_UNITY_PROBE_OUTPUT"] = str(generated)
        log_path = generated / "unity-editor.log"
        command = [str(editor), "-batchmode", "-nographics", "-quit",
                   "-projectPath", str(staged_project),
                   "-executeMethod", "UcmUnitySerializationProbe.SyntheticSerializationDriver.RunBatch",
                   "-logFile", str(log_path)]
        print("Launching the installed Unity Editor in batchmode for the synthetic project.")
        print("Editor version check is enforced by the Editor script; output is outside the repo.")
        completed = subprocess.run(command, cwd=str(ROOT), env=environment,
                                   timeout=args.timeout_seconds, check=False)
        if completed.returncode != 0:
            raise ValueError("Unity Editor exited with code " + str(completed.returncode) +
                             "; inspect the local Editor log, which is excluded from transfer")

        check = [sys.executable, str(ROOT / "scripts" / "validate_unity_editor_probe.py"), str(generated)]
        subprocess.run(check, cwd=str(ROOT), check=True)
        print("Unity-only stage complete. The full probe remains INCOMPLETE until AssetsTools.NET validates the bundles.")
        print("Editor log and temporary Unity project stay outside the repository and are excluded from transfer.")
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        print("Unity Editor stage failed or is unavailable: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
