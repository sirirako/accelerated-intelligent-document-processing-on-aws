# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from PIL import Image, ImageFilter, ImageChops, ImageOps
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

def apply_adaptive_binarization(image_data: bytes) -> bytes:
    """
    Apply adaptive binarization using Pillow-only implementation.
    
    This preprocessing step can significantly improve OCR accuracy on documents with:
    - Uneven lighting or shadows
    - Low contrast text
    - Background noise or gradients
    
    Implements adaptive mean thresholding similar to OpenCV's ADAPTIVE_THRESH_MEAN_C
    with block_size=15 and C=10.
    
    Args:
        image_data: Raw image bytes
        
    Returns:
        Processed image as JPEG bytes with adaptive binarization applied
    """
    try:
        # Convert bytes to PIL Image
        pil_image = Image.open(io.BytesIO(image_data))
        
        # Convert to grayscale if not already
        if pil_image.mode != 'L':
            pil_image = pil_image.convert('L')
        
        # Apply adaptive thresholding using Pillow operations
        block_size = 15
        C = 10
        
        # Create a blurred version for local mean calculation
        # Use BoxBlur with radius = block_size // 2 to approximate local mean
        radius = block_size // 2
        blurred = pil_image.filter(ImageFilter.BoxBlur(radius))
        
        # Apply adaptive threshold: original > (blurred - C) ? 255 : 0
        # Load pixel data for efficient access
        width, height = pil_image.size
        original_pixels = list(pil_image.getdata())
        blurred_pixels = list(blurred.getdata())
        
        binary_pixels = []
        # Apply thresholding pixel by pixel
        for orig, blur in zip(original_pixels, blurred_pixels):
            threshold = blur - C
            binary_pixels.append(255 if orig > threshold else 0)
        
        # Create binary image
        binary_image = Image.new('L', (width, height))
        binary_image.putdata(binary_pixels)
        
        # Convert to JPEG bytes
        img_byte_array = io.BytesIO()
        binary_image.save(img_byte_array, format="JPEG")
        
        logger.debug("Applied adaptive binarization preprocessing (Pillow implementation)")
        return img_byte_array.getvalue()
        
    except Exception as e:
        logger.error(f"Error applying adaptive binarization: {str(e)}")
        # Return original image if preprocessing fails
        logger.warning("Falling back to original image due to preprocessing error")
        return image_data


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
