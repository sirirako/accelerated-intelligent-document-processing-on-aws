#!/usr/bin/env python3
"""
verify all packages from the node master manifest can be fetched from a registry.

sends a HEAD request to `{registry}/{name}/{version}` for each entry in the
manifest and reports pass/fail.

env vars:
    NODE_REGISTRY_URL  - registry base URL (default: https://registry.npmjs.org)
    NODE_REGISTRY_AUTH - Authorization header value (e.g. "Bearer <token>")

usage:
    python scripts/verify_node_packages.py [--manifest PATH] [--concurrency N]
"""

import argparse
import os
import concurrent.futures
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


REGISTRY_URL = os.environ.get("NODE_REGISTRY_URL", "https://registry.npmjs.org").rstrip("/")
REGISTRY_AUTH = os.environ.get("NODE_REGISTRY_AUTH", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="verify node packages from master manifest")
    default_manifest = Path(__file__).resolve().parent.parent / "deps" / "node" / "master" / "manifest.txt"
    parser.add_argument(
        "--manifest",
        type=Path,
        default=default_manifest,
        help="path to manifest.txt (default: deps/node/master/manifest.txt)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=20,
        help="max concurrent requests (default: 20)",
    )
    return parser.parse_args()


def parse_manifest_entry(entry: str) -> tuple[str, str]:
    """parse 'name@version' into (name, version). handles scoped packages like @scope/name@version."""
    # last @ is the version separator (scoped packages have @ in the name)
    idx = entry.rfind("@")
    if idx <= 0:
        raise ValueError(f"invalid manifest entry: {entry}")
    return entry[:idx], entry[idx + 1:]


def check_package(name: str, version: str) -> tuple[str, str, bool, str]:
    """HEAD request to registry for name/version. returns (name, version, ok, error)."""
    url = f"{REGISTRY_URL}/{name}/{version}"
    req = Request(url, method="HEAD")
    req.add_header("Accept", "application/json")
    if REGISTRY_AUTH:
        req.add_header("Authorization", REGISTRY_AUTH)

    try:
        resp = urlopen(req, timeout=15)
        resp.close()
        return name, version, True, ""
    except HTTPError as e:
        return name, version, False, f"HTTP {e.code}"
    except URLError as e:
        return name, version, False, str(e.reason)
    except Exception as e:
        return name, version, False, str(e)


def main() -> None:
    args = parse_args()

    if not args.manifest.exists():
        print(f"error: manifest not found: {args.manifest}")
        raise SystemExit(1)

    entries = [
        stripped for line in args.manifest.read_text().splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]

    print(f"\n=== verifying {len(entries)} node packages ===")
    print(f"  registry: {REGISTRY_URL}")
    if REGISTRY_AUTH:
        print(f"  auth: (set)")
    print()

    passed: list[str] = []
    failed: list[tuple[str, str]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {}
        for entry in entries:
            try:
                name, version = parse_manifest_entry(entry)
            except ValueError as e:
                failed.append((entry, str(e)))
                print(f"  [--/{len(entries)}] FAIL {entry}: {e}")
                continue
            fut = pool.submit(check_package, name, version)
            futures[fut] = entry

        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            entry = futures[fut]
            name, version, ok, err = fut.result()
            if ok:
                passed.append(entry)
                print(f"  [{i}/{len(entries)}] OK   {entry}")
            else:
                failed.append((entry, err))
                print(f"  [{i}/{len(entries)}] FAIL {entry}: {err}")

    # summary
    print(f"\n=== results ===\n")
    print(f"  passed: {len(passed)}/{len(entries)}")
    print(f"  failed: {len(failed)}/{len(entries)}")

    if failed:
        print(f"\n=== failed packages ===\n")
        for pkg, err in failed:
            print(f"  {pkg}: {err}")

    # write results alongside manifest
    results_dir = args.manifest.parent
    (results_dir / "verify-passed.txt").write_text(
        ("\n".join(sorted(passed)) + "\n") if passed else ""
    )
    (results_dir / "verify-failed.txt").write_text(
        ("\n".join(f"{pkg}: {err}" for pkg, err in sorted(failed)) + "\n") if failed else ""
    )
    print(f"\n  results written to {results_dir}/verify-passed.txt and verify-failed.txt\n")

    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
