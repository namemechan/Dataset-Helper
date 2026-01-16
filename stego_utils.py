from PIL import Image
import gzip
import struct
from typing import List, Dict, Optional

POSSIBLE_SIGS = {
    'stealth_pnginfo': {'mode': 'alpha', 'compressed': False},
    'stealth_pngcomp': {'mode': 'alpha', 'compressed': True},
    'stealth_rgbinfo': {'mode': 'rgb', 'compressed': False},
    'stealth_rgbcomp': {'mode': 'rgb', 'compressed': True},
}

def compress_data(data: str) -> bytes:
    """문자열을 gzip으로 압축합니다."""
    return gzip.compress(data.encode('utf-8'))

def decompress_data(compressed_data: bytes) -> str:
    """gzip으로 압축된 데이터를 문자열로 압축 해제합니다."""
    return gzip.decompress(compressed_data).decode('utf-8')

def _prepare_data_to_embed(data: str, signature: str) -> str:
    """임베딩을 위해 데이터를 바이너리 문자열로 준비합니다."""
    is_compressed = POSSIBLE_SIGS[signature]['compressed']
    payload = compress_data(data) if is_compressed else data.encode('utf-8')
    
    # Pad signature to 16 bytes
    sig_bytes = signature.encode('utf-8')
    sig_bytes = sig_bytes + b'\x00' * (16 - len(sig_bytes))
    
    binary_signature = ''.join(format(byte, '08b') for byte in sig_bytes)
    binary_payload = ''.join(format(byte, '08b') for byte in payload)
    binary_payload_len = format(len(binary_payload), '032b')
    
    return binary_signature + binary_payload_len + binary_payload

def embed_stealth_pnginfo(image: Image.Image, data: str, mode: str = 'alpha', compressed: bool = True) -> Image.Image:
    """LSB 스테가노그래피를 사용하여 PNG 이미지에 데이터를 숨깁니다."""
    if mode == 'alpha' and image.mode != 'RGBA':
        image = image.convert('RGBA')
    elif mode == 'rgb' and image.mode not in ['RGB', 'RGBA']:
        image = image.convert('RGB')

    signature = f"stealth_{'png' if mode == 'alpha' else 'rgb'}{'comp' if compressed else 'info'}"
    binary_data = _prepare_data_to_embed(data, signature)
    
    pixels = image.load()
    width, height = image.size
    data_index = 0
    
    for y in range(height):
        for x in range(width):
            if data_index >= len(binary_data):
                return image

            pixel = list(pixels[x, y])
            if mode == 'alpha':
                pixel[3] = (pixel[3] & ~1) | int(binary_data[data_index])
                data_index += 1
            else: # rgb
                for i in range(3):
                    if data_index < len(binary_data):
                        pixel[i] = (pixel[i] & ~1) | int(binary_data[data_index])
                        data_index += 1
            pixels[x, y] = tuple(pixel)
            
    return image

def extract_stealth_pnginfo(image: Image.Image) -> Optional[Dict]:
    """이미지에서 LSB 스테가노그래피로 숨겨진 데이터를 추출합니다."""
    if image.mode not in ['RGB', 'RGBA']:
        return None

    width, height = image.size
    pixels = image.load()

    def get_bits(mode: str):
        if mode == 'alpha':
            for y in range(height):
                for x in range(width):
                    yield pixels[x, y][3] & 1
        else: # rgb
            for y in range(height):
                for x in range(width):
                    pixel = pixels[x, y]
                    for i in range(3):
                        yield pixel[i] & 1

    def bits_to_bytes(bit_gen, n_bytes):
        res = bytearray()
        for _ in range(n_bytes):
            byte = 0
            for i in range(8):
                try:
                    bit = next(bit_gen)
                    byte = (byte << 1) | bit
                except StopIteration:
                    return res
            res.append(byte)
        return res

    # 1. Try Alpha first
    if image.mode == 'RGBA':
        bit_gen = get_bits('alpha')
        sig_bytes = bits_to_bytes(bit_gen, 16)
        try:
            decoded_sig = sig_bytes.decode('utf-8', errors='ignore').strip('\x00')
            if decoded_sig in POSSIBLE_SIGS and POSSIBLE_SIGS[decoded_sig]['mode'] == 'alpha':
                return _finish_extraction(bit_gen, decoded_sig)
        except Exception:
            pass

    # 2. Try RGB
    bit_gen = get_bits('rgb')
    sig_bytes = bits_to_bytes(bit_gen, 16)
    try:
        decoded_sig = sig_bytes.decode('utf-8', errors='ignore').strip('\x00')
        if decoded_sig in POSSIBLE_SIGS and POSSIBLE_SIGS[decoded_sig]['mode'] == 'rgb':
            return _finish_extraction(bit_gen, decoded_sig)
    except Exception:
        pass

    return None

def _finish_extraction(bit_gen, signature: str) -> Dict:
    """시그니처 이후의 길이와 데이터를 추출합니다."""
    # Read 32 bits for length
    len_bits = 0
    for _ in range(32):
        try:
            len_bits = (len_bits << 1) | next(bit_gen)
        except StopIteration:
            break
    
    # Extract data bits
    data_bits = []
    for _ in range(len_bits):
        try:
            data_bits.append(next(bit_gen))
        except StopIteration:
            break
    
    # Convert bits to bytes
    data_bytes = bytearray()
    for i in range(0, len(data_bits), 8):
        byte = 0
        for j in range(8):
            if i + j < len(data_bits):
                byte = (byte << 1) | data_bits[i+j]
        data_bytes.append(byte)
    
    # Decompress if needed
    is_compressed = POSSIBLE_SIGS[signature]['compressed']
    try:
        if is_compressed:
            data_str = decompress_data(data_bytes)
        else:
            data_str = data_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        data_str = f"Error decoding data: {e}"

    return {
        'signature': signature,
        'mode': POSSIBLE_SIGS[signature]['mode'],
        'compressed': is_compressed,
        'data': data_str
    }


def detect_steganography_methods(image: Image.Image) -> List[str]:
    """이미지에 사용된 스테가노그래피 방식을 감지합니다."""
    methods = []
    # This is a simplified detection. A real implementation would be more thorough.
    if extract_stealth_pnginfo(image) is not None:
        methods.append("stealth_pnginfo")
    # Add other detection methods here
    return methods

# Placeholders for other functions from the guide
def extract_custom_steganography(image: Image.Image, method: str) -> bytes:
    print(f"Function 'extract_custom_steganography' for method {method} is not implemented yet.")
    return b''

def embed_custom_steganography(image: Image.Image, data: bytes, method: str) -> Image.Image:
    print(f"Function 'embed_custom_steganography' for method {method} is not implemented yet.")
    return image

def verify_steganography_integrity(image: Image.Image, expected_data: str) -> bool:
    print("Function 'verify_steganography_integrity' is not implemented yet.")
    return False
