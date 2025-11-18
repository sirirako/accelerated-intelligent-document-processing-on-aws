# Deliverable Security Review (DSR)

## Overview

DSR (Deliverable Security Review) is a security scanning tool used to identify and remediate security issues in code repositories before delivery.

## Step-by-Step Instructions

### Step 1: Create DSR Directory
Create `.dsr` folder under project root:
```bash
mkdir .dsr
```

### Step 2: Download DSR Tool
Download latest DSR version from [releases](https://drive.corp.amazon.com/folders/DSR_Tool/Releases/Latest) based on your OS

### Step 3: Extract Package
Extract the package to the `.dsr` folder:
```bash
cd .dsr
tar -xzf dsr-cli-*.tar.gz
```

### Step 4: Update DSR Tool (Optional)
Update to latest version if you have an existing installation:
```bash
cd .dsr
./dsr update
```

### Step 5: Configure DSR
Configure DSR tool:
```bash
cd .dsr
./dsr config
```

### Step 5: Authenticate
Follow instructions to authenticate using mwint (install mwint if missing):
```bash
# Follow authentication prompts during config
```

### Step 6: Load Existing Issues (Optional)
Load existing `issues.json` from shared team archive before running DSR:
```bash
# Download issues.json from shared location
# Example: https://drive.corp.amazon.com/documents/tanimath@/genaiic-idp-accelerator/issues.json
cp /path/to/shared/issues.json .dsr/issues.json
```

### Step 7: Run DSR Scan
Run DSR tool:
```bash
cd .dsr
./dsr
```
- Confirm project root path
- Select license type (default: AWS)
- DSR will perform security scan and save results in `issues.json`

After DSR scan completes, you'll see a summary like:

```
🚀 DSR complete!

🔍 DSR Status

License: AWS
Last Scan: less than a minute ago

Open: 49
Resolved: 4
Suppressed: 108

Progress: 70% complete
49 issues need attention
```

### Step 8: Fix Issues (Optional)
Fix issues interactively:
```bash
cd .dsr
./dsr fix
```
Options available:
- Suppress issue
- Apply automatic fix
- Skip/escape

**Important**: Commit your work to git before running `dsr fix` as AI-suggested fixes may introduce unintended changes.

### Step 9: Save Results to Shared Archive for Future Updated Scan
Save updated `issues.json` to shared team archive so team members can use it for future DSR scans:
```bash
# Upload issues.json to shared location for team access
# This preserves issue status and enables incremental progress tracking
# Example: https://drive.corp.amazon.com/documents/tanimath@/genaiic-idp-accelerator/issues.json
cp .dsr/issues.json /path/to/shared/archive/issues.json
```

### Step 10: Commit Fixes and Create MR
Review DSR changes before committing and create a merge request:
```bash
# Review all changes made by DSR tool
git diff
git add .
git commit -m "DSR: Fix security issues"
git push origin feature/dsr-fixes
# Create merge request through your Git platform
```

## References

- [DSR Tool Wiki](https://w.amazon.com/bin/view/DSRTool)
- [DSR Releases](https://drive.corp.amazon.com/folders/DSR_Tool/Releases/Latest)
