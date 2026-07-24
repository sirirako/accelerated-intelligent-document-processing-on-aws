# Customer Repo Sync Guide

How to maintain the customer's air-gapped repository with enterprise releases.

## Overview

The customer's repo is a manual fork of our `enterprise/develop` branch. Updates
are delivered as zip files (GitHub releases). The customer may also have their own
local commits (config changes, fixes). This guide covers both the initial setup
and the ongoing update process.

## One-time setup (replace customer main with our fork)

Run this once to establish the baseline. This replaces all existing code on the
customer's main branch with our enterprise fork.

```powershell
# In the customer's repo directory
git checkout main
git rm -rf .
Expand-Archive -Path .\release-v0.2.5.zip -DestinationPath . -Force
git add -A
git commit -m "chore: replace with enterprise fork v0.2.5 (upstream v0.6.1)"
git push origin main --force
```

After this, the customer's `main` is identical to our `enterprise/develop` at
that release point.

## Ongoing updates (merge new release into customer main)

When a new release is available:

### Step 1: Create a branch from the release zip

```powershell
git checkout main
git checkout -b upstream-v0.2.6
git rm -rf .
Expand-Archive -Path .\release-v0.2.6.zip -DestinationPath . -Force
git add -A
git commit -m "upstream: v0.2.6"
```

### Step 2: Merge into main

```powershell
git checkout main
git merge upstream-v0.2.6
```

If there are conflicts (customer's local changes vs our update), resolve them,
then:

```powershell
git add -A
git commit
```

### Step 3: Push

```powershell
git push origin main
```

### Step 4: Clean up the branch (optional)

```powershell
git branch -d upstream-v0.2.6
```

## When customer sends changes back

If the customer makes fixes or improvements that should come back to us:

1. Customer creates a patch:
   ```powershell
   git format-patch main~3  # last 3 commits, adjust as needed
   ```
   Or zips their branch/diff.

2. Send the patch files to us (email, shared drive, etc.)

3. We apply on our side:
   ```bash
   git am *.patch
   ```

## Tips

- **Why `git rm -rf .` before unzipping?** — Ensures files deleted or renamed in
  the new release don't linger from the old version.
- **Merge conflicts** — Most likely in `enterprise/environments/local-*.yaml`
  (customer's config) or any file both sides modified. Customer's config files
  should be in `.gitignore` to avoid this.
- **Testing after merge** — Run the pipeline after merging to verify the update
  deploys successfully.
- **Release naming** — Use semantic versions: `v0.2.5`, `v0.2.6`, etc. The
  branch name `upstream-vX.Y.Z` makes it clear what's being merged.

## Diagram

```
Our fork (GitHub)              Customer repo (air-gapped)
─────────────────              ──────────────────────────

enterprise/develop             main
      │                           │
      ├─ release zip ──────────►  ├─ upstream-v0.2.5 (from zip)
      │                           │       │
      │                           │       └─── merge ──► main
      │                           │                        │
      │                           │              customer commits
      │                           │                        │
      ├─ release zip ──────────►  ├─ upstream-v0.2.6 (from zip)
      │                           │       │
      │                           │       └─── merge ──► main
```
