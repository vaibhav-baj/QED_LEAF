from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .model import decide, digest, release, validate_policy
from .store import Store
from .worker import TOOLCHAIN, extract, snapshot


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _default_policy() -> dict:
    return {"schema": 1, "targets": ["pilot"],
            "permitted_axioms": ["propext", "Quot.sound", "Classical.choice"],
            "required_checkers": ["lean-build", "target-exists", "axiom-policy", "sorry-free"],
            "track": "completed-proof", "toolchain": TOOLCHAIN}


def init_project(args: argparse.Namespace) -> int:
    root = Path(args.directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source"
    source.mkdir(exist_ok=True)
    (source / "Pilot.lean").write_text("/-- A complete, kernel-checked pilot target. -/\ntheorem pilot : True := by trivial\n", encoding="utf-8")
    policy = _default_policy()
    (root / "qed-leaf-policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    print(f"Created {source / 'Pilot.lean'} and {root / 'qed-leaf-policy.json'}")
    return 0


def analyze(args: argparse.Namespace) -> int:
    source = Path(args.source).resolve()
    policy_path = Path(args.policy).resolve()
    output = Path(args.output).resolve()
    try:
        policy = _read_json(policy_path)
        validate_policy(policy)
        files = snapshot(source)
    except ValueError as error:
        print(json.dumps({"status": "inconclusive", "reason": str(error)}), file=sys.stderr)
        return 2
    source_id = digest(files)
    policy_id = digest(policy)
    if not args.local_trust:
        report = {"schema": 1, "status": "inconclusive", "reason": "Local trusted-source acknowledgement is required",
                  "source": source_id, "policy": policy_id, "toolchain": TOOLCHAIN}
        output.mkdir(parents=True, exist_ok=True)
        report_id = Store(output).put("reports", report)
        print(json.dumps({"status": report["status"], "report": report_id, "path": str(output / "reports" / f"{report_id}.json")}))
        return 2
    extraction = extract(files, timeout=args.timeout)
    facts = extraction.get("facts", [])
    by_name = {fact.get("name"): fact for fact in facts}
    checks = []
    for target in policy["targets"]:
        fact = by_name.get(target)
        checks.append({"target": target, "check": "lean-build", "status": "passed" if extraction["status"] == "passed" else "inconclusive",
                       "evidence": "Lean 4 kernel compilation"})
        checks.append({"target": target, "check": "target-exists", "status": "passed" if fact else ("failed" if extraction["status"] == "passed" else "inconclusive"),
                       "evidence": "Lean environment declaration table"})
        axioms = set(fact.get("axioms", [])) if fact else set()
        forbidden = sorted(axioms - set(policy["permitted_axioms"]))
        checks.append({"target": target, "check": "axiom-policy", "status": "failed" if forbidden else ("passed" if fact else "inconclusive"),
                       "evidence": {"axioms": sorted(axioms), "forbidden": forbidden}})
        checks.append({"target": target, "check": "sorry-free", "status": "failed" if "sorryAx" in axioms else ("passed" if fact else "inconclusive"),
                       "evidence": {"axioms": sorted(axioms)}})
    formal = decide(checks, policy["required_checkers"], policy["targets"])
    report = {"schema": 1, "created_at": datetime.now(timezone.utc).isoformat(), "analyzer": __version__,
              "status": formal, "formal_verification": formal, "mathematical_fidelity": "review-pending",
              "engineering_quality": {"build_seconds": sum(x.get("seconds", 0) for x in extraction.get("logs", []))},
              "source": {"id": source_id, "files": sorted(files)}, "policy": {"id": policy_id, **policy},
              "toolchain": extraction.get("version", TOOLCHAIN), "facts": facts, "checks": checks,
              "worker": {"accepted": extraction["status"] == "passed", "status": extraction["status"], "reason": extraction.get("reason")}}
    output.mkdir(parents=True, exist_ok=True)
    report_id = Store(output).put("reports", report)
    print(json.dumps({"status": formal, "report": report_id, "path": str(output / "reports" / f"{report_id}.json")}))
    return 0 if formal == "passed" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qed-leaf", description="Evidence-based Lean verification reports")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a runnable pilot project")
    init.add_argument("directory", nargs="?", default=".")
    init.set_defaults(func=init_project)
    audit = sub.add_parser("analyze", help="analyze a Lean source snapshot")
    audit.add_argument("--source", required=True)
    audit.add_argument("--policy", required=True)
    audit.add_argument("--output", default=".qed-leaf")
    audit.add_argument("--timeout", type=float, default=300)
    audit.add_argument("--local-trust", action="store_true", help="acknowledge this curated source is trusted")
    audit.set_defaults(func=analyze)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "inconclusive", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
