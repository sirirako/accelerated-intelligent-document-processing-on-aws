#!/usr/bin/env python3
"""
Build RVL-CDIP-NMP TestSet locally.

This script:
1. Randomly selects 500 packet definitions from the 5000 available manifests
2. Transforms them to simplified format
3. Creates combined packet PDFs by merging pages from source PDFs
4. Generates ground truth baseline files for classification and splitting evaluation
5. Optionally creates a zip file for upload to Test Studio

Usage:
    python scripts/build_rvl_cdip_nmp_testset.py \
        --assets-dir scratch/rvl-cdip-nmp-assets \
        --manifest-dir scratch/rvl-cdip-nmp-packet-metadata/test \
        --output-dir scratch/rvl-cdip-nmp-testset \
        --create-zip

Requirements:
    pip install pypdf
"""

import argparse
import json
import logging
import os
import random
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Any

from pypdf import PdfReader, PdfWriter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

NUM_PACKETS = 500
RANDOM_SEED = 42


def load_original_manifests(manifest_dir: Path) -> List[Dict[str, Any]]:
    manifests = []
    manifest_files = list(manifest_dir.glob('*.json'))
    logger.info(f"Found {len(manifest_files)} manifest files")
    for manifest_file in manifest_files:
        try:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifests.append(json.load(f))
        except Exception as e:
            logger.warning(f"Error loading {manifest_file}: {e}")
    logger.info(f"Successfully loaded {len(manifests)} manifests")
    return manifests


def transform_manifest(original: Dict[str, Any], packet_id: str) -> Dict[str, Any]:
    simplified = {
        "packet_id": packet_id,
        "original_doc_id": original["doc_id"],
        "total_pages": original["total_pages"],
        "subdocuments": []
    }
    for subdoc in original["subdocuments"]:
        first_page = subdoc["pages"][0]
        parts = first_page["image_path"].split('/')
        if len(parts) >= 3:
            source_pdf = f"{parts[1]}/{parts[2]}"
        else:
            continue
        source_pages = [page["local_doc_id_page_ordinal"] for page in subdoc["pages"]]
        simplified["subdocuments"].append({
            "doc_type_id": subdoc["doc_type_id"],
            "page_ordinals": subdoc["page_ordinals"],
            "source_pdf": source_pdf,
            "source_pages": source_pages
        })
    return simplified


def select_and_transform_manifests(manifests, num_packets=NUM_PACKETS, seed=RANDOM_SEED):
    random.seed(seed)
    selected = random.sample(manifests, min(num_packets, len(manifests)))
    logger.info(f"Selected {len(selected)} manifests")
    return [transform_manifest(m, f"packet_{i:04d}") for i, m in enumerate(selected, 1)]


def create_packet_pdf(manifest, assets_dir, output_path):
    try:
        writer = PdfWriter()
        for subdoc in manifest["subdocuments"]:
            source_pdf_path = assets_dir / subdoc["source_pdf"]
            if not source_pdf_path.exists():
                logger.error(f"Source PDF not found: {source_pdf_path}")
                return False
            reader = PdfReader(source_pdf_path)
            for page_num in subdoc["source_pages"]:
                page_idx = page_num - 1
                if page_idx < 0 or page_idx >= len(reader.pages):
                    logger.error(f"Invalid page {page_num} for {source_pdf_path}")
                    return False
                writer.add_page(reader.pages[page_idx])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            writer.write(f)
        return True
    except Exception as e:
        logger.error(f"Error creating packet PDF: {e}")
        return False


def create_baseline_files(manifest, baseline_dir):
    try:
        packet_baseline_dir = baseline_dir / f"{manifest['packet_id']}.pdf" / "sections"
        for section_idx, subdoc in enumerate(manifest["subdocuments"], 1):
            section_dir = packet_baseline_dir / str(section_idx)
            section_dir.mkdir(parents=True, exist_ok=True)
            page_indices = [p - 1 for p in subdoc["page_ordinals"]]
            result = {
                "document_class": {"type": subdoc["doc_type_id"]},
                "split_document": {"page_indices": page_indices},
                "inference_result": {}
            }
            with open(section_dir / "result.json", 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error creating baseline files: {e}")
        return False


def build_testset(manifests, assets_dir, output_dir):
    input_dir = output_dir / "input"
    baseline_dir = output_dir / "baseline"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    baseline_dir.mkdir(parents=True, exist_ok=True)
    stats = {"total": len(manifests), "success": 0, "failed": 0, "total_pages": 0, "total_sections": 0}
    for idx, manifest in enumerate(manifests, 1):
        packet_id = manifest["packet_id"]
        if idx % 50 == 0:
            logger.info(f"Processing packet {idx}/{len(manifests)}...")
        pdf_path = input_dir / f"{packet_id}.pdf"
        if not create_packet_pdf(manifest, assets_dir, pdf_path):
            stats["failed"] += 1
            continue
        if not create_baseline_files(manifest, baseline_dir):
            stats["failed"] += 1
            if pdf_path.exists():
                pdf_path.unlink()
            continue
        stats["success"] += 1
        stats["total_pages"] += manifest["total_pages"]
        stats["total_sections"] += len(manifest["subdocuments"])
    return stats


def create_zip_file(output_dir, zip_path=None):
    if zip_path is None:
        zip_path = output_dir.parent / f"{output_dir.name}.zip"
    logger.info(f"Creating zip file: {zip_path}")
    root_name = output_dir.name
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = Path(root_name) / file_path.relative_to(output_dir)
                zipf.write(file_path, arcname)
    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    logger.info(f"Created zip file: {zip_path} ({zip_size_mb:.1f} MB)")
    return zip_path


def save_manifest(manifests, output_path):
    manifest_data = {
        "version": "1.0",
        "description": "RVL-CDIP-NMP Packet TestSet - 500 packets for classification and splitting evaluation",
        "source": "huggingface:jordyvl/rvl_cdip_n_mp",
        "packet_count": len(manifests),
        "packets": manifests
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2)
    logger.info(f"Saved manifest to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Build RVL-CDIP-NMP TestSet locally")
    parser.add_argument("--assets-dir", type=Path, default=Path("scratch/rvl-cdip-nmp-assets"))
    parser.add_argument("--manifest-dir", type=Path, default=Path("scratch/rvl-cdip-nmp-packet-metadata/test"))
    parser.add_argument("--output-dir", type=Path, default=Path("scratch/rvl-cdip-nmp-testset"))
    parser.add_argument("--create-zip", action="store_true")
    parser.add_argument("--num-packets", type=int, default=NUM_PACKETS)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--save-manifest", type=Path, default=None)
    args = parser.parse_args()

    if not args.assets_dir.exists():
        logger.error(f"Assets directory not found: {args.assets_dir}")
        return 1
    if not args.manifest_dir.exists():
        logger.error(f"Manifest directory not found: {args.manifest_dir}")
        return 1

    logger.info("=" * 60)
    logger.info("RVL-CDIP-NMP TestSet Builder")
    logger.info("=" * 60)
    
    original_manifests = load_original_manifests(args.manifest_dir)
    if not original_manifests:
        logger.error("No manifests loaded")
        return 1
    
    simplified_manifests = select_and_transform_manifests(original_manifests, args.num_packets, args.seed)
    
    if args.save_manifest:
        save_manifest(simplified_manifests, args.save_manifest)
    else:
        save_manifest(simplified_manifests, args.output_dir / "packets.json")
    
    stats = build_testset(simplified_manifests, args.assets_dir, args.output_dir)
    
    logger.info("=" * 60)
    logger.info("Build Statistics:")
    logger.info(f"  Total packets: {stats['total']}")
    logger.info(f"  Successful: {stats['success']}")
    logger.info(f"  Failed: {stats['failed']}")
    logger.info(f"  Total pages: {stats['total_pages']}")
    logger.info(f"  Total sections: {stats['total_sections']}")
    if stats['success'] > 0:
        logger.info(f"  Avg pages/packet: {stats['total_pages']/stats['success']:.1f}")
        logger.info(f"  Avg sections/packet: {stats['total_sections']/stats['success']:.1f}")
    logger.info("=" * 60)
    
    if args.create_zip and stats['success'] > 0:
        create_zip_file(args.output_dir)
    
    logger.info("TestSet build complete!")
    return 0


if __name__ == "__main__":
    exit(main())
