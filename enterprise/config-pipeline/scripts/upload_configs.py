#!/usr/bin/env python3
"""
Upload IDP document configurations to the target stack.

Run by the config pipeline's CodeBuild stage. The working directory is the
unpacked config artifact (the zip produced by the config repository's CI), so
config files are discovered relative to the current directory.

Every config in the artifact is uploaded on every run. That is deliberate: the
config repository is the source of truth, and a config can also be edited in the
Web UI between runs, so a zip-to-zip diff would silently skip a version that had
drifted. Re-uploading an unchanged config is safe -- ConfigurationManager
preserves IsActive and CreatedAt, so only UpdatedAt changes.

Configs must be exported with `config-download --format full` (the default). Then
the uploaded version becomes an exact copy of the source, deletions included.

`config-upload` applies the YAML as a recursive dict.update() -- not a code-style
three-way merge -- so every key present in the file overwrites what the target
had, and `--format full` emits every key. Lists (`classes`, `policy_classes`) are
replaced wholesale rather than merged element-by-element, so deleting a class or
an attribute inside a class propagates.

Stale data survives only for a key ABSENT from the upload, which nothing tells
the target to change. That is what `--format minimal` causes: it strips keys
matching a default, so a target holding an override would keep it. A null means
"restore to default" rather than "set to null".

Environment variables (set by CodeBuild):
  IDP_STACK_NAME        target IDP stack name (required)
  CONFIG_MANIFEST_NAME  optional manifest filename at the artifact root
"""

import glob
import os
import subprocess
import sys

import yaml

IDP_STACK_NAME = os.environ.get("IDP_STACK_NAME", "")
MANIFEST_NAME = os.environ.get("CONFIG_MANIFEST_NAME", "configs-manifest.yaml")

# Extensions accepted for a config file, in preference order. Used both when
# globbing and when resolving a bare version name from the manifest.
CONFIG_EXTENSIONS = (".yaml", ".yml")


def load_manifest():
    """Load the optional manifest from the config artifact root.

    Absent manifest is the normal case and means "upload everything".
    """
    if not os.path.exists(MANIFEST_NAME):
        print(f"No {MANIFEST_NAME} in the artifact - uploading every config found")
        return {}

    try:
        with open(MANIFEST_NAME, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f) or {}
    except Exception as e:
        # A manifest that exists but cannot be parsed is an authoring error.
        # Uploading everything anyway could promote configs the author meant to
        # hold back, so fail instead of guessing.
        print(f"ERROR: {MANIFEST_NAME} exists but could not be parsed: {e}")
        sys.exit(1)

    if not isinstance(manifest, dict):
        print(f"ERROR: {MANIFEST_NAME} must contain a YAML mapping")
        sys.exit(1)

    # The target stack comes from the pipeline's CloudFormation parameter only.
    # Honouring a stack_name here would let a file inside the artifact retarget
    # the promotion -- e.g. point a dev config drop at the production stack.
    if "stack_name" in manifest:
        print(
            f"WARNING: ignoring 'stack_name' in {MANIFEST_NAME}. The target stack "
            "is fixed by the pipeline's IdpStackName parameter and cannot be "
            "overridden from inside the artifact."
        )

    print(f"Loaded manifest {MANIFEST_NAME}")
    return manifest


def find_config_files():
    """Find every config file at the artifact root, deduped by version name.

    If both <name>.yaml and <name>.yml exist they would upload to the same
    version, with the winner decided by sort order. Treat that as an error
    rather than letting one silently overwrite the other.
    """
    by_version: dict[str, list[str]] = {}
    for ext in CONFIG_EXTENSIONS:
        for path in glob.glob(f"*{ext}"):
            if os.path.basename(path) == MANIFEST_NAME:
                continue
            by_version.setdefault(version_of(path), []).append(path)

    conflicts = {v: p for v, p in by_version.items() if len(p) > 1}
    if conflicts:
        for version, paths in sorted(conflicts.items()):
            print(f"ERROR: version '{version}' matches multiple files: {sorted(paths)}")
        sys.exit(1)

    return sorted(paths[0] for paths in by_version.values())


def resolve_manifest_entry(entry):
    """Resolve a manifest entry to a path on disk.

    Entries are version names ("lending-v2"), but a filename with an extension
    is accepted too. Returns None when nothing matches.
    """
    if entry.endswith(CONFIG_EXTENSIONS):
        return entry if os.path.exists(entry) else None

    for ext in CONFIG_EXTENSIONS:
        candidate = f"{entry}{ext}"
        if os.path.exists(candidate):
            return candidate
    return None


def version_of(config_file):
    """Version name for a config file: its basename without the extension."""
    return os.path.splitext(os.path.basename(config_file))[0]


def upload_config(config_file, version, stack_name):
    """Upload a single config version using idp-cli."""
    print(f"\n  Uploading {config_file} as version '{version}' to {stack_name}")

    cmd = [
        "idp-cli",
        "config-upload",
        "--stack-name",
        stack_name,
        "--config-file",
        config_file,
        "--config-version",
        version,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        # The install phase is supposed to hard-fail before this point; if it
        # somehow did not, say so plainly rather than dying on a bare traceback.
        print("  FAILED: idp-cli is not installed or not on PATH")
        return False

    if result.returncode != 0:
        print(f"  FAILED: {version} (exit {result.returncode})")
        if result.stdout:
            print(f"  stdout: {result.stdout}")
        if result.stderr:
            print(f"  stderr: {result.stderr}")
        return False

    print(f"  OK: {version}")
    return True


def main():
    if not IDP_STACK_NAME:
        print("ERROR: IDP_STACK_NAME not set")
        sys.exit(1)

    manifest = load_manifest()
    stack_name = IDP_STACK_NAME

    print(f"Working directory: {os.getcwd()}")
    print(f"Target stack: {stack_name}")

    requested = manifest.get("config_versions")
    missing = []

    if requested:
        if not isinstance(requested, list):
            print(f"ERROR: 'config_versions' in {MANIFEST_NAME} must be a list")
            sys.exit(1)

        config_files = []
        for entry in requested:
            path = resolve_manifest_entry(str(entry))
            if path:
                config_files.append(path)
            else:
                missing.append(str(entry))

        print(f"Manifest lists {len(requested)} config version(s)")
        for entry in missing:
            print(f"  MISSING: no file in the artifact for '{entry}'")
    else:
        config_files = find_config_files()
        print(f"Found {len(config_files)} config file(s) in the artifact")

    if not config_files and not missing:
        # Nothing to do and nothing wrong. Succeed so an empty drop is not
        # reported as a pipeline failure.
        print("No config files found. Nothing to upload.")
        sys.exit(0)

    succeeded, failed = [], list(missing)
    for config_file in config_files:
        version = version_of(config_file)
        if upload_config(config_file, version, stack_name):
            succeeded.append(version)
        else:
            failed.append(version)

    print(f"\nDone: {len(succeeded)} uploaded, {len(failed)} failed")
    if succeeded:
        print(f"  uploaded: {', '.join(sorted(succeeded))}")
    if failed:
        print(f"  failed:   {', '.join(sorted(failed))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
