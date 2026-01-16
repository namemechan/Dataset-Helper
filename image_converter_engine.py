from PIL import Image
import multiprocessing
import time
from typing import List, Dict, Any, Callable
import os
import piexif
import functools

# Assuming other modules are in the same directory
import image_file_utils as file_manager
import metadata_utils as metadata_handler
from app_logger import logger

def _convert_image_worker(args):
    """멀티프로세싱을 위한 워커 함수"""
    input_path, settings = args
    return convert_image(input_path, settings)

def orient_image(image: Image.Image) -> Image.Image:
    """EXIF 정보에 따라 이미지 방향을 바로잡습니다."""
    exif_bytes = image.info.get('exif')
    if not exif_bytes:
        return image

    try:
        exif_dict = piexif.load(exif_bytes)
        if piexif.ImageIFD.Orientation in exif_dict['0th']:
            orientation = exif_dict['0th'][piexif.ImageIFD.Orientation]
            if orientation == 2:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                image = image.rotate(180)
            elif orientation == 4:
                image = image.rotate(180).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 5:
                image = image.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 6:
                image = image.rotate(-90, expand=True)
            elif orientation == 7:
                image = image.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
            
            # Orientation 태그를 1(정상)로 리셋하여 재회전 방지
            exif_dict['0th'][piexif.ImageIFD.Orientation] = 1
            
            # CFAPattern (41729) 태그가 있으면 삭제 (타입 오류 방지)
            if 'Exif' in exif_dict and 41729 in exif_dict['Exif']:
                del exif_dict['Exif'][41729]

            image.info['exif'] = piexif.dump(exif_dict)
            
    except Exception as e:
        logger.warning(f"EXIF 방향 처리 중 오류 발생: {e}", module="converter_engine")
    return image

def apply_quality_settings(image: Image.Image, format: str, quality: int, optimize: bool) -> Dict:
    """이미지 저장 시 품질 및 최적화 설정을 적용합니다."""
    save_options = {'quality': quality}
    if format.upper() in ['PNG', 'WEBP']:
        save_options['optimize'] = optimize
    if format.upper() == 'WEBP':
        save_options['lossless'] = quality == 100
    return save_options

def apply_resize_settings(image: Image.Image, scale_factor: float) -> Image.Image:
    """이미지 해상도를 조절합니다."""
    if scale_factor == 1.0:
        return image
    new_size = (int(image.width * scale_factor), int(image.height * scale_factor))
    return image.resize(new_size, Image.Resampling.LANCZOS)

def convert_image(input_path: str, settings: dict) -> dict:
    """단일 이미지를 변환하고 결과를 반환합니다."""
    start_time = time.time()
    output_settings = settings['output_settings']
    conversion_settings = settings['conversion_settings']
    metadata_settings = settings['metadata_settings']

    output_path = file_manager.generate_output_filename(
        input_path, 
        output_settings['target_folder'], 
        output_settings['target_format'],
        output_settings['naming_pattern']
    )

    final_output_path = file_manager.handle_file_conflicts(output_path, output_settings['overwrite_policy'])

    if final_output_path is None:
        return {'status': 'skipped', 'path': input_path, 'reason': 'File exists and overwrite policy is skip'}

    try:
        logger.log_conversion_start(input_path, output_settings['target_format'])
        
        # Metadata extraction
        source_metadata = None
        if metadata_settings['preserve_enabled']:
            source_metadata = metadata_handler.extract_all_metadata(input_path)
            if source_metadata:
                logger.log_metadata_detection([k for k, v in source_metadata.items() if v], input_path)

        with Image.open(input_path) as img:
            img = orient_image(img)
            # Resize
            if conversion_settings['resize_enabled']:
                img = apply_resize_settings(img, conversion_settings['resize_scale'])

            # Prepare save options
            save_opts = {}
            if conversion_settings['quality_enabled']:
                save_opts = apply_quality_settings(img, output_settings['target_format'], conversion_settings['quality_value'], conversion_settings.get('optimize', False))

            # Preserve metadata
            if source_metadata:
                meta_opts = metadata_handler.prepare_save_options(source_metadata, output_settings['target_format'], metadata_settings)
                save_opts.update(meta_opts)

            # Convert and save
            # Ensure target directory exists
            os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
            img.save(final_output_path, format=output_settings['target_format'].upper(), **save_opts)

        processing_time = time.time() - start_time
        logger.info(f"변환 완료: {final_output_path} ({processing_time:.2f}초)", module="converter_engine")
        return {'status': 'success', 'input': input_path, 'output': final_output_path, 'time': processing_time}

    except Exception as e:
        logger.error(f"변환 실패: {input_path} - {e}", module="converter_engine", exc_info=True)
        return {'status': 'error', 'path': input_path, 'reason': str(e)}

def batch_convert_images(file_list: List[str], settings: Dict, progress_callback: Callable = None, control_callbacks: Dict[str, Callable] = None) -> Dict:
    """이미지 파일 목록을 배치 처리합니다."""
    results = {'success': [], 'error': [], 'skipped': []}
    total_files = len(file_list)
    
    use_multiprocessing = settings.get('processing_settings', {}).get('multiprocessing_enabled', False)
    max_workers = settings.get('processing_settings', {}).get('max_workers', 1)

    logger.info(f'{total_files}개 파일에 대한 일괄 변환을 시작합니다. (멀티코어: {use_multiprocessing})', module="converter_engine")

    if use_multiprocessing and max_workers > 1:
        with multiprocessing.Pool(processes=max_workers) as pool:
            # imap을 사용하여 결과가 나오는 대로 처리
            worker_args = [(f, settings) for f in file_list]
            for i, result in enumerate(pool.imap(_convert_image_worker, worker_args)):
                # Check Stop Signal
                if control_callbacks and control_callbacks.get('check_stop') and control_callbacks['check_stop']():
                    logger.info("사용자 요청에 의해 변환이 중지되었습니다. (워커 종료 중...)", module="converter_engine")
                    pool.terminate()
                    break

                # Check Pause Signal
                if control_callbacks and control_callbacks.get('check_pause'):
                    while control_callbacks['check_pause']():
                        time.sleep(0.5)
                        if control_callbacks.get('check_stop') and control_callbacks['check_stop']():
                            pool.terminate()
                            break
                    if control_callbacks.get('check_stop') and control_callbacks['check_stop']():
                        break

                results[result['status']].append(result)
                if progress_callback:
                    progress_callback(i + 1, total_files, result.get('input', file_list[i]))
    else:
        # 기존 순차 처리 로직
        for i, file_path in enumerate(file_list):
            # Check Stop Signal
            if control_callbacks and control_callbacks.get('check_stop') and control_callbacks['check_stop']():
                logger.info("사용자 요청에 의해 변환이 중지되었습니다.", module="converter_engine")
                break

            # Check Pause Signal
            if control_callbacks and control_callbacks.get('check_pause'):
                while control_callbacks['check_pause']():
                    time.sleep(0.5)
                    if control_callbacks.get('check_stop') and control_callbacks['check_stop']():
                        logger.info("사용자 요청에 의해 변환이 중지되었습니다 (일시정지 중).", module="converter_engine")
                        break
                if control_callbacks.get('check_stop') and control_callbacks['check_stop']():
                    break

            result = convert_image(file_path, settings)
            results[result['status']].append(result)
            if progress_callback:
                progress_callback(i + 1, total_files, file_path)
            
    logger.info("일괄 변환 완료.", module="converter_engine")
    return results

# Placeholders for more advanced functions
def estimate_processing_time(file_list: list, settings: dict) -> float:
    print("Function 'estimate_processing_time' is not implemented yet.")
    # Simple estimation: 0.5 seconds per file
    return len(file_list) * 0.5

def validate_conversion_settings(settings: dict) -> tuple:
    print("Function 'validate_conversion_settings' is not implemented yet.")
    return (True, [])