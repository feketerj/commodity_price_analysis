from __future__ import annotations

import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY_FILES = [
    "app.py",
    "cpa/db.py",
    "cpa/exporting.py",
    "cpa/memo.py",
    "cpa/pricing.py",
    "cpa/seed.py",
    "cpa/sources.py",
    "cpa/validation.py",
]


def main() -> int:
    failures: list[str] = []
    print("Commodity Price Analysis operator doctor")
    print(f"Root: {ROOT}")

    for relative in PY_FILES:
        path = ROOT / relative
        try:
            py_compile.compile(str(path), doraise=True)
            print(f"PASS compile {relative}")
        except py_compile.PyCompileError as exc:
            failures.append(f"compile {relative}: {exc.msg}")
            print(f"FAIL compile {relative}: {exc.msg}")

    test_result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if test_result.returncode == 0:
        print("PASS unit tests")
    else:
        failures.append("unit tests failed")
        print(test_result.stdout)

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            from cpa.db import Database
            from cpa.pricing import analyze_case
            from cpa.seed import seed_demo_data

            db = Database(Path(temp_dir) / "doctor.sqlite3")
            db.initialize()
            seed_demo_data(db)
            bundle = db.get_case_bundle("demo-pinto-beans-50kg")
            if not bundle:
                raise RuntimeError("demo case was not seeded")
            analysis = analyze_case(bundle["case"], bundle["evidence"], bundle["adjustments"])
            if analysis["eligible_count"] < 3:
                raise RuntimeError("demo case has fewer than three eligible evidence records")
            backup = db.backup(Path(temp_dir) / "backups")
            if not backup.exists():
                raise RuntimeError("database backup was not created")
            print("PASS database initialize, seed, analyze, backup")
    except Exception as exc:
        failures.append(f"database smoke failed: {exc}")
        print(f"FAIL database smoke: {exc}")

    if failures:
        print("")
        print("Doctor result: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("")
    print("Doctor result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
