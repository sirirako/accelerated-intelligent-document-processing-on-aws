# Development Environment Setup Guide on Windows using WSL(Windows Subsystem for Linux)
# Introduction  
This guide establishes a WSL-based development environment on Windows, specifically designed for the GenAI IDP accelerator.

Purpose: Provides a Linux development environment directly on Windows without virtualization overhead, combining native Windows tools with a complete Linux 
development stack. This approach eliminates cross-platform compatibility issues while maintaining familiar Windows workflows.

When to use this guide:
• You're developing on Windows and need Linux compatibility
• You want to avoid Docker Desktop or VM overhead
• You need consistent behavior with the project's Linux-based AWS infrastructure
• You prefer integrated Windows/Linux development workflows

What you'll achieve:
A seamless development setup where you can use Windows tools (VS Code, browsers, file explorers) while running the GenAI IDP accelerator in a native Linux 
environment, ensuring compatibility with AWS Lambda's Linux runtime and deployment targets.
# Official Microsoft WSL Installation Guide:
https://docs.microsoft.com/en-us/windows/wsl/install  

# Step 1: Enable WSL on Windows
### 1.1 Enable WSL Feature for example Ubuntu
1. Open PowerShell as Administrator
2. Run the installation command:
```
wsl --install -d Ubuntu 
```  
3. Restart your computer when prompted
4. Complete Ubuntu setup with username/password
### 1.2 Verify Installation
```
wsl --version
```
# Step 2: Install Development Tools in WSL
Open "Ubuntu" in local machine
### 2.1 Update System Packages
```
sudo apt update && sudo apt upgrade -y
```  
### 2.2 Install Essential Tools
### Install Git 
```
sudo apt install git -y
```
# Step 3: Clone and Setup Project
### Clone Repository
```
git clone https://github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws
```
### Go to directory  
```
cd accelerated-intelligent-document-processing-on-aws
```
### Install Python and pip 
```
sudo apt install python3 python3-pip -y
```
### Verify Python version
```
python3 --version
```
### Create and setup Python Environment
```
python3 -m venv venv
source venv/bin/activate
```
### Build tools and make
```
sudo apt install build-essential make -y
```
### Install Node.js for UI development
```
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
```
```
sudo apt-get install -y nodejs
```
### AWS CLI
#### Downloads the latest AWS CLI zip file for Linux x86_64 architecture
```
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscli.zip"
```
#### Unzip aws-cli-linux-x86_64.zip -d 
```
unzip awscli.zip
```
#### Installation
```
sudo ./aws/install
```
#### Remove Zip file
```
rm -rf aws awscli.zip
```
### Verify AWS CLI installation
```
aws --version
```
### AWS SAM CLI
#### Downloads the latest AWS SAM CLI zip file for Linux x86_64 architecture from GitHub releases
```
wget https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip
```
#### Unzip aws-sam-cli-linux-x86_64.zip -d sam-installation
```
unzip aws-sam-cli-linux-x86_64.zip -d sam-installation
```
#### Installation
```
sudo ./sam-installation/install
```
#### Remove Zip file
```
rm -rf sam-installation aws-sam-cli-linux-x86_64.zip
```
### Verify SAM Installation
```
sam --version
```
### Install package building tools
```
pip install setuptools wheel
```
### Install all dependencies required for python
```
pip install boto3 rich PyYAML botocore
```
### Install development tools
```
pip install ruff pytest
```
### Install IDP common package in development mode
```
pip install -e lib/idp_common_pkg/
```
# Step 4: AWS Configure
### Refer this link for AWS configure
https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html  

# Step 5: Run Publish Script 
## Using publish.py (Recommended)

### Test publish script help
```
python3 publish.py --help
```
### Test build using publish.py
```
python3 publish.py bucket_name build-test us-east-1
```
### Troubleshooting Build Issues
If the build fails, use the `--verbose` flag to see detailed error messages:
```
python3 publish.py bucket_name build-test us-east-1 --verbose
```
The verbose flag will show:
- Exact SAM build commands being executed
- Complete error output from failed builds
- Python version compatibility issues
- Missing dependencies or configuration problems

## Using publish.sh (Legacy)
### Test publish script help
```
./publish.sh --help
```
### Test build using publish.sh
```
./publish.sh bucket_name build-test us-east-1
```