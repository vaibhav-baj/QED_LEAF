import json
import uuid
import unittest
from pathlib import Path

from qed_leaf.model import decide, digest, release, validate_policy
from qed_leaf.store import Store
from qed_leaf.worker import snapshot


class CoreTests(unittest.TestCase):
    def scratch(self) -> Path:
        root = Path.cwd() / ".qed-leaf" / "test-runs" / uuid.uuid4().hex
        root.mkdir(parents=True)
        return root

    def test_decision_requires_every_target_and_checker(self):
        checks = [{"target": "A.t", "check": "build", "status": "passed"}]
        self.assertEqual(decide(checks, ["build", "axioms"], ["A.t"]), "inconclusive")
        checks.append({"target": "A.t", "check": "axioms", "status": "passed"})
        self.assertEqual(decide(checks, ["build", "axioms"], ["A.t"]), "passed")
        checks[-1]["status"] = "failed"
        self.assertEqual(decide(checks, ["build", "axioms"], ["A.t"]), "failed")

    def test_forbidden_sorry_is_rejected_by_policy(self):
        policy = {"schema": 1, "targets": ["A.t"], "permitted_axioms": ["sorryAx"],
                  "required_checkers": ["build"], "track": "completed-proof", "toolchain": "leanprover/lean4:v4.33.1"}
        with self.assertRaises(ValueError):
            validate_policy(policy)

    def test_release_is_separate_from_formal_result(self):
        self.assertFalse(release("passed", "review-pending", "completed-proof"))
        self.assertTrue(release("passed", "expert-reviewed-match", "completed-proof"))

    def test_store_is_content_addressed_and_immutable(self):
        directory = self.scratch()
        store = Store(directory)
        value = {"hello": "world"}
        identity = store.put("reports", value)
        self.assertEqual(store.get("reports", identity), value)
        Path(directory, "reports", identity + ".json").write_text(json.dumps({"tampered": True}), encoding="utf-8")
        with self.assertRaises(ValueError):
            store.get("reports", identity)

    def test_snapshot_rejects_non_lean_files(self):
        directory = self.scratch()
        Path(directory, "x.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            snapshot(directory)


if __name__ == "__main__":
    unittest.main()
