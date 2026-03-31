#!/usr/bin/env python3
"""
verify all packages from the python master manifest can be fetched and installed.

creates a temp venv, runs `uv pip install --no-deps <pkg>==<version>` for each
entry in the master manifest, and reports pass/fail.
so you will need a valid config at ~/.config/uv/uv.toml

usage:
    python scripts/verify_packages.py [--manifest PATH]
"""

import argparse
import subprocess
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="verify python packages from master manifest")
    default_manifest = Path(__file__).resolve().parent.parent / "deps" / "python" / "master" / "manifest.txt"
    parser.add_argument(
        "--manifest",
        type=Path,
        default=default_manifest,
        help="path to manifest.txt (default: deps/python/master/manifest.txt)",
    )
    return parser.parse_args()


def create_temp_venv(tmpdir: Path) -> Path:
    """create a temp venv with uv and return its path."""
    venv_path = tmpdir / ".venv"
    try:
        result = subprocess.run(
            ["uv", "venv", str(venv_path), "--python", "3.12"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise RuntimeError("uv is not installed or not on PATH")
    if result.returncode != 0:
        raise RuntimeError(f"failed to create venv: {result.stderr}")
    return venv_path


def install_package(pkg_spec: str, venv_path: Path) -> tuple[bool, str]:
    """run `uv pip install --no-deps <pkg_spec>` into the venv."""
    try:
        result = subprocess.run(
            [
                "uv", "pip", "install",
                "--no-deps",
                "--python", str(venv_path / "bin" / "python"),
                pkg_spec,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return True, ""
        # grab the last meaningful line from stderr
        err_lines = [ln for ln in result.stderr.strip().splitlines() if ln.strip()]
        err_msg = err_lines[-1] if err_lines else f"exit {result.returncode}"
        return False, err_msg
    except subprocess.TimeoutExpired:
        return False, "timeout after 60s"
    except Exception as e:
        return False, str(e)


def main() -> None:
    args = parse_args()

    if not args.manifest.exists():
        print(f"error: manifest not found: {args.manifest}")
        raise SystemExit(1)

    packages = [
        stripped for line in args.manifest.read_text().splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]

    print(f"\n=== verifying {len(packages)} packages ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        venv_path = create_temp_venv(Path(tmpdir))

        passed: list[str] = []
        failed: list[tuple[str, str]] = []

        for i, pkg in enumerate(packages, 1):
            success, err = install_package(pkg, venv_path)
            if success:
                passed.append(pkg)
                print(f"  [{i}/{len(packages)}] OK  {pkg}")
            else:
                failed.append((pkg, err))
                print(f"  [{i}/{len(packages)}] FAIL {pkg}: {err}")

    # summary
    print(f"\n=== results ===\n")
    print(f"  passed: {len(passed)}/{len(packages)}")
    print(f"  failed: {len(failed)}/{len(packages)}")

    if failed:
        print(f"\n=== failed packages ===\n")
        for pkg, err in failed:
            print(f"  {pkg}: {err}")

    # write results to files alongside the manifest
    results_dir = args.manifest.parent
    (results_dir / "verify-passed.txt").write_text(
        ("\n".join(passed) + "\n") if passed else ""
    )
    (results_dir / "verify-failed.txt").write_text(
        ("\n".join(f"{pkg}: {err}" for pkg, err in failed) + "\n") if failed else ""
    )
    print(f"\n  results written to {results_dir}/verify-passed.txt and verify-failed.txt\n")

    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
