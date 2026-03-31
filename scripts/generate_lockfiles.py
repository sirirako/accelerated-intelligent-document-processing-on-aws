#!/usr/bin/env python3
"""
generate lockfiles for all python and node dependencies in the IDP repo.

python: scans requirements.txt and lib/ pyproject.toml files, converts them to
temporary pyproject.toml projects, runs `uv lock`, and saves lockfiles.

node: finds all package.json files, runs `npm install --package-lock-only` in
temp dirs, and saves the resulting package-lock.json files.

usage:
    python scripts/generate_lockfiles.py [--repo-dir PATH] [--output-dir PATH]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


PYTHON_REQUIRES = ">=3.12,<3.14"

# internal packages that won't resolve from PyPI
INTERNAL_PACKAGES = {"idp_common", "idp-common", "idp_sdk", "idp-sdk", "idp_cli", "idp-cli"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="generate lockfiles for all python and node deps")
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=repo_root,
        help="path to the cloned repo (defaults to repo root)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "deps",
        help="base output directory for lockfiles (python/ and node/ subdirs)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--python-only",
        action="store_true",
        help="only generate python lockfiles",
    )
    group.add_argument(
        "--node-only",
        action="store_true",
        help="only generate node lockfiles",
    )
    return parser.parse_args()


def encode_path(rel_path: Path) -> str:
    """convert a relative path to a flat directory name. e.g. src/lambda/foo -> src-lambda-foo"""
    parent = rel_path.parent
    name = str(parent).replace(os.sep, "-").replace("/", "-")
    if not name or name == ".":
        return "root"
    return name


def is_local_path_ref(line: str) -> bool:
    """check if a requirements.txt line is a local path reference."""
    stripped = line.strip()
    # local paths start with . or / or look like ../../something
    if stripped.startswith((".", "/")):
        return True
    # also catch windows-style paths or bare directory names with brackets
    # that point to local packages
    if re.match(r"^[\w./-]+\[", stripped) and ("/" in stripped or ".." in stripped):
        return True
    return False


def is_internal_package(line: str) -> bool:
    """check if a dep line references an internal package."""
    # extract package name (before any version specifier or extras)
    pkg_name = re.split(r"[>=<!\[;\s]", line.strip())[0].strip()
    normalized = pkg_name.lower().replace("_", "-").replace(".", "-")
    return normalized in {p.lower().replace("_", "-") for p in INTERNAL_PACKAGES}


def parse_requirements_txt(filepath: Path) -> list[str]:
    """parse a requirements.txt, returning only public PyPI deps."""
    deps = []
    for raw_line in filepath.read_text().splitlines():
        # strip inline comments
        line = raw_line.split("#")[0].strip()
        if not line:
            continue
        # skip flags like -r, -e, -f, --index-url etc
        if line.startswith("-"):
            continue
        if is_local_path_ref(line):
            continue
        if is_internal_package(line):
            continue
        deps.append(line)
    return deps


def generate_pyproject_toml(name: str, deps: list[str]) -> str:
    """generate a minimal pyproject.toml string."""
    # sanitize name for PEP 508
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", name).lower()
    deps_str = ",\n".join(f'    "{d}"' for d in deps)
    return f"""\
[project]
name = "{safe_name}"
version = "0.0.0"
requires-python = "{PYTHON_REQUIRES}"
dependencies = [
{deps_str}
]

[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"
"""


def run_uv_lock(workdir: Path) -> tuple[bool, str]:
    """run `uv lock` in the given directory. returns (success, output)."""
    try:
        result = subprocess.run(
            ["uv", "lock"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, result.stderr.strip()
        return False, f"exit {result.returncode}: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "timeout after 120s"
    except Exception as e:
        return False, str(e)


def process_requirements_txt(
    req_file: Path, repo_dir: Path, output_dir: Path
) -> tuple[str, bool, str]:
    """process a single requirements.txt file. returns (name, success, message)."""
    rel_path = req_file.relative_to(repo_dir)
    dir_name = encode_path(rel_path)

    deps = parse_requirements_txt(req_file)
    if not deps:
        return dir_name, True, "skipped (no public deps)"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pyproject_content = generate_pyproject_toml(dir_name, deps)
        (tmp / "pyproject.toml").write_text(pyproject_content)

        success, msg = run_uv_lock(tmp)

        if success:
            dest = output_dir / dir_name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp / "uv.lock", dest / "uv.lock")
            shutil.copy2(tmp / "pyproject.toml", dest / "pyproject.toml")
            return dir_name, True, f"locked ({len(deps)} deps)"
        return dir_name, False, msg


_DEP_SECTIONS = {"[project]", "[project.optional-dependencies]", "[dependency-groups]"}


def patch_pyproject_for_locking(content: str) -> str:
    """remove internal package deps from a pyproject.toml so uv lock can resolve.

    only strips internal packages inside dependency arrays within [project],
    [project.optional-dependencies], or [dependency-groups] sections.
    """
    lines = content.splitlines()
    patched = []
    current_section = ""
    in_dep_array = False
    internal_normalized = {p.lower().replace("_", "-") for p in INTERNAL_PACKAGES}

    for line in lines:
        stripped = line.strip()

        # track TOML table headers (but not array-of-tables [[...]])
        if stripped.startswith("[") and not stripped.startswith("[["):
            current_section = stripped
            in_dep_array = False
            patched.append(line)
            continue

        is_dep_section = current_section in _DEP_SECTIONS

        # detect start of a dependency array within a dep section
        if (
            is_dep_section
            and not stripped.startswith("[")
            and "= [" in line
            and not stripped.endswith("]")
        ):
            in_dep_array = True
            patched.append(line)
            continue

        # detect end of array
        if in_dep_array and stripped.startswith("]"):
            in_dep_array = False
            patched.append(line)
            continue

        # only filter inside dependency arrays in dep sections
        if in_dep_array and stripped and not stripped.startswith("#"):
            # strip inline TOML comment before extracting dep string
            comment_idx = stripped.find("#")
            if comment_idx > 0:
                stripped = stripped[:comment_idx].strip()
            dep_str = stripped.strip(",").strip('"').strip("'")
            if not dep_str:
                patched.append(line)
                continue

            # check for local path references
            if dep_str.startswith((".", "/")):
                patched.append(f"    # removed local path: {dep_str}")
                continue

            # check for internal packages
            pkg_name = re.split(r"[>=<!\[;\s]", dep_str)[0].strip()
            normalized = pkg_name.lower().replace("_", "-").replace(".", "-")
            if normalized in internal_normalized:
                patched.append(f"    # removed internal dep: {dep_str}")
                continue

        patched.append(line)
    return "\n".join(patched)


def process_lib_pyproject(
    pyproject_file: Path, repo_dir: Path, output_dir: Path
) -> tuple[str, bool, str]:
    """process a lib/ pyproject.toml file. returns (name, success, message)."""
    rel_path = pyproject_file.relative_to(repo_dir)
    dir_name = encode_path(rel_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # copy pyproject.toml with internal deps patched out
        content = pyproject_file.read_text()
        patched = patch_pyproject_for_locking(content)
        (tmp / "pyproject.toml").write_text(patched)

        # copy setup.py/setup.cfg if they exist alongside
        for extra in ["setup.py", "setup.cfg"]:
            src = pyproject_file.parent / extra
            if src.exists():
                shutil.copy2(src, tmp / extra)

        # some pyprojects need a package dir to exist for setuptools to be happy
        pkg_name = pyproject_file.parent.name.replace("-", "_")
        pkg_dir = tmp / pkg_name
        pkg_dir.mkdir(exist_ok=True)
        (pkg_dir / "__init__.py").write_text("")

        success, msg = run_uv_lock(tmp)

        if success:
            dest = output_dir / dir_name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp / "uv.lock", dest / "uv.lock")
            shutil.copy2(tmp / "pyproject.toml", dest / "pyproject.toml")
            return dir_name, True, "locked"
        return dir_name, False, msg


def parse_uv_lock_packages(lockfile: Path) -> list[dict[str, str]]:
    """parse [[package]] entries from a uv.lock file.

    returns a list of dicts with 'name', 'version', and the full raw block text.
    """
    content = lockfile.read_text()
    packages = []
    # split on [[package]] boundaries
    blocks = re.split(r"\n(?=\[\[package\]\])", content)
    for block in blocks:
        if not block.strip().startswith("[[package]]"):
            continue
        name_match = re.search(r'^name\s*=\s*"(.+?)"', block, re.MULTILINE)
        version_match = re.search(r'^version\s*=\s*"(.+?)"', block, re.MULTILINE)
        if name_match and version_match:
            packages.append({
                "name": name_match.group(1),
                "version": version_match.group(1),
                "block": block,
            })
    return packages


def generate_master_from_lockfiles(output_dir: Path) -> tuple[bool, str]:
    """merge all resolved uv.lock files into one master lockfile.

    combines every unique (name, version) pair from all individual lockfiles.
    no re-resolution — just aggregation of what was already resolved.
    """
    # find all uv.lock files except any existing master
    lockfiles = sorted(
        p for p in output_dir.rglob("uv.lock")
        if p.parent.name != "master"
    )

    if not lockfiles:
        return False, "no lockfiles to consolidate"

    # collect unique packages by (name, version)
    seen: dict[tuple[str, str], str] = {}
    for lockfile in lockfiles:
        for pkg in parse_uv_lock_packages(lockfile):
            key = (pkg["name"], pkg["version"])
            if key not in seen:
                seen[key] = pkg["block"]

    if not seen:
        return False, "no packages found in lockfiles"

    # filter out synthetic project entries (generated pyproject.toml placeholders)
    seen = {k: v for k, v in seen.items() if k[1] != "0.0.0"}

    # sort by (name, version) for deterministic output
    sorted_packages = sorted(seen.items(), key=lambda kv: (kv[0][0].lower(), kv[0][1]))

    # build the master lockfile
    header = f'version = 1\nrequires-python = "{PYTHON_REQUIRES}"\n'
    body = "\n".join(block for _, block in sorted_packages)
    master_content = f"{header}\n{body}\n"

    dest = output_dir / "master"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "uv.lock").write_text(master_content)

    # also write a summary manifest for easy scanning
    manifest_lines = [f"{name}=={version}" for (name, version), _ in sorted_packages]
    (dest / "manifest.txt").write_text("\n".join(manifest_lines) + "\n")

    unique_pkgs = len(seen)
    unique_names = len({name for (name, _) in seen})
    return True, f"{unique_pkgs} packages ({unique_names} unique names) from {len(lockfiles)} lockfiles"


def run_npm_lock(workdir: Path) -> tuple[bool, str]:
    """run `npm install --package-lock-only` in the given directory."""
    try:
        result = subprocess.run(
            ["npm", "install", "--package-lock-only"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, result.stderr.strip()
        return False, f"exit {result.returncode}: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "timeout after 120s"
    except Exception as e:
        return False, str(e)


def process_package_json(
    pkg_file: Path, repo_dir: Path, output_dir: Path
) -> tuple[str, bool, str]:
    """process a single package.json. returns (name, success, message)."""
    rel_path = pkg_file.relative_to(repo_dir)
    dir_name = encode_path(rel_path)

    # read and count deps
    pkg_data = json.loads(pkg_file.read_text())
    deps = pkg_data.get("dependencies", {})
    dev_deps = pkg_data.get("devDependencies", {})
    total_deps = len(deps) + len(dev_deps)

    if total_deps == 0:
        return dir_name, True, "skipped (no deps)"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        shutil.copy2(pkg_file, tmp / "package.json")

        # copy .npmrc if it exists (for registry config)
        npmrc = pkg_file.parent / ".npmrc"
        if npmrc.exists():
            shutil.copy2(npmrc, tmp / ".npmrc")

        success, msg = run_npm_lock(tmp)

        if success:
            lock_file = tmp / "package-lock.json"
            if lock_file.exists():
                dest = output_dir / dir_name
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(lock_file, dest / "package-lock.json")
                shutil.copy2(tmp / "package.json", dest / "package.json")
                return dir_name, True, f"locked ({total_deps} deps)"
            return dir_name, False, "npm succeeded but no package-lock.json generated"
        return dir_name, False, msg


def parse_package_lock_packages(lockfile: Path) -> dict[str, list[dict[str, str]]]:
    """parse resolved packages from a package-lock.json (lockfileVersion 3).

    returns {package_name: [{version, resolved, integrity}, ...]}
    """
    data = json.loads(lockfile.read_text())
    packages: dict[str, list[dict[str, str]]] = {}

    for path, info in data.get("packages", {}).items():
        # skip the root entry (empty string key)
        if not path:
            continue
        # extract package name from path (node_modules/@scope/name or node_modules/name)
        parts = path.split("node_modules/")
        if not parts:
            continue
        pkg_name = parts[-1]
        version = info.get("version", "")
        resolved = info.get("resolved", "")
        integrity = info.get("integrity", "")

        if not version:
            continue

        entry = {"version": version, "resolved": resolved, "integrity": integrity}
        if pkg_name not in packages:
            packages[pkg_name] = []
        # avoid duplicate (name, version) pairs
        if not any(e["version"] == version for e in packages[pkg_name]):
            packages[pkg_name].append(entry)

    return packages


def generate_node_master_from_lockfiles(output_dir: Path) -> tuple[bool, str]:
    """merge all resolved package-lock.json files into one master manifest.

    combines every unique (name, version) pair from all individual lockfiles.
    """
    lockfiles = sorted(
        p for p in output_dir.rglob("package-lock.json")
        if p.parent.name != "master"
    )

    if not lockfiles:
        return False, "no lockfiles to consolidate"

    # collect all unique (name, version) -> {resolved, integrity}
    all_packages: dict[str, dict[str, dict[str, str]]] = {}

    for lockfile in lockfiles:
        for pkg_name, entries in parse_package_lock_packages(lockfile).items():
            if pkg_name not in all_packages:
                all_packages[pkg_name] = {}
            for entry in entries:
                version = entry["version"]
                if version not in all_packages[pkg_name]:
                    all_packages[pkg_name][version] = entry

    if not all_packages:
        return False, "no packages found in lockfiles"

    dest = output_dir / "master"
    dest.mkdir(parents=True, exist_ok=True)

    # write a JSON manifest with all resolved packages
    master_data: dict[str, list[dict[str, str]]] = {}
    for pkg_name in sorted(all_packages.keys()):
        versions = all_packages[pkg_name]
        master_data[pkg_name] = sorted(versions.values(), key=lambda e: e["version"])

    (dest / "resolved-packages.json").write_text(json.dumps(master_data, indent=2) + "\n")

    # also write a flat manifest for easy scanning
    manifest_lines = []
    for pkg_name in sorted(all_packages.keys()):
        for version in sorted(all_packages[pkg_name].keys()):
            manifest_lines.append(f"{pkg_name}@{version}")

    (dest / "manifest.txt").write_text("\n".join(manifest_lines) + "\n")

    total_entries = sum(len(v) for v in all_packages.values())
    unique_names = len(all_packages)
    return True, f"{total_entries} packages ({unique_names} unique names) from {len(lockfiles)} lockfiles"


def run_python_lockfiles(repo_dir: Path, output_dir: Path) -> None:
    """generate all python lockfiles."""
    py_output = output_dir / "python"
    py_output.mkdir(parents=True, exist_ok=True)

    # --- requirements.txt files ---
    req_files = sorted(repo_dir.rglob("requirements.txt"))
    print(f"\n=== requirements.txt files: {len(req_files)} ===\n")

    succeeded = 0
    skipped = 0
    failed = 0

    for req_file in req_files:
        name, success, msg = process_requirements_txt(req_file, repo_dir, py_output)
        status = "OK" if success else "FAIL"
        if "skipped" in msg:
            status = "SKIP"
            skipped += 1
        elif success:
            succeeded += 1
        else:
            failed += 1
        print(f"  [{status}] {name}: {msg}")

    print(f"\n  requirements.txt: {succeeded} locked, {skipped} skipped, {failed} failed")

    # --- lib/ pyproject.toml files ---
    lib_pyprojects = sorted(repo_dir.glob("lib/*/pyproject.toml"))
    print(f"\n=== lib/ pyproject.toml files: {len(lib_pyprojects)} ===\n")

    lib_succeeded = 0
    lib_failed = 0
    for pyproject_file in lib_pyprojects:
        name, success, msg = process_lib_pyproject(pyproject_file, repo_dir, py_output)
        status = "OK" if success else "FAIL"
        if success:
            lib_succeeded += 1
        else:
            lib_failed += 1
        print(f"  [{status}] {name}: {msg}")

    print(f"\n  lib/: {lib_succeeded} locked, {lib_failed} failed")

    # --- master: merge all resolved lockfiles ---
    print(f"\n=== python master (merged from resolved lockfiles) ===\n")
    success, msg = generate_master_from_lockfiles(py_output)
    status = "OK" if success else "FAIL"
    print(f"  [{status}] master: {msg}")

    total_lockfiles = len(list(py_output.rglob("uv.lock")))
    print(f"\n  python: {total_lockfiles} lockfiles in {py_output}")


def run_node_lockfiles(repo_dir: Path, output_dir: Path) -> None:
    """generate all node lockfiles."""
    node_output = output_dir / "node"
    node_output.mkdir(parents=True, exist_ok=True)

    # find all package.json, excluding node_modules and deps/ output
    pkg_files = sorted(
        p for p in repo_dir.rglob("package.json")
        if "node_modules" not in p.parts and "deps" not in p.parts
    )
    print(f"\n=== package.json files: {len(pkg_files)} ===\n")

    succeeded = 0
    skipped = 0
    failed = 0

    for pkg_file in pkg_files:
        name, success, msg = process_package_json(pkg_file, repo_dir, node_output)
        status = "OK" if success else "FAIL"
        if "skipped" in msg:
            status = "SKIP"
            skipped += 1
        elif success:
            succeeded += 1
        else:
            failed += 1
        print(f"  [{status}] {name}: {msg}")

    print(f"\n  total: {succeeded} locked, {skipped} skipped, {failed} failed")

    # --- master: merge all resolved lockfiles ---
    print(f"\n=== node master (merged from resolved lockfiles) ===\n")
    success, msg = generate_node_master_from_lockfiles(node_output)
    status = "OK" if success else "FAIL"
    print(f"  [{status}] master: {msg}")

    total_lockfiles = len(list(node_output.rglob("package-lock.json")))
    print(f"\n  node: {total_lockfiles} lockfiles in {node_output}")


def main() -> None:
    args = parse_args()
    repo_dir = args.repo_dir.resolve()
    output_dir = args.output_dir.resolve()

    if not repo_dir.exists():
        print(f"error: repo dir not found: {repo_dir}")
        raise SystemExit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    run_python = not args.node_only
    run_node = not args.python_only

    if run_python:
        run_python_lockfiles(repo_dir, output_dir)

    if run_node:
        run_node_lockfiles(repo_dir, output_dir)

    print("\n=== all done ===\n")


if __name__ == "__main__":
    main()
