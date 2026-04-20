---
title: "Artifactory Dependency Workaround Guide"
---

# Artifactory Dependency Workaround Guide

**Document Purpose:** This guide describes how to resolve dependency download failures when Artifactory is used as the only package registry and public registries (PyPI, npm, Docker Hub, GitHub Container Registry) are blocked.

---

## Table of Contents

1. [Overview & Root Cause](#1-overview--root-cause)
2. [Complete Dependency Inventory](#2-complete-dependency-inventory)
3. [Option 1 — Configure Artifactory as a Remote Proxy (Recommended)](#3-option-1--configure-artifactory-as-a-remote-proxy-recommended)
4. [Option 2 — Bridge Machine: Download & Upload Missing Packages](#4-option-2--bridge-machine-download--upload-missing-packages)
5. [Option 5 — Automated Manifest Generation (Recommended Pre-Step for Option 2)](#5-option-5--automated-manifest-generation-recommended-pre-step-for-option-2)
6. [Option 3 — Vendor Dependencies into the Repository (Fully Air-Gapped)](#6-option-3--vendor-dependencies-into-the-repository-fully-air-gapped)
7. [Option 4 — Point Build Tools to Artifactory Explicitly](#7-option-4--point-build-tools-to-artifactory-explicitly)
8. [Decision Guide](#8-decision-guide)
9. [Quick Reference: Copy-Paste Commands](#9-quick-reference-copy-paste-commands)

---

## 1. Overview & Root Cause

### What Is Happening

This project downloads dependencies from public registries during builds:

| Tool | Registry | Used for |
|------|----------|----------|
| `pip` / `uv` | `https://pypi.org/simple/` | Python packages |
| `npm` | `https://registry.npmjs.org/` | JavaScript / UI packages |
| `docker pull` | `ghcr.io` (GitHub Container Registry) | `uv` build tool image |
| `docker pull` | `public.ecr.aws` | AWS Lambda Python base image |

When **Artifactory is the only allowed registry** and packages are not in its cache, installations fail with errors such as:

```
ERROR: Could not find a version that satisfies the requirement strands-agents==1.14.0
ERROR: No matching distribution found for bedrock-agentcore>=0.1.1
npm ERR! code E404 - Not Found
```

### Why Packages Are Missing from Artifactory

Artifactory caches packages **on first request**. Packages that have never been requested, or were added after the last cache refresh, will be missing. The solution is one of:

- Enable Artifactory to proxy public registries (preferred)
- Manually upload the missing packages to Artifactory
- Vendor the packages directly in the repository

---

## 2. Complete Dependency Inventory

### 2.1 Python Dependencies

#### Core Library (`lib/idp_common_pkg/pyproject.toml`)

```
boto3==1.42.0
jsonschema>=4.25.1
pydantic>=2.12.0
deepdiff>=6.0.0
PyYAML>=6.0.0
Pillow==12.1.1
pypdfium2>=5.5.0
amazon-textract-textractor[pandas]==1.9.2
numpy==1.26.4
pandas==2.2.3
openpyxl==3.1.5
python-docx==1.2.0
strands-agents==1.14.0
strands-agents-tools==0.2.22
bedrock-agentcore>=0.1.1
stickler-eval==0.1.4
genson==1.3.0
munkres>=1.1.4
requests==2.33.0
pyarrow==20.0.0
aws-lambda-powertools>=3.2.0
jsonpatch==1.33
email-validator>=2.3.0
tabulate>=0.9.0
datamodel-code-generator>=0.25.0
mypy-boto3-bedrock-runtime>=1.39.0
ruamel-yaml>=0.17.0,<0.19.0
aws-xray-sdk>=2.14.0
genson==1.3.0
```

#### Lambda Function Dependencies (`src/lambda/*/requirements.txt`)

```
huggingface-hub==0.20.0
cfnresponse
crhelper~=2.0.10
aws-requests-auth==0.4.3
bedrock_agentcore_starter_toolkit
urllib3>=1.26.0
pypdf>=4.0.0
```

#### Development / Test Dependencies

```
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-xdist>=3.3.1
pytest-asyncio>=1.1.0
pytest-mock>=3.11.1
moto[s3]==5.1.8
ruff>=0.14.0
typer>=0.19.2
rich>=13.0.0
cfn-lint
basedpyright
build==1.3.0
python-dotenv>=1.1.0
```

### 2.2 Node.js (npm) Dependencies

Located in `src/ui/package.json` and `docs-site/package.json`.

**Key packages include:**
- `react`, `react-dom`
- `@aws-amplify/ui-react`
- `@aws-appsync/gql`
- AWS AppSync codegen libraries
- `astro` (docs site)

To get the full list:
```bash
cat src/ui/package.json | jq '.dependencies, .devDependencies'
cat docs-site/package.json | jq '.dependencies, .devDependencies'
```

### 2.3 Docker Base Images

| Image | Registry | Purpose |
|-------|----------|---------|
| `ghcr.io/astral-sh/uv:0.9.6` | GitHub Container Registry | `uv` Python package installer (multi-stage build) |
| `public.ecr.aws/lambda/python:3.12-arm64` | AWS Public ECR | Lambda function runtime base image |

---

## 3. Option 1 — Configure Artifactory as a Remote Proxy *(Recommended)*

**Best for:** Long-term fix. All future installs work transparently. No code changes required.

**Who performs this:** Your Artifactory administrator.

### Steps for Artifactory Admin

#### A. Add PyPI Remote Repository

1. Log into Artifactory → **Administration** → **Repositories** → **Remote**
2. Click **New Remote Repository**
3. Set:
   - **Package Type:** `PyPI`
   - **Repository Key:** `pypi-remote` (or any name)
   - **URL:** `https://pypi.org/`
4. Save

#### B. Add npm Remote Repository

1. Click **New Remote Repository**
2. Set:
   - **Package Type:** `npm`
   - **Repository Key:** `npm-remote`
   - **URL:** `https://registry.npmjs.org`
3. Save

#### C. Add Docker Remote Repositories

For `ghcr.io` (GitHub Container Registry):
1. Click **New Remote Repository**
2. Set:
   - **Package Type:** `Docker`
   - **Repository Key:** `ghcr-remote`
   - **URL:** `https://ghcr.io`
3. Save

For AWS Public ECR (`public.ecr.aws`):
1. Click **New Remote Repository**
2. Set:
   - **Package Type:** `Docker`
   - **Repository Key:** `ecr-public-remote`
   - **URL:** `https://public.ecr.aws`
3. Save

#### D. Create Virtual Repositories (Aggregate local + remote)

Create virtual repositories that front your local + remote repos for seamless access:
- `pypi-virtual` → includes `pypi-local` + `pypi-remote`
- `npm-virtual` → includes `npm-local` + `npm-remote`
- `docker-virtual` → includes `docker-local` + `ghcr-remote` + `ecr-public-remote`

### Developer Configuration (after admin sets up proxy)

```bash
# Set pip to use Artifactory
export PIP_INDEX_URL=https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/
export PIP_TRUSTED_HOST=your-artifactory.company.com

# Set uv to use Artifactory
export UV_INDEX_URL=https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/

# Set npm to use Artifactory
npm config set registry https://your-artifactory.company.com/artifactory/api/npm/npm-virtual/

# Then run setup as normal
make setup-venv
```

---

## 4. Option 2 — Bridge Machine: Download & Upload Missing Packages

**Best for:** When you cannot change Artifactory config but have a machine that can reach the internet AND Artifactory.

```mermaid
flowchart LR
    Internet[Public Internet\nPyPI / npm / Docker Hub]
    Bridge[Bridge Machine\ninternet + Artifactory access]
    AF[Artifactory\ninternal only]
    Dev[Developer Machine\nArtifactory only]
    
    Internet -->|1. Download packages| Bridge
    Bridge -->|2. Upload to Artifactory| AF
    AF -->|3. Install packages| Dev
```

> **Tip:** Use [Option 5 — Automated Manifest Generation](#5-option-5--automated-manifest-generation-recommended-pre-step-for-option-2) first to get a complete, fully-resolved list of all packages (including transitive dependencies) before running the bridge machine download steps below. This avoids the common mistake of only downloading direct dependencies and missing transitive ones.

### Python Packages

**On the bridge machine (internet access):**

```bash
# If you have run Option 5, use the generated manifest directly:
mkdir -p ./wheel-cache
while IFS= read -r pkg; do
  pip download -d ./wheel-cache "$pkg" 2>/dev/null || echo "WARN: $pkg not downloaded"
done < deps/python/master/manifest.txt

# Alternatively, download specific packages manually:
# For Linux ARM64 (used by Lambda container images)
pip download \
  --platform manylinux2014_aarch64 \
  --python-version 312 \
  --only-binary=:all: \
  -d ./wheel-cache \
  "boto3==1.42.0" \
  "strands-agents==1.14.0" \
  "strands-agents-tools==0.2.22" \
  "bedrock-agentcore>=0.1.1" \
  "stickler-eval==0.1.4" \
  "Pillow==12.1.1" \
  "pypdfium2>=5.5.0" \
  "pyarrow==20.0.0" \
  "numpy==1.26.4" \
  "huggingface-hub==0.20.0" \
  "cfnresponse" \
  "crhelper~=2.0.10" \
  "aws-requests-auth==0.4.3" \
  "bedrock_agentcore_starter_toolkit"

# Download remaining packages for local dev (your OS/arch)
pip download \
  -d ./wheel-cache-local \
  -e "lib/idp_common_pkg[all,dev,test]" \
  -e lib/idp_cli_pkg \
  -e lib/idp_sdk \
  -e lib/idp_mcp_connector_pkg
```

**Upload to Artifactory via REST API:**

```bash
ARTIFACTORY_URL="https://your-artifactory.company.com/artifactory"
REPO="pypi-local"
AF_USER="your-username"
AF_PASSWORD="your-password-or-api-key"

for whl in ./wheel-cache/*.whl ./wheel-cache/*.tar.gz; do
  filename=$(basename "$whl")
  echo "Uploading $filename ..."
  curl -u "${AF_USER}:${AF_PASSWORD}" \
    -T "$whl" \
    "${ARTIFACTORY_URL}/${REPO}/${filename}"
done
```

**Or upload via Artifactory Web UI:**
1. Navigate to **Artifactory** → **Artifacts**
2. Select your `pypi-local` repository
3. Click **Deploy** → Upload `.whl` files from `./wheel-cache/`

### Docker Images

```bash
# Pull from public registries
docker pull ghcr.io/astral-sh/uv:0.9.6
docker pull public.ecr.aws/lambda/python:3.12-arm64

# Re-tag for your Artifactory Docker registry
docker tag ghcr.io/astral-sh/uv:0.9.6 \
  your-artifactory.company.com/docker-local/astral-sh/uv:0.9.6

docker tag public.ecr.aws/lambda/python:3.12-arm64 \
  your-artifactory.company.com/docker-local/lambda/python:3.12-arm64

# Push to Artifactory
docker login your-artifactory.company.com
docker push your-artifactory.company.com/docker-local/astral-sh/uv:0.9.6
docker push your-artifactory.company.com/docker-local/lambda/python:3.12-arm64
```

Then update `Dockerfile.optimized` lines 1 and 6:
```dockerfile
# Line 1 - change FROM
FROM your-artifactory.company.com/docker-local/astral-sh/uv:0.9.6 AS uv

# Line 6 - change FROM
FROM your-artifactory.company.com/docker-local/lambda/python:3.12-arm64 AS builder
```

---

## 5. Option 5 — Automated Manifest Generation *(Recommended Pre-Step for Option 2)*

**Best for:** When you need to seed Artifactory with a complete, verified list of every resolved dependency — including all transitive dependencies — before executing the bridge machine workflow. Run this once on any internet-connected machine to produce authoritative manifests.

**Why this matters:** The manual approach in Option 2 lists only *direct* top-level dependencies. In practice, `boto3` alone pulls in dozens of sub-packages, and multi-platform build tools (esbuild, sharp, rollup) each have 20+ platform-specific optional binaries. Manually enumerating these is error-prone and almost always incomplete. This script uses `uv lock` and `pnpm install --lockfile-only` to perform full dependency-graph resolution and capture every package at its locked version.

```mermaid
flowchart LR
    A[Internet-connected machine] -->|Run generate_lockfiles.py| B[Per-component lockfiles\ndeps/python/ and deps/node/]
    B -->|Merge| C[Master manifests\ndeps/python/master/manifest.txt\ndeps/node/master/manifest.txt]
    C -->|Input to| D[Option 2: Bridge Machine\nDownload & Upload workflow]
    D --> E[Artifactory seeded\nBuilds work]
```

### Prerequisites

```bash
# Install uv (Python resolver)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install pnpm (Node resolver)
npm install -g pnpm
```

### Generate the Manifests

```bash
# From the repo root on any internet-connected machine
python3 scripts/generate_lockfiles.py

# Python only (skip Node resolution)
python3 scripts/generate_lockfiles.py --python-only

# Node only (skip Python resolution)
python3 scripts/generate_lockfiles.py --node-only
```

This scans all `requirements.txt`, `pyproject.toml` (in `lib/`), and `package.json` files in the repo. It generates:

| Output | Contents |
|--------|----------|
| `deps/python/master/manifest.txt` | Flat list of `name==version` for every resolved Python package (~295 packages) |
| `deps/node/master/manifest.txt` | Flat list of `name@version` for every resolved Node package (~1,524 packages) |
| `deps/python/<component>/uv.lock` | Per-component Python lockfiles for traceability |
| `deps/node/<component>/pnpm-lock.yaml` | Per-component Node lockfiles for traceability |

### Verify Packages Are Accessible from Artifactory

Before running a real build, use the verification scripts to confirm packages are reachable. Set the registry URL to your Artifactory endpoint:

```bash
# Verify Python packages
UV_INDEX_URL="https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/" \
  python3 scripts/verify_python_packages.py

# Results written to:
#   deps/python/master/verify-passed.txt
#   deps/python/master/verify-failed.txt

# Verify Node packages
NODE_REGISTRY_URL="https://your-artifactory.company.com/artifactory/api/npm/npm-virtual/" \
  python3 scripts/verify_node_packages.py

# Results written to:
#   deps/node/master/verify-passed.txt
#   deps/node/master/verify-failed.txt
```

### Use the Manifests with Option 2 (Bridge Machine)

Instead of manually listing packages, use the manifests as input to the bridge machine download step:

```bash
# On the bridge machine — download all Python packages from the manifest
mkdir -p ./wheel-cache
while IFS= read -r pkg; do
  pip download -d ./wheel-cache "$pkg" 2>/dev/null || echo "WARN: $pkg not downloaded"
done < deps/python/master/manifest.txt

# Upload all to Artifactory
ARTIFACTORY_URL="https://your-artifactory.company.com/artifactory"
REPO="pypi-local"
AF_CREDS="username:api-key"
for f in ./wheel-cache/*.whl ./wheel-cache/*.tar.gz; do
  curl -u "$AF_CREDS" -T "$f" "${ARTIFACTORY_URL}/${REPO}/$(basename $f)"
done
```

For Node packages, provide `deps/node/master/manifest.txt` to your Artifactory admin for bulk npm import via the Artifactory web UI or REST API.

### Known Caveats

| Issue | Details |
|-------|---------|
| **Windows-only packages** | `pywin32` and `pywinpty` appear in the Python manifest because they are pulled in transitively by Jupyter. These are Windows-only and will fail `pip install` on Linux — skip them if your build agents are Linux-only. They are listed in `deps/python/master/verify-failed.txt`. |
| **Docker images not included** | The two Docker base images (`ghcr.io/astral-sh/uv:0.9.6` and `public.ecr.aws/lambda/python:3.12-arm64`) are **not** in the manifests. Handle these separately using the Docker section of Option 2. |
| **Multiple versions of same package** | The master manifest intentionally keeps all versions (e.g., `boto3==1.42.0` and `boto3==1.42.80`) because different Lambda functions pin to different versions. Import all of them. |
| **Re-run on dependency changes** | When any `requirements.txt` or `pyproject.toml` version is bumped, re-run the script to regenerate the manifests before the next Artifactory seeding operation. |

### Keep Manifests Up to Date

Add this to your workflow when updating dependencies:

```bash
# After bumping any dependency version, regenerate manifests
python3 scripts/generate_lockfiles.py

# Review what changed
git diff deps/python/master/manifest.txt deps/node/master/manifest.txt
```

---

## 6. Option 3 — Vendor Dependencies into the Repository (Fully Air-Gapped)

**Best for:** Completely air-gapped environments with no internet access whatsoever.

This involves downloading all packages **once** on an internet-connected machine and committing them to the repository, so no registry is needed at install time.

### Setup (on a machine with internet access)

```bash
# Create vendor directories
mkdir -p vendor/python vendor/npm

# Download all Python wheels for local development
pip download \
  -d vendor/python \
  "boto3==1.42.0" \
  "jsonschema>=4.25.1" \
  "pydantic>=2.12.0" \
  "deepdiff>=6.0.0" \
  "PyYAML>=6.0.0" \
  "Pillow==12.1.1" \
  "pypdfium2>=5.5.0" \
  "strands-agents==1.14.0" \
  "strands-agents-tools==0.2.22" \
  "bedrock-agentcore>=0.1.1" \
  "stickler-eval==0.1.4" \
  "numpy==1.26.4" \
  "pandas==2.2.3" \
  "pyarrow==20.0.0" \
  "requests==2.33.0" \
  "huggingface-hub==0.20.0" \
  "cfnresponse" \
  "crhelper~=2.0.10" \
  "aws-requests-auth==0.4.3" \
  "pytest>=7.4.0" \
  "moto[s3]==5.1.8" \
  "ruff>=0.14.0" \
  "typer>=0.19.2" \
  "rich>=13.0.0"

# Pack npm dependencies
cd src/ui && npm pack --pack-destination ../../vendor/npm
cd ../../docs-site && npm pack --pack-destination ../vendor/npm
cd ..
```

### Install from Vendor Directory (no network needed)

```bash
# Python
pip install --no-index --find-links vendor/python \
  -e "lib/idp_common_pkg[all,dev,test]" \
  -e lib/idp_cli_pkg \
  -e lib/idp_sdk \
  -e lib/idp_mcp_connector_pkg

# npm (configure local registry)
cd src/ui && npm install --prefer-offline --cache ../../vendor/npm
```

### Add a Makefile Target for Vendored Install

Add this to `Makefile`:

```makefile
setup-vendored: ## Install from local vendor/ directory (no network required)
	@echo "Installing from vendor directory (no-index mode)..."
	$(PIP) install --no-index --find-links vendor/python \
		-e "lib/idp_common_pkg[all,dev,test]" \
		-e lib/idp_cli_pkg \
		-e lib/idp_sdk \
		-e lib/idp_mcp_connector_pkg
	@echo -e "$(GREEN)✅ Vendored install complete!$(NC)"
```

### Add `vendor/` to `.gitignore` or commit it

If committing to git (fully self-contained):
```bash
# Remove vendor/ from .gitignore if present
grep -v "^vendor/" .gitignore > .gitignore.tmp && mv .gitignore.tmp .gitignore

# Commit
git add vendor/
git commit -m "Add vendored dependencies for air-gapped deployment"
```

---

## 7. Option 4 — Point Build Tools to Artifactory Explicitly

**Best for:** When Artifactory *does* have the packages but the build tools are not configured to use it (wrong index URL).

### Configure pip

Create or update `~/.pip/pip.conf` (macOS/Linux) or `%APPDATA%\pip\pip.ini` (Windows):

```ini
[global]
index-url = https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/
trusted-host = your-artifactory.company.com
```

Or use environment variables (temporary, no file changes):

```bash
export PIP_INDEX_URL=https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/
export PIP_TRUSTED_HOST=your-artifactory.company.com
```

### Configure uv

`uv` (used in `Dockerfile.optimized` and optionally in CI) reads:

```bash
export UV_INDEX_URL=https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/
```

Or create `~/.config/uv/uv.toml`:

```toml
[pip]
index-url = "https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/"
```

### Configure npm

```bash
# Set globally
npm config set registry https://your-artifactory.company.com/artifactory/api/npm/npm-virtual/

# OR create a project-level .npmrc file
echo "registry=https://your-artifactory.company.com/artifactory/api/npm/npm-virtual/" \
  > src/ui/.npmrc
echo "registry=https://your-artifactory.company.com/artifactory/api/npm/npm-virtual/" \
  > docs-site/.npmrc
```

### Configure Docker

```bash
# Configure Docker to use Artifactory as a mirror
# Edit /etc/docker/daemon.json (Linux) or Docker Desktop settings:
{
  "registry-mirrors": [
    "https://your-artifactory.company.com/artifactory/docker-virtual"
  ]
}
```

---

## 8. Decision Guide

```mermaid
flowchart TD
    A[Artifactory: packages failing] --> B{Can Artifactory admin\nadd remote proxy repos?}
    
    B -->|Yes| C[✅ Option 1\nConfigure Artifactory\nas remote proxy\nBest long-term fix]
    
    B -->|No| D{Is there a bridge machine\nwith internet AND\nArtifactory access?}
    
    D -->|Yes| E[Run Option 5 first\ngenerate_lockfiles.py\nGet complete manifest]
    E --> E2[✅ Option 2\nUse manifest to download\n& upload to Artifactory]
    
    D -->|No| F{Are packages in Artifactory\nbut URL is wrong?}
    
    F -->|Yes| G[✅ Option 4\nPoint pip/npm/uv\nexplicitly to Artifactory URL]
    
    F -->|No / Fully air-gapped| H[✅ Option 3\nVendor dependencies\ninto git repository]
    
    style C fill:#90EE90
    style E fill:#87CEEB
    style E2 fill:#90EE90
    style G fill:#90EE90
    style H fill:#90EE90
```

---

## 9. Quick Reference: Copy-Paste Commands

### Option 5 — Generate Complete Dependency Manifests (run this before Option 2)

```bash
# Requires uv and pnpm installed
python3 scripts/generate_lockfiles.py

# Outputs:
#   deps/python/master/manifest.txt   (~295 Python packages)
#   deps/node/master/manifest.txt     (~1,524 Node packages)
```

### Identify Missing Packages (run this first)

```bash
# Capture all errors during setup to identify exactly which packages are failing
make setup-venv 2>&1 | tee /tmp/setup-errors.txt
grep -E "ERROR|Could not find|No matching|WARN" /tmp/setup-errors.txt
```

### Option 1 — Temporary environment variables to use Artifactory

```bash
# Replace with your actual Artifactory URL
ARTIFACTORY_URL="https://your-artifactory.company.com/artifactory"

export PIP_INDEX_URL="${ARTIFACTORY_URL}/api/pypi/pypi-virtual/simple/"
export PIP_TRUSTED_HOST="your-artifactory.company.com"
export UV_INDEX_URL="${ARTIFACTORY_URL}/api/pypi/pypi-virtual/simple/"
npm config set registry "${ARTIFACTORY_URL}/api/npm/npm-virtual/"

make setup-venv
```

### Option 2 — Download + Upload using generated manifest

```bash
# Download all packages listed in the manifest
mkdir -p ./wheel-cache
while IFS= read -r pkg; do
  pip download -d ./wheel-cache "$pkg" 2>/dev/null || echo "WARN: $pkg"
done < deps/python/master/manifest.txt

# Upload to Artifactory
ARTIFACTORY_URL="https://your-artifactory.company.com/artifactory"
REPO="pypi-local"
AF_CREDS="username:api-key"
for f in ./wheel-cache/*.whl ./wheel-cache/*.tar.gz; do
  curl -u "$AF_CREDS" -T "$f" "${ARTIFACTORY_URL}/${REPO}/$(basename $f)"
done
```

### Option 2 — Download + Upload specific missing package

```bash
# Replace package name and version as needed
PACKAGE="strands-agents==1.14.0"
ARTIFACTORY_URL="https://your-artifactory.company.com/artifactory"
REPO="pypi-local"
AF_CREDS="username:api-key"

# Download
pip download -d /tmp/pkg "$PACKAGE"

# Upload
for f in /tmp/pkg/*.whl /tmp/pkg/*.tar.gz; do
  curl -u "$AF_CREDS" -T "$f" "${ARTIFACTORY_URL}/${REPO}/$(basename $f)"
done
```

### Option 3 — Install from vendor directory

```bash
pip install --no-index --find-links ./vendor/python \
  -e "lib/idp_common_pkg[all,dev,test]" \
  -e lib/idp_cli_pkg \
  -e lib/idp_sdk \
  -e lib/idp_mcp_connector_pkg
```

### Option 4 — Set pip.conf to use Artifactory

```bash
# Create pip config (macOS/Linux)
mkdir -p ~/.pip
cat > ~/.pip/pip.conf << 'EOF'
[global]
index-url = https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/
trusted-host = your-artifactory.company.com
EOF
```

---

## Need Help?

If you are unsure which packages are failing or need to generate a complete package list for your Artifactory admin:

```bash
# Generate complete resolved manifests for ALL components (recommended)
python3 scripts/generate_lockfiles.py

# Outputs a flat list of every package at every version:
#   deps/python/master/manifest.txt   — hand this to your Artifactory admin
#   deps/node/master/manifest.txt     — hand this to your Artifactory admin

# Then verify packages are accessible from Artifactory
UV_INDEX_URL="https://your-artifactory.company.com/artifactory/api/pypi/pypi-virtual/simple/" \
  python3 scripts/verify_python_packages.py
NODE_REGISTRY_URL="https://your-artifactory.company.com/artifactory/api/npm/npm-virtual/" \
  python3 scripts/verify_node_packages.py
```

This produces a flat, fully-resolved list of every package (including transitive dependencies) across all project components that can be handed to your Artifactory admin for bulk upload.

---

*Generated for the GenAI IDP Accelerator project — [GitHub Repository](https://github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws)*
