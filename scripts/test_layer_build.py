#!/usr/bin/env python3
"""
Standalone test script to debug Lambda layer building.
Tests only the layer building logic without running the full publish pipeline.
"""

import sys
import os
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from publish import IDPPublisher

def main():
    """Test layer building in isolation"""
    print("="*60)
    print("Testing Lambda Layer Building")
    print("="*60)
    
    # Create a publisher instance with verbose=True
    publisher = IDPPublisher(verbose=True)
    
    # Set minimal required attributes for layer building
    publisher.bucket = "test-bucket"
    publisher.prefix_and_version = "test-prefix/0.4.11"
    publisher.region = "us-west-2"
    
    # Mock S3 client to avoid actual uploads
    class MockS3Client:
        def head_object(self, **kwargs):
            from botocore.exceptions import ClientError
            error = ClientError(
                {"Error": {"Code": "404"}},
                "HeadObject"
            )
            raise error
        
        def upload_file(self, *args, **kwargs):
            print(f"  [MOCK] Would upload: {args[0]} -> s3://{args[1]}/{args[2]}")
    
    publisher.s3_client = MockS3Client()
    
    # Clean up old layers first
    print("\n🧹 Cleaning up old layer zips...")
    layers_dir = ".aws-sam/layers"
    if os.path.exists(layers_dir):
        for f in os.listdir(layers_dir):
            if f.endswith('.zip'):
                path = os.path.join(layers_dir, f)
                os.remove(path)
                print(f"  Deleted: {path}")
    
    print("\n📦 Building layers...")
    print("-"*60)
    
    try:
        # Call the layer building function
        layer_arns = publisher.build_all_lambda_layers()
        
        print("\n" + "="*60)
        print("✅ SUCCESS - Layers built!")
        print("="*60)
        
        for layer_name, info in layer_arns.items():
            print(f"\nLayer: {layer_name}")
            print(f"  Zip: {info['zip_name']}")
            print(f"  Path: {info['zip_path']}")
            print(f"  Hash: {info['hash']}")
            
            # Check actual file size
            if os.path.exists(info['zip_path']):
                size_mb = os.path.getsize(info['zip_path']) / 1024 / 1024
                print(f"  Size: {size_mb:.2f} MB")
                
                # Verify extras by unzipping and checking contents
                print(f"  Verifying contents...")
                import zipfile
                with zipfile.ZipFile(info['zip_path'], 'r') as zf:
                    files = zf.namelist()
                    
                    # Check for key packages that indicate extras are installed
                    has_requests = any('requests' in f for f in files)
                    has_pillow = any('PIL' in f or 'Pillow' in f for f in files)
                    has_pyarrow = any('pyarrow' in f for f in files)
                    has_strands = any('strands' in f for f in files)
                    
                    print(f"    - requests (docs_service): {has_requests}")
                    print(f"    - Pillow (image): {has_pillow}")
                    print(f"    - pyarrow (reporting): {has_pyarrow}")
                    print(f"    - strands-agents (agents): {has_strands}")
        
        print("\n" + "="*60)
        print("Test completed successfully!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()