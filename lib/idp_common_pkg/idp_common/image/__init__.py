# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from PIL import Image
import io
import logging
from typing import Tuple, Optional, Dict, Any, Union
from ..s3 import get_binary_content
from ..utils import parse_s3_uri

logger = logging.getLogger(__name__)

def resize_image(image_data: bytes, 
                target_width: int = 951, 
                target_height: int = 1268) -> bytes:
    """
    Resize an image to fit within target dimensions while preserving aspect ratio.
    No padding, no distortion - pure proportional scaling.
    
    Args:
        image_data: Raw image bytes
        target_width: Target width in pixels
        target_height: Target height in pixels
        
    Returns:
        Resized image as JPEG bytes
    """
    image = Image.open(io.BytesIO(image_data))
    current_width, current_height = image.size
    
    # Calculate scaling factor to fit within bounds while preserving aspect ratio
    width_ratio = target_width / current_width
    height_ratio = target_height / current_height
    scale_factor = min(width_ratio, height_ratio)  # Fit within bounds
    
    # Only resize if we're making it smaller
    if scale_factor < 1.0:
        new_width = int(current_width * scale_factor)
        new_height = int(current_height * scale_factor)
        logger.info(f"Resizing image from {current_width}x{current_height} to {new_width}x{new_height} (scale: {scale_factor:.3f})")
        image = image.resize((new_width, new_height), Image.LANCZOS)
    else:
        logger.debug(f"Image {current_width}x{current_height} already fits within {target_width}x{target_height}, no resizing needed")
    
    # Convert to JPEG bytes
    img_byte_array = io.BytesIO()
    image.save(img_byte_array, format="JPEG")
    return img_byte_array.getvalue()

def prepare_image(image_source: Union[str, bytes],
                 target_width: int = 951, 
                 target_height: int = 1268) -> bytes:
    """
    Prepare an image for model input from either S3 URI or raw bytes
    
    Args:
        image_source: Either an S3 URI (s3://bucket/key) or raw image bytes
        target_width: Target width in pixels
        target_height: Target height in pixels
        
    Returns:
        Processed image as JPEG bytes ready for model input
    """
    # Get the image data
    if isinstance(image_source, str) and image_source.startswith('s3://'):
        image_data = get_binary_content(image_source)
    elif isinstance(image_source, bytes):
        image_data = image_source
    else:
        raise ValueError(f"Invalid image source: {type(image_source)}. Must be S3 URI or bytes.")
        
    # Resize and process
    return resize_image(image_data, target_width, target_height)

def prepare_bedrock_image_attachment(image_data: bytes) -> Dict[str, Any]:
    """
    Format an image for Bedrock API attachment
    
    Args:
        image_data: Raw image bytes
        
    Returns:
        Formatted image attachment for Bedrock API
    """
    # Detect image format from image data
    image = Image.open(io.BytesIO(image_data))
    format_mapping = {
        'JPEG': 'jpeg',
        'PNG': 'png', 
        'GIF': 'gif',
        'WEBP': 'webp'
    }
    detected_format = format_mapping.get(image.format)
    if not detected_format:
        raise ValueError(f"Unsupported image format: {image.format}")
    logger.info(f"Detected image format: {detected_format}")
    return {
        "image": {
            "format": detected_format,
            "source": {"bytes": image_data}
        }
    }
