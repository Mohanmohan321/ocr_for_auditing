"""
Image preprocessing: grayscale, contrast enhancement, thresholding.
Returns both original and processed versions so OCR can pick the better one.
Preserves Tamil characters by using gentle enhancement.
"""
import logging
import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


def preprocess_image(image_path: str) -> tuple[np.ndarray, np.ndarray, Image.Image]:
    """
    Read image, apply preprocessing, return original + processed + PIL.

    Returns:
        (original_rgb, processed_rgb, pil_original)
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    log.info("Preprocessing: %s (%dx%d)", image_path, img.shape[1], img.shape[0])

    # Upscale small images for better OCR
    h, w = img.shape[:2]
    if w < 1000:
        scale = 1000 / w
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        log.info("Upscaled %.1fx to %dx%d", scale, img.shape[1], img.shape[0])

    # Original RGB
    original_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_original = Image.fromarray(original_rgb)

    # Processed: gentle enhancement
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=6, templateWindowSize=7, searchWindowSize=21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    processed_rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)

    log.info("Preprocessing complete")
    return original_rgb, processed_rgb, pil_original
