"""Pure, fail-closed acceptance logic; never consumes worker acceptance claims."""
from __future__ import annotations

import hashlib
import json


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def decide(checks: list[dict], required: list[str], targets: list[str]) -> str:
    if not targets or not required or len(set(targets)) != len(targets):
        return "inconclusive"
    expected = {(target, check) for target in targets for check in required}
    indexed: dict[tuple, list[str]] = {}
    for row in checks:
        key = (row.get("target"), row.get("check"))
        indexed.setdefault(key, []).append(row.get("status"))
    if any("failed" in indexed.get(key, []) for key in expected):
        return "failed"
    if any(indexed.get(key) != ["passed"] for key in expected):
        return "inconclusive"
    return "passed"


def release(formal: str, fidelity: str, track: str) -> bool:
    return formal == "passed" and fidelity == "expert-reviewed-match" and track == "completed-proof"


def validate_policy(policy: dict) -> None:
    if set(policy) != {"schema", "targets", "permitted_axioms", "required_checkers", "track", "toolchain"}:
        raise ValueError("Policy has missing or unknown fields")
    if policy["schema"] != 1 or policy["track"] not in {"completed-proof", "open-conjecture"}:
        raise ValueError("Unsupported policy schema or track")
    for key in ("targets", "permitted_axioms", "required_checkers"):
        values = policy[key]
        if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values) or len(set(values)) != len(values):
            raise ValueError(f"Invalid {key}")
    if not policy["targets"] or not policy["required_checkers"]:
        raise ValueError("Targets and required checkers must be nonempty")
    if "sorryAx" in policy["permitted_axioms"]:
        raise ValueError("sorryAx may not be permitted")
    if policy["toolchain"] != "leanprover/lean4:v4.33.1":
        raise ValueError("Only Lean 4.33.1 is supported by this adapter")
