# UNDERWOOD — PHASE INDEX

| Phase | Description | Date | Status |
|---|---|---:|---|
| Phase 0 | System Framing & Constraints: Defined Underwood as a controller-owned deterministic execution layer rather than an autonomous agent. Locked core principles: determinism, boundedness, auditability, controller authority, and fail-closed behavior. | TBD | CERTIFIED |
| Phase 1 | Minimal Controller Skeleton: Established the base controller loop and the initial interaction surface between agent, controller, and environment. | TBD | CERTIFIED |
| Phase 2 | Action / Observation Boundary: Formalized the separation between agent-produced actions and environment observations. | TBD | CERTIFIED |
| Phase 3 | Execution Loop Stabilization: Stabilized step progression and prevented uncontrolled looping. | TBD | CERTIFIED |
| Phase 4 | Validation & Control Hooks: Added controller-side validation points and intervention hooks. | TBD | CERTIFIED |
| Phase 5 | Bounded Mode Introduction: Introduced constrained execution mode with explicit controller-enforced limits. | TBD | CERTIFIED |
| Phase 6 | Control Layer Formalization: Certified deterministic bounded execution semantics: explicit stop reasons, immutable permission context, hard pre-execution turn ceiling, and snapshot isolation. | TBD | CERTIFIED |
| Phase 7 | Observability & Lifecycle: Added structured lifecycle visibility, including heartbeats, step deltas, and bounded audit payload foundation. | TBD | CERTIFIED |
| Phase 8 | Multi-Task Composition: Added deterministic controller-owned task sequencing and task-boundary reset semantics. | TBD | CERTIFIED |
| Phase 9 | Sequence Execution Activation: Enabled automatic progression across tasks with fail-fast behavior and sequence-level boundedness. | TBD | CERTIFIED |
| Phase 10 | Replayable Sequence Runs: Added sequence snapshots, replay boundaries, and replay-verification surfaces. | TBD | CERTIFIED |
| Phase 11 | Deterministic Sequence Simulation: Added isolated simulation state, simulated boundaries, projected budget usage, and structured simulation audit. | TBD | CERTIFIED |
| Phase 12 | Pre-Execution Decision Gating: Added deterministic admission control before execution begins, including gate refusal and simulation-driven go/no-go decisions. | TBD | CERTIFIED |
| Phase 13 | Graph Execution Foundations: Added graph-aware execution foundations, including task graph handling, next-node selection, graph-path simulation, and graph-aware gating hooks. | TBD | CERTIFIED |
| Phase 14A | Live Graph Traversal Integration: Integrated graph-aware traversal into the live execution path. | TBD | CERTIFIED |
| Phase 14B | Graph-Aware Boundary Reset: Certified deterministic boundary reset behavior across graph execution steps. | TBD | CERTIFIED |
| Phase 14C | Executed Path Lineage Telemetry: Added `_executed_path` lineage telemetry for live graph runs. | TBD | CERTIFIED |
| Phase 14D | Terminal Path Certification: Certified `terminal_path` / `path_terminal` audit fields. | TBD | CERTIFIED |
| Phase 15A | Gating Reason Mapping: Added passive operator diagnostics for gate decisions. | TBD | CERTIFIED |
| Phase 15B | Projection Summaries: Added operator-facing projection summaries without changing execution behavior. | TBD | CERTIFIED |
| Phase 15C | Path Divergence Monitoring: Added passive divergence visibility for operator review. | TBD | CERTIFIED |
| Phase 15D | Unified Terminal Audit Event Loop: Unified audit/event diagnostics into an operator-legible terminal surface. | TBD | CERTIFIED |
| Phase 16A | Graph Admission Contract: Defined admissible external graph payload structure under controller authority. | TBD | CERTIFIED |
| Phase 16B | Graph Injection Mechanism: Added deterministic graph injection after controller-side acceptance. | TBD | CERTIFIED |
| Phase 16C | Graph-Aware Simulation Integration: Integrated admitted graphs with deterministic simulation. | TBD | CERTIFIED |
| Phase 16D | Graph Snapshot & Replay Certification: Added graph snapshot and replay certification surfaces. | TBD | CERTIFIED |
| Phase 16E | Graph Replay Structural Integrity: Certified graph replay structural consistency. | TBD | CERTIFIED |
| Phase 17A | External Graph / Task Interface Layer: Specified standalone external submission layer; partially satisfied through existing config-based graph ingestion. Do not overstate as fully standalone-certified. | TBD | SPECIFIED / PARTIAL |
| Phase 17B | Execution Parameter Enforcement Layer: Implemented controller-enforced execution parameters; external parameters remain requests, not authority. | TBD | CERTIFIED |
| Phase 17C | Parameter Snapshot / Audit / Replay Integration: Integrated canonical execution parameters into snapshot, audit, and replay surfaces. | TBD | CERTIFIED |
| Phase 18A | External Boundary Hardening Specification: Defined hardening requirements before controlled experimentation. | TBD | CERTIFIED |
| Phase 18B | Boundary Rejection / Resource Protection: Certified fail-closed admission, malformed graph refusal, and resource guardrails. | TBD | CERTIFIED |
| Phase 18C | Adversarial Fixture Pack: Added adversarial fixtures for cycle rejection, density caps, payload caps, and malformed graph refusal. | TBD | CERTIFIED |
| Phase 18D | Pre-Test Readiness Memo: Certified readiness posture for controlled experimentation. | TBD | CERTIFIED |
| Phase 19A | Frontier → Qwen Integration Test Plan: Defined live observation and test plan for bounded controller runtime verification. | TBD | COMPLETED |
| Phase 19B | Live Test Surface: Certified repo-native live test surface; audit fields exposed and verified. Full multi-node live lineage remains optional future certification. | TBD | CERTIFIED |
| Phase 20A | Controlled Experimentation Brief: Cleared the system to begin controlled real-world planner→executor experimentation under hardened controller conditions. | TBD | COMPLETED |
| Phase 20B | Recovery Branching Enablement: Allowed `validation_failed` to branch only where explicit `on_failure` graph authority exists; fail-fast preserved otherwise. | TBD | CERTIFIED |
| Phase 21A | Repo-Native Multi-Hop Branching Follow-Through: Verified success and recovery follow-through paths including `[0,1,3]` and `[0,2,3]`. | TBD | CERTIFIED |
| Phase 21B | Deep Convergent Branching: Verified deeper convergent paths including success `[0,1,3,4]` and recovery `[0,2,4]`. | TBD | CERTIFIED |
| Phase 22A | Real Runtime Ingress Isolation: Established real OpenHands runtime ingress with explicit LM Studio local-provider route; auth/bootstrap blockers classified and bypassed. | TBD | CERTIFIED |
| Phase 22B | Runtime-Edge Audit Surfacing: Surfaced canonical Underwood audit payload at the CLI/runtime edge. | TBD | CERTIFIED |
| Phase 23A | Real-Setup Harness Graduation: `stage_1_experimentation.py` graduated from mock-heavy experimentation into a real-setup runtime-adjacent logic harness. | TBD | CERTIFIED |
| Phase 23B | Real-Setup Dual-Outcome Symmetry: Certified diamond branching symmetry: success `[0,1,3]`, recovery `[0,2,3]`, canonical replay boundaries, and consistency bits true. | TBD | CERTIFIED |
| Phase 23C | Real-Setup Convergent Topology Certification: Certified deeper convergent topology: success `[0,1,3,4]`, recovery `[0,2,4]`. | TBD | CERTIFIED |
| Phase 23D | Real-Setup Robustness Pack: Certified topology-preserving robustness: edge-order invariance, node-label variation, disconnected-node tolerance, redundant-edge tolerance. | TBD | CERTIFIED |
| Phase 24B | Frontier → Harness Bridge: Added strict planner payload admission into `stage_1_experimentation.py`: schema-bound graph intake, deterministic validation, and direct planner payload→Underwood graph conversion. | TBD | CERTIFIED |
| Phase 24B.1 | Start Node Boundary Enforcement: Explicitly fail-closed unless `start_node == 0`. | TBD | CERTIFIED |
| Phase 24C | Bridge Hardening: Added explicit bridge taxonomy: `invalid_schema`, `payload_too_large`, `invalid_index`, `nondeterministic_transition`, `unsupported_start_node`, and `cyclic_graph`. | TBD | CERTIFIED |
| Phase 24C.1 | True 64 KiB Boundary: Corrected payload limit to a true 65,536-byte boundary. | TBD | CERTIFIED |
| Phase 24D | Planner-Facing Validation Surface: Separated validation from execution via `validate_frontier_payload(...)`. | TBD | CERTIFIED |
| Phase 24D.1 | Clean Message Surface: Removed Pydantic formatting noise from planner-facing errors. | TBD | CERTIFIED |
| Phase 24E | Structured Planner Handoff: Added canonical planner handoff artifact with `ok`, `category`, `message`, `graph`, `canonical_payload_example`, and `bridge_version`. | TBD | CERTIFIED |
| Phase 24F | Live Qwen Planner Loop: Integrated real LM Studio / Qwen planner output into the bridge/harness loop. | TBD | CERTIFIED / BACKEND-DEPENDENT |
| Phase 24F.1 | Live Planner Contract Hardening: Tightened planner prompt and taxonomy classification for live planner errors. | TBD | CERTIFIED / BACKEND-DEPENDENT |
| Phase 24G | Scratch Workspace Execution: First real workspace side effect in a disposable scratch directory. | TBD | CERTIFIED |
| Phase 24G.1 | Bounded Two-Node Workspace Execution: Added bounded create→verify workspace execution. | TBD | CERTIFIED |
| Phase 24H | Live Qwen Two-Node Planner Compliance: Planner generated bridge-admissible two-node graphs for real workspace execution. | TBD | CERTIFIED / BACKEND-DEPENDENT |
| Phase 25A | VS Code Operator Surface Runbook: Established VS Code as the primary design/control surface. | TBD | CERTIFIED |
| Phase 25B | Warp Terminal-Only Cockpit: Established Warp as a zero-AI execution cockpit. | TBD | CERTIFIED |
| Phase 25C | Unified Operator Workflow: Defined the VS Code + Warp combined operator loop. | TBD | CERTIFIED |
| Phase 25D | Operator Discipline Certification: Added explicit run discipline, failure taxonomy, and operator certification checklist. | TBD | CERTIFIED |
| Phase 26A | Multi-Task Workspace Execution Design: Defined primitive-registry model. | TBD | CERTIFIED |
| Phase 26B | Multi-Task Executor Implementation: Implemented semantic mapping for `CREATE_FILE`, `APPEND_FILE`, and `VERIFY_FILE`. | TBD | CERTIFIED |
| Phase 26B.1 | Adversarial Mapping Hardening: Hardened semantic mapping against multiple filenames, traversal, slash attempts, and substring filename tricks. | TBD | CERTIFIED |
| Phase 26C | Primitive Registry Extension Design: Audited safe next primitive expansion. | TBD | CERTIFIED |
| Phase 26D | DELETE_FILE Primitive: Implemented bounded deletion primitive. | TBD | CERTIFIED |
| Phase 26E | DELETE + VERIFY Consistency: Verified deletion state propagates deterministically into later verification failure. | TBD | CERTIFIED |
| Phase 26F | READ_METADATA Design: Designed read-only metadata primitive. | TBD | CERTIFIED |
| Phase 26G | READ_METADATA Primitive: Implemented read-only metadata primitive for existence, size, and modified time. | TBD | CERTIFIED |
| Phase 26H | Metadata Consistency Verification: Verified metadata reflects create / append / delete transitions. | TBD | CERTIFIED |
| Phase 26I | Primitive Ambiguity Audit: Audited keyword overlap and ambiguity risk. | TBD | CERTIFIED |
| Phase 26J | Deterministic Keyword Hardening: Removed overly broad planner/executor verbs such as `check` and `update`. | TBD | CERTIFIED |
| Phase 26K | Planner Prompt Alignment: Aligned planner vocabulary to the hardened primitive registry. | TBD | CERTIFIED |
| Phase 27A | Live Multi-Primitive Planner Compliance Suite: Added live planner sweep across multiple primitive workflows. | TBD | CERTIFIED / BACKEND-DEPENDENT |
| Phase 27B | Filename Discipline Hardening: Constrained planner to executor allowlist filenames. | TBD | CERTIFIED |
| Phase 27C | Intent Filename Fidelity Hardening: Improved filename adherence to task intent. | TBD | CERTIFIED |
| Phase 27D | Cross-Node Filename Lock Hardening: Eliminated cross-node filename drift. | TBD | CERTIFIED |
| Phase 27E | Intent Grounding Bias Hardening: Eliminated `hello.txt` default-bias; planner now uses exact filename specified by intent. | TBD | CERTIFIED |
| Phase 28A | Three-Node Linear Execution Expansion: Added bounded three-node linear execution. | TBD | CERTIFIED |
| Phase 28A.1 | Three-Node Edge-Set Hardening: Made three-node linear validation edge-order invariant. | TBD | CERTIFIED |
| Phase 28B | Three-Node Conditional Branching: Added bounded branching topology `0→1 on_success`, `0→2 on_failure`. | TBD | CERTIFIED |
| Phase 28C | Live Three-Node Linear Planner Compliance: Added live planner compliance suite at the three-node linear boundary. | TBD | CERTIFIED / BACKEND-DEPENDENT |
| Phase 28D | Three-Node Content Contract Hardening: Eliminated missing quoted-content drift in three-node planner outputs. | TBD | CERTIFIED |
| Phase 28E | Live Three-Node Branching Planner Compliance: Added live planner compliance suite at the three-node branching boundary. | TBD | CERTIFIED / BACKEND-DEPENDENT |
| Phase 28F | Branch Path State Consistency Verification: Verified selected-branch-only execution, skipped branch non-effects, and true filesystem state for branch-selected paths. | TBD | CERTIFIED |
| Phase 29A | Four-Node Linear Execution Expansion: Expanded authorized topology to `0→1→2→3` on success. | TBD | CERTIFIED |
| Phase 29B | Live Four-Node Linear Planner Compliance Suite: Live planner-dependent compliance for four-node linear workflows. During recovery, missing `LLM_MODEL` must report `BLOCKED/UNAVAILABLE`, not `PASS` or false `FAIL`. | TBD | RECOVERY-CORRECTED / BACKEND-DEPENDENT |
| Phase 29C | Four-Node Content Contract Hardening: Live planner-dependent content/continuity hardening for four-node workflows. During recovery, missing `LLM_MODEL` must report `BLOCKED/UNAVAILABLE`. | TBD | RECOVERY-CORRECTED / BACKEND-DEPENDENT |
| Phase 30A | Four-Node Execution Scaling Continuation: Continued four-node execution hardening beyond initial linear admission. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 30B | Four-Node Robustness / Boundary Checks: Continued topology and workspace robustness checks. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 30C | Four-Node Failure Surface Refinement: Continued bounded failure handling and diagnosis surface. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 30D | Four-Node Operator Diagnostics: Continued operator-facing reporting for four-node execution results. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 30E | Harness Lifecycle Cleanup: Cleaned up harness lifecycle behavior and stabilized end-of-run housekeeping. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 31A | Execution Scaling / Branching Topology Continuation: Continued scaling and branching topology certification prior to CLI operator work. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 32A | CLI Entry Surface: Introduced bounded CLI entrypoint via `--task` and `--cli-only`; established single-intent execution model. | TBD | CERTIFIED |
| Phase 32B | CLI Output Surface: Added structured CLI output rendering and diagnostic visibility. | TBD | CERTIFIED |
| Phase 32C | CLI Gate Parity: Ensured CLI execution respects full controller gating; no admission/validation bypass. | TBD | CERTIFIED |
| Phase 32D | CLI Topology Classification: Surfaced topology classification aligned with internal execution graph semantics. | TBD | CERTIFIED |
| Phase 33A | CLI Runbook Surface: Introduced `--show-runbook` and operator-facing usage documentation. During recovery, missing planner dependency reports `BLOCKED/UNAVAILABLE` for planner-dependent checks. | TBD | RECOVERY-CORRECTED |
| Phase 33B | Example Intent Surface: Added safe certified CLI intent examples. Current recovery expectation: `BLOCKED/UNAVAILABLE` if planner-dependent checks are blocked by missing `LLM_MODEL`; otherwise `PASS`/`FAIL` truthfully. | TBD | RECOVERY-CORRECTED / VERIFY |
| Phase 33C | Natural-Language Example Intent Alignment: Replaced primitive syntax with natural-language examples and preserved render bypass. During recovery, missing planner dependency reports `BLOCKED/UNAVAILABLE`. | TBD | RECOVERY-CORRECTED |
| Phase 33D | Runbook / Classification Consistency: Synced runbook terminology with internal topology classifications. | TBD | RECOVERY-CORRECTED |
| Phase 34A | Compact Mode: Introduced `--compact` high-signal output mode. | TBD | RECOVERY-CORRECTED |
| Phase 34B | Compact/Rich Parity Verification: Verified rendering modes do not alter execution logic. | TBD | RECOVERY-CORRECTED |
| Phase 34C | Exit-Code Semantics: Introduced deterministic exit codes: `0` success, `1` execution failure, `2` blocked. | TBD | RECOVERY-CORRECTED |
| Phase 34D | Exit-Code Documentation: Synced runbook with exit-code definitions. | TBD | RECOVERY-CORRECTED |
| Phase 35A | Summary Line: Introduced `__UNDERWOOD_SUMMARY__` machine-readable output. | TBD | RECOVERY-CORRECTED |
| Phase 35B | Summary ↔ Exit-Code Consistency: Verified summary reflects true execution result. | TBD | RECOVERY-CORRECTED |
| Phase 35C | Summary Documentation: Added summary-line spec to runbook. Recovery restored verification-level environment awareness while keeping runtime fail-closed. | TBD | RECOVERY-CORRECTED |
| Phase 36A | Quiet-Success Mode: Introduced `--quiet-success`; suppresses success diagnostics only. Recovery restored loud fail-closed behavior without planner fallback. | TBD | RECOVERY-CORRECTED |
| Phase 36B | CLI Flag Documentation: Documented all CLI flags in runbook. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 37A | Error-Class Surface: Introduced exit code `3` for system errors; added `outcome=ERROR` and `state=EXCEPTION`. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 37B | Error-Class Consistency Verification: Verified error signaling across all surfaces. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 38A | Invocation Header: Added `[UNDERWOOD INVOCATION]` header with timestamp, intent, and mode flags. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 38B | Header / Summary Consistency: Verified invocation header and summary alignment. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 38C | Invocation Documentation: Added header spec to runbook. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 39A | Session Delimiters: Introduced session start/end delimiters for log isolation. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 39B | Delimiter Documentation: Documented session envelope in runbook. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 40A | Footer Ordering Verification: Enforced diagnostics → summary → end delimiter ordering. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 40B | Closure Documentation: Documented terminal closure guarantees. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 41A | Copy/Paste-Safe Surface: Verified full output is grep-stable, single-emission, and drift-free. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 41B | Parsing Documentation: Defined five-stage output envelope: start, header, diagnostics, summary, end. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 42A | Outcome Token Verification: Stabilized `outcome`, `topology`, `exit_code`, and `state` tokens. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 42B | Token Documentation: Added explicit token definitions to runbook. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 43A | Cross-Mode Verification: Verified structural and semantic parity across standard, compact, and quiet-success modes. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 43B | Cross-Mode Documentation: Defined rendering policies and ensured failures remain loud. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 44A | Runbook ↔ Live Drift Verification: Programmatically validated runbook against implementation; zero tolerance for drift. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 45A | Paste-Ready Commands: Added copyable commands for standard, compact, quiet-success, and help. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 45B | Command / Flag Consistency Verification: Verified paste-ready commands match live CLI flags and certified capabilities; absence of multi-intent/retries/unsupported features. | TBD | CERTIFIED / VERIFY IF TOUCHED |
| Phase 46A | VS Code Entry Surface Runbook: Added terminal-only VS Code usage documentation. No extension or editor integration. | TBD | CERTIFIED |
| Phase 46B | VS Code Entry Surface / Live CLI Consistency Verification: Verified terminal-only wording, absence of IDE overclaims, and live CLI alignment. | TBD | CERTIFIED |
| Phase 47A | VS Code Native Surface Boundary Memo: Added boundary note distinguishing certified terminal usage from future native/editor integration. | TBD | CERTIFIED |
| Phase 47B | VS Code Native Surface Boundary / Runbook Consistency Verification: Verified boundary section, future constraints, overclaim rejection, and no native execution mode. | TBD | CERTIFIED |
| Phase 48A | VS Code Terminal Operator Smoke Certification: Proved terminal-only operator workflow, CLI path stability, output-contract stability, workspace reviewability, and no native mode. | TBD | CERTIFIED |
| Phase 49A | Terminal Operator Live Run Proof: Proved bounded practical CLI run shape, stable terminal output, stable summary line, workspace/file reviewability, and shell-first workflow. | TBD | CERTIFIED |
| Phase 49B | Terminal Operator Review Gate Proof: Intended to prove sufficient evidence for human review decisions: `APPROVE`, `REVISE`, `REJECT`. Corrected policy: if live planner backend is absent, report `BLOCKED/UNAVAILABLE`; never add synthetic planner fallback. | TBD | RECOVERY-IN-PROGRESS / BACKEND-DEPENDENT |

---

## Current Recovery Ledger

| Item | Description | Status |
|---|---|---|
| Recovery Mode | The project is conceptually at Phase 49, but `stage_1_experimentation.py` suffered corruption/drift during Phase 49B live verification attempts. Current work is forward re-certification, not new phase development. | ACTIVE |
| Runtime Rule | Runtime must remain strict and fail-closed. Verification may be environment-aware. | LOCKED |
| No Fallback Rule | Missing `LLM_MODEL` or live backend must never trigger synthetic planner output or fake graph generation. | LOCKED |
| 35C Recovery | Summary documentation surface restored by moving environment handling into verification logic, not runtime fallback. | APPROVED |
| 36A Recovery | Quiet-success / loud-failure behavior restored with truthful missing-backend handling. | APPROVED |
| 29B Recovery | Live four-node planner compliance now reports `BLOCKED/UNAVAILABLE` when backend is missing. | APPROVED |
| 29C Recovery | Four-node content contract hardening now reports `BLOCKED/UNAVAILABLE` when backend is missing. | APPROVED |
| 33A Recovery | CLI runbook surface now reports `BLOCKED/UNAVAILABLE` when planner-dependent checks are blocked. | APPROVED |
| 33B Recovery | Example intent surface has been observed as `BLOCKED/UNAVAILABLE`; verify again if it reappears as a failure. | OBSERVED / VERIFY |
| 33C Recovery | Natural-language example alignment now reports `BLOCKED/UNAVAILABLE` when planner-dependent check is blocked. | APPROVED |
| 33D Recovery | Runbook consistency restored by updating `show_cli_runbook` with certified topology names and safety labeling. | APPROVED |
| 34A Recovery | Compact mode output surface restored in `run_cli_task` and truthful `BLOCKED/UNAVAILABLE` reporting implemented. | APPROVED |
| 34B Recovery | Rich/Compact parity verified via output headers; truthful `BLOCKED/UNAVAILABLE` reporting implemented for planner-missing states. | APPROVED |
| 34C Recovery | Exit-code `2` for blocked tasks restored in `run_cli_task`; truthful `BLOCKED/UNAVAILABLE` reporting implemented for planner-missing states. | APPROVED |
| 34D Recovery | Runbook exit-code documentation updated; truthful `BLOCKED/UNAVAILABLE` reporting implemented for planner-missing states. | APPROVED |
| 35A Recovery | Machine-readable summary line restored for all task outcomes; truthful `BLOCKED/UNAVAILABLE` reporting implemented for planner-missing states. | APPROVED |
| 35B Recovery | Summary/exit-code consistency trials now support truthful `BLOCKED/UNAVAILABLE` reporting for planner-missing states. | APPROVED |
| 35C Recovery | Phase 35C outcome semantics corrected to report `BLOCKED/UNAVAILABLE` when planner is missing. | APPROVED |
| 36A Recovery | Phase 36A outcome semantics corrected to report `BLOCKED/UNAVAILABLE` when planner is missing. | APPROVED |
| 36B Recovery | Phase 36B restored; CLI flag documentation added to runbook and verified via automated trial. | APPROVED |
| 37A Recovery | Phase 37A restored; Exit code `3` and `outcome=ERROR` surface implemented for system exceptions. | APPROVED |
| 37B Recovery | Phase 37B restored; Structural consistency of error-class signals (3/ERROR/EXCEPTION) verified. | APPROVED |
| 38A Recovery | Phase 38A restored; Invocation header with timestamp, intent, and mode flags implemented. | APPROVED |
| 38B Recovery | Phase 38B restored; Parity between invocation header and summary fields verified. | APPROVED |
| 38C Recovery | Phase 38C restored; Invocation header documentation added to CLI runbook. | APPROVED |
| 39A Recovery | Phase 39A restored; Session start/end delimiters verified for all output envelopes. | APPROVED |
| 39B Recovery | Phase 39B restored; Session delimiter documentation added to CLI runbook. | APPROVED |
| 40A Recovery | Phase 40A restored; Footer ordering (Summary before End Delimiter) verified. | APPROVED |
| 40B Recovery | Phase 40B restored; Terminal closure documentation added to CLI runbook. | APPROVED |
| 41A Recovery | Phase 41A restored; Parsing stability (copy-paste safe envelope) verified. | APPROVED |
| 41B Recovery | Phase 41B restored; Parsing envelope documentation added to CLI runbook. | APPROVED |
| 42A Recovery | Phase 42A restored; Outcome-token stability (outcome/topology/exit_code/state) verified. | APPROVED |
| 42B Recovery | Phase 42B restored; Outcome-token documentation added to CLI runbook. | APPROVED |
| 43A Recovery | Phase 43A restored; Cross-mode integrity (standard/compact/quiet-success) verified. | APPROVED |
| Next Target | First failing phase after Phase 43A. Current likely target: Phase 43B. | NEXT |

---

## Operating Instructions for Gemini Flash / Codex

| Rule | Instruction | Status |
|---|---|---|
| Effort | Use `EFFORT LEVEL: LOW` unless explicitly told otherwise. | LOCKED |
| Scope | Modify only `stage_1_experimentation.py` and `PHASE_INDEX.md` when phase-index ledger updates are explicitly requested. | LOCKED |
| Granularity | Fix the first failing phase only. | LOCKED |
| Backend Absence | Missing `LLM_MODEL` means `BLOCKED/UNAVAILABLE` for live planner-dependent phases, never `PASS`. | LOCKED |
| Runtime Semantics | Do not change `run_cli_task`, `generate_frontier_plan`, bridge admission, topology, gating, or controller lifecycle unless explicitly scoped. | LOCKED |
| Phase Index | May be updated as a factual ledger, but must not rewrite history or justify behavior changes. | LOCKED |
| Validation | Run `python stage_1_experimentation.py`. | LOCKED |
| Output | Return failing phase, exact files changed, exact diff, validation output, one-line completion status. | LOCKED |

---

## Next Recommended Prompt

```text
SYSTEM:
You are performing a minimal behavioral verification and restoration.

EFFORT LEVEL: LOW

Allowed files:
- stage_1_experimentation.py
- PHASE_INDEX.md

Focus only on:
- the first failing phase after Phase 33C
- recording the recovery status in PHASE_INDEX.md if and only if the implementation correction succeeds

Do not:
- implement new phases
- refactor unrelated code
- modify planner logic
- add fallbacks
- upgrade blocked/unavailable states into PASS
- broadly deduplicate phase blocks
- rewrite historical phase descriptions
- use PHASE_INDEX.md to justify behavior changes
- touch later phases unless required for this specific fix

TASK:
Run the full script, identify the first failing phase after Phase 33C, and restore only that phase so it reports truthful outcome semantics with fail-closed behavior preserved. After the implementation correction is validated, add a concise recovery note to PHASE_INDEX.md recording the corrected phase and its truthful outcome semantics.

OBJECTIVE:
- preserve runtime semantics
- preserve controller/gating/topology behavior
- restore only the first broken certified surface after 33C
- if the phase depends on live planner/backend configuration and LLM_MODEL is missing, report BLOCKED/UNAVAILABLE rather than PASS or FAIL
- if the phase is documentation-only, restore it to PASS without changing runtime behavior
- update PHASE_INDEX.md only as a factual ledger entry, not as a redesign

VALIDATION:
python stage_1_experimentation.py

COMPLETION RULE:
Stop immediately after:
1. the first failing phase after 33C reports truthful outcome semantics
2. PHASE_INDEX.md records the recovery update concisely

OUTPUT FORMAT:
1. failing phase identified
2. exact files changed
3. exact diff
4. validation output
5. one-line completion status
```
