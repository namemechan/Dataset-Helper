from PIL import Image
from PIL.PngImagePlugin import PngInfo
import piexif
import json
from typing import Dict, Any, Optional

# Assuming steganography_handler.py is in the same directory
import stego_utils as steganography_handler

METADATA_STRUCTURE = {
    'source_info': {},
    'standard_metadata': {},
    'steganography_data': {},
    'ai_generation_info': {},
    'preservation_status': {}
}

def extract_exif_data(image: Image.Image) -> Optional[Dict]:
    """Pillow 이미 객체에서 EXIF 데이터를 추출합니다."""
    try:
        exif_data = image.info.get('exif')
        if exif_data:
            return piexif.load(exif_data)
    except Exception:
        return None
    return None

def extract_png_text_chunks(image: Image.Image) -> Dict:
    """Pillow 이미지 객체에서 PNG 텍스트 청크를 추출합니다."""
    if not hasattr(image, 'text') or not image.text:
        return {}
    return image.text

def extract_all_metadata(image_path: str) -> Dict:
    """이미지 파일에서 가능한 모든 메타데이터를 추출합니다."""
    metadata = METADATA_STRUCTURE.copy()
    try:
        with Image.open(image_path) as img:
            metadata['source_info'] = {
                'file_path': image_path,
                'format': img.format,
                'dimensions': img.size,
                'color_mode': img.mode
            }

            standard_meta = {}
            standard_meta['exif'] = extract_exif_data(img)
            standard_meta['png_text'] = extract_png_text_chunks(img)
            # Placeholders for other metadata types
            standard_meta['xmp'] = "<XMP data not implemented>"
            standard_meta['iptc'] = {}
            standard_meta['jpeg_comment'] = img.info.get('comment', '')
            metadata['standard_metadata'] = standard_meta

            # Steganography extraction
            metadata['steganography_data'] = steganography_handler.extract_stealth_pnginfo(img)

            # AI Info Detection
            raw_data, detected_tool = detect_ai_generator_type(metadata)
            metadata['ai_generation_info'] = {
                'detected_tool': detected_tool,
                'raw_data': raw_data,
                'parameters': parse_ai_parameters(raw_data, detected_tool)
            }

    except IOError as e:
        print(f"Error opening or reading image file: {e}")
        return None
    
    return metadata

def detect_ai_generator_type(metadata: Dict) -> (Optional[str], Optional[str]):
    """메타데이터를 기반으로 AI 생성 도구를 감지합니다."""
    # This is a simplified detection logic
    png_text = metadata.get('standard_metadata', {}).get('png_text', {})
    if 'parameters' in png_text: # A1111/WebUI style
        return png_text['parameters'], 'webui'
    if 'prompt' in png_text: # ComfyUI style
        return png_text['prompt'], 'comfyui'
    
    stealth_info = metadata.get('steganography_data')
    if stealth_info and stealth_info.get('data') and stealth_info['data'] != "<data extraction not fully implemented>":
        return stealth_info['data'], 'stealth_pnginfo'

    return None, 'unknown'

def parse_ai_parameters(raw_data: str, generator_type: str) -> Dict:
    """AI 생성 파라미터를 파싱합니다."""
    if not raw_data:
        return {}
    # Placeholder - in a real scenario, this would have complex parsing logic
    return {'raw': raw_data}

def prepare_save_options(source_metadata: dict, target_format: str, settings: dict) -> dict:
    """대상 이미지 저장에 필요한 메타데이터 옵션을 준비합니다."""
    save_opts = {}
    if not source_metadata:
        return save_opts
    
    target_format = target_format.upper().replace('JPEG', 'JPG') # normalize
    standard_meta = source_metadata.get('standard_metadata', {})
    
    # 1. EXIF 보존 (JPEG, WEBP, PNG 지원)
    exif_data = standard_meta.get('exif')
    if exif_data and target_format in ['JPG', 'JPEG', 'WEBP', 'PNG']:
        try:
            save_opts['exif'] = piexif.dump(exif_data)
        except Exception:
            pass 

    # 2. PNG 텍스트 청크 보존 (PNG 전용)
    if target_format == 'PNG':
        pnginfo = PngInfo()
        png_text = standard_meta.get('png_text', {})
        for key, value in png_text.items():
            pnginfo.add_text(key, str(value))
        
        # 만약 AI 정보가 감지되었으나 png_text에 없다면 (예: 스텔스 PNG), 추가 가능
        ai_info = source_metadata.get('ai_generation_info', {})
        if ai_info.get('detected_tool') == 'stealth_pnginfo' and 'parameters' not in png_text:
            pnginfo.add_text('parameters', ai_info.get('raw_data', ''))
            
        save_opts['pnginfo'] = pnginfo

    return save_opts

def preserve_metadata_to_target(source_metadata: dict, target_image: Image.Image, target_format: str, settings: dict) -> bool:
    """(Deprecated) 대신 prepare_save_options를 사용하세요."""
    return True

def calculate_preservation_compatibility(source_format: str, target_format: str) -> dict:
    """소스와 대상 포맷 간의 메타데이터 보존 호환성을 계산합니다."""
    # Placeholder
    return {'estimated_loss': 0.5}

def merge_metadata_sources(metadata_dict: dict) -> dict:
    """다양한 소스에서 추출된 메타데이터를 병합합니다."""
    return metadata_dict
