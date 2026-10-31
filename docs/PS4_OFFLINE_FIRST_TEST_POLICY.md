# PS4 testing: offline first

No experimental PKG installation is used to investigate tooling, package
format, generic compatibility, or an empty/diagnostic build. Continue those
checks locally and in CI with parsers, synthetic projects, independent readers,
package audits, and reproducible builds.

## When a physical test may be proposed

An installation is eligible for explicit owner review only in either case:

1. The private package already contains the first real graphical Ultimate
   Mod Menu, including its L1+R1 open/close path, and the offline identity,
   asset graph, Unity host, input logic, package structure, independent
   inspection, source-diff, base compatibility, and recovery checks pass.
2. A concrete intermediate question cannot be answered offline, the package
   has a measurable purpose, and a separately built and audited menu package
   is ready to be the direct next PS4 test. Explain why the intermediate test
   is indispensable and why its result cannot be obtained by another offline
   check.

Eligibility is never authorization. Before asking the owner to install, report
the package's exact function, completed offline checks, the PS4-only result,
expected visible behavior, failure modes and recovery steps, and whether the
next test is directly the graphical menu. If another fundamental blocker would
remain, do not propose the test.

Keep candidates and commercial source files outside Git. Prefer a patch under
100 MB when its format and base compatibility are actually verified; size is
not a reason to weaken structural or compatibility checks. Do not install,
modify console memory, run live hooks, or edit saves without separate explicit
authorization.

## Offline pre-proposal gate

Use `scripts/check_ps4_test_eligibility.py` with a private JSON manifest. The
manifest stays outside the repository and stores only local absolute package
paths plus SHA-256 digests. Referenced evidence reports must be non-commercial
files inside the repository and are pinned by SHA-256. The tool checks the
artifact identity, evidence-file integrity, required pass records, and policy
fields; it does not inspect PKG cryptography, prove the truth of reports, or
authorize installation. It prints only `BLOCKED` or
`ELIGIBLE_FOR_EXPLICIT_USER_REVIEW`, always with `install_authorized: false`.
The intermediate case additionally requires a ready, hashed next-menu package
and an explicit direct-next step of `first_menu_graphics_test`.

At the current project state there is no modified scene, no menu-containing
PKG, and no validated menu package for an intermediate test to follow. The
physical-test gate is therefore **BLOCKED**. The project remains offline-only.

For `first_menu`, the manifest uses a package record with `path`, `sha256`,
`function`, `contains_graphical_ucm: true`, and
`contains_l1_r1_open_close: true`. Each required check is an object with
`result: "PASS"`, a repository-relative text `report`, and that report's
`sha256`. It also requires concrete `physical_question`, `expected_result`, and
`failure_recovery` fields. The required check names are `target_identity`,
`package_structure`, `independent_package_inspection`, `source_diff_audit`,
`recovery_plan`, `base_compatibility`, `unity_asset_graph`,
`unity_render_host`, and `l1_r1_input_logic`. For an intermediate proposal, use
`test_kind: "indispensable_intermediate"`, provide the written fields
`why_indispensable`, `why_offline_cannot_answer`, `measurable_result`, and
`failure_recovery`, then include the direct next menu package plus its
menu-specific offline evidence. Keep the manifest and both PKGs outside the
repository.

## Required report for a future proposal

- Package purpose and actual menu contents.
- Source/title/version identity, package structural checks, independent
  package inspection, and exact allowed file changes.
- Unity object/PPtr/dependency validation and evidence that the scene-owned
  graphical host is serializable and callable.
- Offline L1+R1 chord tests, including gameplay-open and gameplay-closed cases.
- Compatibility basis for the intended CUSA12398 1.15 installation target.
- Recovery procedure using the known-good original game package; do not alter
  saves. No install starts until the owner explicitly approves it.
