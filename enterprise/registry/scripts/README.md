# Registry Cache Warming Scripts

Warm (pre-populate) a JFrog Artifactory remote repository cache with all IDP dependencies so that subsequent air-gapped builds can pull packages without internet access.

## Prerequisites

1. Generate dependency manifests:
   ```bash
   make dep-manifest
   # Produces: dist/manifests/python-packages.txt
   #           dist/manifests/node-packages.txt
   ```

2. Copy the manifest files to the target environment (VDI or EC2).

3. Configure registry credentials:
   - **Python**: `pip.conf` / `pip.ini` or pass `--index-url` / `-IndexUrl`
   - **Node**: `.npmrc` with registry URL and auth token

## Linux / EC2 (Recommended for Python)

EC2 is preferred for Python warming because Lambda runs on Linux — pip downloads the correct `manylinux` wheels natively.

```bash
# Python
./warm-python.sh python-packages.txt
./warm-python.sh python-packages.txt "https://user:token@jfrog.company.com/artifactory/api/pypi/pypi-remote/simple"

# Node
./warm-node.sh node-packages.txt
```

## Windows / PowerShell

Node packages are platform-agnostic so Windows works fine. For Python, use the `-Platform linux` flag to download Linux wheels.

```powershell
# Node
.\warm-node.ps1 -ManifestFile node-packages.txt

# Node with corporate proxy cert issue
.\warm-node.ps1 -ManifestFile node-packages.txt -SkipSslValidation

# Python (downloads Linux wheels for Lambda)
.\warm-python.ps1 -ManifestFile python-packages.txt -Platform linux

# Python with explicit JFrog URL
.\warm-python.ps1 -ManifestFile python-packages.txt -IndexUrl "https://user:token@jfrog.company.com/artifactory/api/pypi/pypi-remote/simple"
```

## Re-running After Failures

Failures are normal on the first run — JFrog may need time to:
- Fetch and index package metadata from upstream
- Complete Xray security scanning before serving packages

Simply re-run the script. Already-cached packages return instantly; previously failed ones often succeed after JFrog has refreshed its metadata cache.

Persistent failures after 2-3 runs indicate a real issue:
- **404 "no matching version"** — JFrog metadata cache is stale; ask admin to "Zap Caches" on the remote repo
- **401 Unauthorized** — token lacks read access to the remote repo (not just local repos)
- **SELF_SIGNED_CERT_IN_CHAIN** — corporate TLS inspection; use `-SkipSslValidation` or set `NODE_EXTRA_CA_CERTS`
- **Platform mismatch (Python on Windows)** — use `-Platform linux` or run on EC2

## Important Notes

- Use the **remote** repository URL for warming (the one that proxies upstream). The **virtual** repo is what builds consume afterward.
- Python warming should run on Linux (EC2) to get the correct wheel platform. Windows 32-bit pip cannot download `manylinux` wheels without the `-Platform linux` flag.
- Node warming works on any OS since npm packages are platform-agnostic.
