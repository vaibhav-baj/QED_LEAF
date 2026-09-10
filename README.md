# QED_LEAF

QED_LEAF is an analyzer-first assurance pipeline for Lean 4 projects. It turns a curated Lean source snapshot into a content-addressed, immutable JSON report. Formal verification, mathematical fidelity, and engineering quality are separate assessments: a build cannot compensate for a forbidden axiom, missing target, unresolved checker, or pending expert review.

The prototype asks how much additional assurance and actionable information an evidence-based pipeline provides beyond compilation, linting, and an axiom audit.

## Included

- A strict versioned JSON policy with an independently approved, nonempty target list, required checkers, permitted axioms, track, and pinned Lean toolchain.
- A Lean semantic adapter using Lean's environment and transitive `collectAxioms` facts instead of regex parsing.
- Fail-closed decisions: `passed`, `failed`, or `inconclusive`. A worker JSON field can never establish acceptance.
- Checks for target existence, kernel compilation, forbidden transitive axioms, and `sorryAx`.
- Immutable SHA-256 reports containing source and policy identities, toolchain, facts, checks, logs, and caveats.
- Unit and mutation-oriented tests for policy decisions, integrity, and source boundaries.

The local worker is for a single organization and explicitly trusted source. It applies process, memory, output, file-count, and snapshot-size limits and keeps a reproducible run directory. It is not an adversarial sandbox. A public or multi-tenant deployment must add an independently reviewed OS sandbox, controlled dependency provisioning, exported-artifact verification, and process-tree isolation.

## Requirements

Python 3.11 or newer and Lean 4.33.1. The `lean` executable must be on `PATH`; the adapter refuses another Lean version. No Python packages beyond the standard library are required.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
qed-leaf init pilot
qed-leaf analyze --source pilot\source --policy pilot\qed-leaf-policy.json --output pilot\.qed-leaf --local-trust
```

The command prints a report ID and path. A successful formal result still has `mathematical_fidelity: review-pending`; release requires a separate expert decision recorded by the calling organization. Omit `--local-trust` or use a missing target to get an `inconclusive` report and a nonzero exit code.

## Policy

```json
{
  "schema": 1,
  "targets": ["pilot"],
  "permitted_axioms": ["propext", "Quot.sound", "Classical.choice"],
  "required_checkers": ["lean-build", "target-exists", "axiom-policy", "sorry-free"],
  "track": "completed-proof",
  "toolchain": "leanprover/lean4:v4.33.1"
}
```

`sorryAx` is rejected even if someone attempts to add it to `permitted_axioms`. Open conjectures must use `open-conjecture` and remain a separately labelled track. Targets and required checkers must be nonempty and unique. The submission cannot change its own policy during analysis.

## Evidence and reports

Lean environment facts and compilation are machine-checked within the declared scope; durations and hashes are measured; policy and mathematical fidelity remain reviewable decisions. Heuristics are never a release gate by themselves.

Reports are stored under `<output>/reports/<sha256>.json`. The filename is the hash of canonical report content. Existing objects are never overwritten, and every read rechecks the hash. Changed source, dependency, policy, analyzer, or toolchain creates a new report. Run logs remain under `.qed-leaf/runs` for reproducibility on Windows.

## Testing

```powershell
python -m unittest discover -s tests -v
```

Tests cover fail-closed acceptance, unconditional forbidden-axiom rejection, separate fidelity review, immutable report storage, and source snapshot boundaries. The pilot command additionally exercises Lean compilation and semantic extraction.

## Design limits and next steps

The adapter does not claim that a formal statement faithfully represents informal mathematics. It does not infer logical redundancy from syntactic unused hypotheses, classify automation or noncomputability as defects, or reject a proof because it is long. Public declarations are analyzed only within the submitted source scope.

Before broader deployment, add trusted-specification comparison for protected statements and definitions, an export checker such as Comparator, an independently reviewed worker sandbox, conservative module-level cache invalidation, reviewer decisions, dependent rebuilds, and a ten-problem mutation suite. Compare build-only, build-plus-linters, trusted-specification checking, and the complete pipeline before making claims about research impact.

## Repository

Source: https://github.com/vaibhav-baj/QED_LEAF

QED_LEAF is an experimental prototype. Review the security boundary before processing untrusted submissions.
