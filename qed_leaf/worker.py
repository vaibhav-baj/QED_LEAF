"""Disposable LOCAL worker for explicitly trusted, curated Lean source only.

This is process hygiene, not a hostile-code sandbox. The CLI refuses execution
without acknowledgement. An adversarial-source deployment needs an independent
export checker and OS sandbox and is not supported by this adapter.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import uuid
import time
from pathlib import Path

TOOLCHAIN = "leanprover/lean4:v4.33.1"
MAX_SOURCE = 2 * 1024 * 1024
MAX_OUTPUT = 16 * 1024 * 1024


def snapshot(root: Path) -> dict[str, str]:
    root = root.resolve()
    files = {}
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Source snapshots cannot contain symlinks")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix != ".lean":
            raise ValueError(f"Source directory must contain only Lean files: {relative}")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(/[A-Za-z][A-Za-z0-9_]*)*\.lean", relative):
            raise ValueError(f"Unsupported module path: {relative}")
        total += path.stat().st_size
        if total > MAX_SOURCE or len(files) >= 100:
            raise ValueError("Source snapshot exceeds limits (2 MiB / 100 files)")
        files[relative] = path.read_text(encoding="utf-8")
    if not files:
        raise ValueError("Source snapshot is empty")
    return files


def kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run(command: list[str], cwd: Path, env: dict, timeout: float) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                start_new_session=os.name != "nt")
        reason = None
        while proc.poll() is None:
            if time.monotonic() - started > timeout:
                reason = "timeout"
            elif os.fstat(output.fileno()).st_size > MAX_OUTPUT:
                reason = "output-limit"
            if reason:
                kill_tree(proc)
                break
            time.sleep(0.02)
        proc.wait()
        output.seek(0)
        raw = output.read(MAX_OUTPUT + 1)
    if len(raw) > MAX_OUTPUT:
        reason = "output-limit"
    return {"command": command, "returncode": proc.returncode, "reason": reason,
            "output": raw[:MAX_OUTPUT].decode("utf-8", errors="replace"),
            "seconds": round(time.monotonic() - started, 4)}


def extract(files: dict[str, str], timeout: float = 60) -> dict:
    lean = shutil.which("lean")
    if not lean:
        return {"status": "inconclusive", "reason": "Lean executable unavailable", "logs": []}
    logs = []
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "ELAN_HOME"}}
    # Keep the disposable run directory under the project. On Windows, Lean's
    # native process can retain a handle briefly; retaining the directory avoids
    # turning a successful verification into a cleanup failure.
    run_root = Path.cwd() / ".qed-leaf" / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    work = run_root / f"run-{uuid.uuid4().hex}"
    work.mkdir()
    try:
        libdir_row = run([lean, "--print-libdir"], work, env, timeout)
        logs.append(libdir_row)
        if libdir_row["returncode"] or libdir_row["reason"]:
            return {"status": "inconclusive", "reason": "Lean library path unavailable", "logs": logs}
        libdir = Path(libdir_row["output"].strip())
        env["LEAN_PATH"] = str(work) + os.pathsep + str(libdir)
        version = run([lean, "--version"], work, env, timeout)
        logs.append(version)
        if version["returncode"] or version["reason"] or "version 4.33.1," not in version["output"]:
            return {"status": "inconclusive", "reason": "Unsupported or unavailable Lean version", "logs": logs}
        modules = {path[:-5].replace("/", "."): path for path in files}
        for relative, content in files.items():
            destination = work / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        # Lean itself computes imports; Python does not parse Lean syntax.
        pending = set(modules)
        dependencies = {}
        for name, relative in modules.items():
            row = run([lean, "--deps", relative], work, env, timeout)
            logs.append(row)
            if row["reason"] or row["returncode"]:
                return {"status": "inconclusive", "reason": "Dependency discovery failed", "logs": logs}
            dependencies[name] = {other for other, path in modules.items()
                                  if str((work / path).with_suffix(".olean")).replace("\\", "/") in row["output"].replace("\\", "/")}
        while pending:
            ready = sorted(name for name in pending if not dependencies[name] & pending)
            if not ready:
                return {"status": "inconclusive", "reason": "Cyclic or unresolved module dependencies", "logs": logs}
            for name in ready:
                path = modules[name]
                row = run([lean, "-M", "1024", "-T", "200000", "-o", path[:-5] + ".olean", path], work, env, timeout)
                logs.append(row)
                if row["reason"] or row["returncode"]:
                    return {"status": "inconclusive", "reason": row["reason"] or "Lean build failed", "logs": logs}
                pending.remove(name)
        adapter = Path(__file__).with_name("Extract.lean").read_text(encoding="utf-8")
        imports = "\n".join(f"import {name}" for name in sorted(modules))
        exporter = adapter.replace("import Lean", "import Lean\n" + imports, 1)
        exporter += "\n\nsyntax (name := qedLeafExtractCmd) \"qed_leaf_extract\" : command\n"
        exporter += "open Lean Elab Command in\nelab_rules : command\n  | `(qed_leaf_extract) => qedLeafExtract " + json.dumps(sorted(modules)) + "\n"
        exporter += "qed_leaf_extract\n"
        (work / "QEDLeafAudit.lean").write_text(exporter, encoding="utf-8")
        row = run([lean, "-M", "1024", "-T", "200000", "QEDLeafAudit.lean"], work, env, timeout)
        logs.append(row)
        if row["reason"] or row["returncode"]:
            return {"status": "inconclusive", "reason": row["reason"] or "Semantic extraction failed", "logs": logs}
        lines = [line.removeprefix("QED_LEAF_FACTS=") for line in row["output"].splitlines() if line.startswith("QED_LEAF_FACTS=")]
        if len(lines) != 1:
            return {"status": "inconclusive", "reason": "Missing or ambiguous semantic output", "logs": logs}
        try:
            facts = json.loads(lines[0])
            if not isinstance(facts, list) or len(facts) > 100000:
                raise ValueError("Invalid fact count")
            if len({f["name"] for f in facts}) != len(facts):
                raise ValueError("Duplicate declarations")
            for fact in facts:
                if set(fact) != {"name", "module", "kind", "type", "levels", "body", "axioms"}:
                    raise ValueError("Invalid fact schema")
                if any(not isinstance(fact[k], str) for k in ("name", "module", "kind", "type", "body")):
                    raise ValueError("Invalid fact type")
                if any(not isinstance(fact[k], list) or any(not isinstance(v, str) for v in fact[k]) for k in ("levels", "axioms")):
                    raise ValueError("Invalid fact arrays")
        except (ValueError, KeyError, TypeError) as error:
            return {"status": "inconclusive", "reason": str(error), "logs": logs}
        return {"status": "passed", "facts": sorted(facts, key=lambda f: f["name"]), "logs": logs,
                "version": version["output"].strip()}
    finally:
        # The directory is intentionally retained for reproducibility and
        # post-mortem logs; it is ignored by git and can be removed by the user.
        pass
