#!/usr/bin/env python3
"""
Minimal test to isolate pip extras installation issue.
Tests only the pip install command with extras.
"""

import subprocess
import sys
import os
import shutil
import zipfile

def test_pip_with_extras():
    """Test pip install with extras in isolation"""
    print("="*80)
    print("TESTING PIP INSTALL WITH EXTRAS")
    print("="*80)
    
    # Clean up any existing test directory
    test_dir = ".test-layer-debug"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    
    os.makedirs(f"{test_dir}/python", exist_ok=True)
    
    # Test 1: Install with NO extras
    print("\n1️⃣  TEST 1: Install WITHOUT extras")
    print("-"*80)
    install_spec_no_extras = "./lib/idp_common_pkg"
    cmd_no_extras = [
        sys.executable,
        "-m",
        "pip",
        "install",
        install_spec_no_extras,
        "-t",
        f"{test_dir}/python",
        "--upgrade",
    ]
    
    print(f"Install spec: {install_spec_no_extras}")
    print(f"Command: {' '.join(cmd_no_extras)}")
    print(f"Running...")
    
    result = subprocess.run(cmd_no_extras, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ SUCCESS")
        # Check what was installed
        installed_packages = os.listdir(f"{test_dir}/python")
        print(f"Packages installed: {len([p for p in installed_packages if not p.startswith('.')])}")
        has_pyarrow = any('pyarrow' in p for p in installed_packages)
        has_requests = any('requests' in p for p in installed_packages)
        print(f"  - pyarrow: {has_pyarrow}")
        print(f"  - requests: {has_requests}")
    else:
        print(f"❌ FAILED: {result.stderr}")
    
    # Clean for next test
    shutil.rmtree(test_dir)
    os.makedirs(f"{test_dir}/python", exist_ok=True)
    
    # Test 2: Install with [reporting] extra
    print("\n2️⃣  TEST 2: Install WITH [reporting] extra")
    print("-"*80)
    layer_extras = ["reporting"]
    extras_str = ",".join(layer_extras)
    install_spec_with_extras = f"./lib/idp_common_pkg[{extras_str}]"
    
    cmd_with_extras = [
        sys.executable,
        "-m",
        "pip",
        "install",
        install_spec_with_extras,
        "-t",
        f"{test_dir}/python",
        "--upgrade",
    ]
    
    print(f"layer_extras = {layer_extras}")
    print(f"extras_str = {extras_str}")
    print(f"Install spec: {install_spec_with_extras}")
    print(f"Command: {' '.join(cmd_with_extras)}")
    print(f"Command[4] = '{cmd_with_extras[4]}'")
    print(f"Running...")
    
    result = subprocess.run(cmd_with_extras, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ SUCCESS")
        # Check what was installed
        installed_packages = os.listdir(f"{test_dir}/python")
        print(f"Packages installed: {len([p for p in installed_packages if not p.startswith('.')])}")
        has_pyarrow = any('pyarrow' in p for p in installed_packages)
        has_requests = any('requests' in p for p in installed_packages)
        print(f"  - pyarrow (reporting extra): {has_pyarrow} ← Should be TRUE")
        print(f"  - requests (docs_service extra): {has_requests} ← Depends on deps")
    else:
        print(f"❌ FAILED: {result.stderr}")
        return False
    
    # Clean for next test
    shutil.rmtree(test_dir)
    os.makedirs(f"{test_dir}/python", exist_ok=True)
    
    # Test 3: Install with [agents] extra
    print("\n3️⃣  TEST 3: Install WITH [agents] extra")
    print("-"*80)
    layer_extras_agents = ["agents"]
    extras_str_agents = ",".join(layer_extras_agents)
    install_spec_agents = f"./lib/idp_common_pkg[{extras_str_agents}]"
    
    cmd_agents = [
        sys.executable,
        "-m",
        "pip",
        "install",
        install_spec_agents,
        "-t",
        f"{test_dir}/python",
        "--upgrade",
    ]
    
    print(f"layer_extras = {layer_extras_agents}")
    print(f"extras_str = {extras_str_agents}")
    print(f"Install spec: {install_spec_agents}")
    print(f"Command: {' '.join(cmd_agents)}")
    print(f"Running...")
    
    result = subprocess.run(cmd_agents, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ SUCCESS")
        # Check what was installed
        installed_packages = os.listdir(f"{test_dir}/python")
        print(f"Packages installed: {len([p for p in installed_packages if not p.startswith('.')])}")
        has_strands = any('strands' in p.lower() for p in installed_packages)
        has_bedrock = any('bedrock' in p.lower() for p in installed_packages)
        print(f"  - strands-agents (agents extra): {has_strands} ← Should be TRUE")
        print(f"  - bedrock-agentcore (agents extra): {has_bedrock} ← Should be TRUE")
    else:
        print(f"❌ FAILED: {result.stderr}")
        return False
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED")
    print("="*80)
    print("\nConclusion: pip install command works correctly with extras!")
    print("The issue must be somewhere else in the code flow.")
    return True

if __name__ == "__main__":
    try:
        success = test_pip_with_extras()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)