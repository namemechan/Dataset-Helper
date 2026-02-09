# Dataset Helper - 개발자 가이드 (Developer Guide)

본 문서는 **Dataset Helper** 프로젝트의 아키텍처, 파일 구조, 모듈 간의 연결 관계를 설명하여 개발 및 유지보수를 돕기 위해 작성되었습니다.

---

## 1. 아키텍처 개요 (Architecture Overview)

이 프로젝트는 **Python**과 **Tkinter**를 기반으로 한 GUI 애플리케이션입니다.  
**Modularized Monolith** 형태를 띠고 있으며, `main.py`가 전체 애플리케이션의 껍데기(Shell) 역할을 하고, 각 기능(Tab)들은 독립적인 모듈이나 서브시스템으로 분리되어 있습니다.

### 핵심 디자인 패턴
- **GUI와 로직의 분리:** 대부분의 기능에서 UI 코드(`*_tab.py` 또는 `main.py` 내부)와 비즈니스 로직(`*_processor.py`, `*_engine.py`)이 분리되어 있습니다.
- **멀티프로세싱 (Multiprocessing):** 대량의 파일 처리(변환, 중복 찾기, 태그 처리) 시 UI 프리징을 방지하고 성능을 높이기 위해 `multiprocessing` 및 `concurrent.futures`를 적극적으로 사용합니다.
- **설정 관리:** `json` 파일을 통해 사용자 설정을 영구 저장하고 로드합니다.

---

## 2. 모듈별 상세 구조 및 역할 (Module Structure)

프로젝트는 크게 **메인 시스템**, **공통 유틸리티**, 그리고 **5가지 핵심 기능 모듈**로 나뉩니다.

### 2.1. 메인 시스템 (Core System)
애플리케이션의 진입점이자 전체적인 레이아웃을 담당합니다.

| 파일명 | 역할 및 설명 | 연결 관계 |
|:---:|:---|:---|
| **`main.py`** | **프로그램 진입점**. 메인 윈도우 생성, 탭(Notebook) 구성, 설정 로드/저장, 간단한 탭(이름변경, 단일찾기, 태그)의 UI 로직 포함. | 모든 `*_tab.py` 및 `*_processor.py`를 통합 관리 |
| `requirements.txt` | 프로젝트 의존성 목록 (Pillow, piexif, psutil 등). | - |

### 2.2. 공통 유틸리티 (Common Utilities)
모든 모듈에서 공통적으로 사용하는 헬퍼 함수들입니다.

| 파일명 | 역할 및 설명 |
|:---:|:---|
| **`utils.py`** | **가장 기초적인 유틸리티**. `ScrollableFrame`(UI), `process_with_multicore`(병렬처리), 파일 쌍(Pair) 찾기 로직 등 포함. |
| `app_logger.py` | 로깅 시스템 래퍼. GUI 내 텍스트 박스로 로그를 리다이렉트하는 핸들러 포함. |
| `metadata_utils.py` | 이미지 메타데이터(EXIF, PNG Info) 추출 및 병합 로직. |
| `stego_utils.py` | 스테가노그래피(이미지 내 데이터 은닉) 관련 인코딩/디코딩 로직. |

---

### 2.3. 기능별 모듈 상세 (Feature Modules)

#### A. 이름 변경 (Renaming)
단순한 구조로 `main.py`가 UI를, `rename_processor.py`가 로직을 담당합니다.

- **`rename_processor.py`**: 파일 이름 변경, Undo(실행 취소) 데이터 관리 및 복구 로직.

#### B. 단일 파일 찾기 (Single File Finder)
- **`file_manager.py`**: 짝이 없는(Orphan) 이미지/텍스트 파일 검색, 파일 삭제 및 이동 로직.

#### C. 태그 처리 (Tag Processing)
- **`tag_processor.py`**: 텍스트 파일 파싱, 태그 치환/삭제/추가/정렬 로직. 대량 처리를 위한 멀티코어 로직 내장.

#### D. 이미지 변환 서브시스템 (Image Converter Subsystem)
가장 복잡한 모듈로, 별도의 파일들로 구성되어 있습니다.

| 파일명 | 역할 |
|:---:|:---|
| **`image_converter_tab.py`** | **UI 담당**. 변환 탭의 레이아웃, 사용자 입력 처리, 진행 상황 표시. |
| **`image_converter_engine.py`** | **핵심 엔진**. 이미지 변환, 리사이징, 포맷 변경, 메타데이터 보존 처리의 실제 수행. |
| `image_settings.py` | 변환기 전용 설정(`converter_config.json`)의 유효성 검사, 로드/저장. |
| `image_file_utils.py` | 파일 검색, 출력 경로 생성, 권한 확인 등 파일 시스템 관련 헬퍼. |
| `image_utils.py` | 파일 크기 포맷팅, 진행률 계산, 시간 예측 등 잡다한 헬퍼. |

#### E. 중복/유사 이미지 찾기 (Duplicate Finder)
별도의 스레드와 복잡한 알고리즘을 사용합니다.

| 파일명 | 역할 |
|:---:|:---|
| **`duplicate_finder_tab.py`** | **UI 담당**. 검색 옵션 설정, 결과 트리뷰(Treeview) 표시, 미리보기 제공. |
| **`duplicate_finder.py`** | **알고리즘 담당**. MD5 및 dHash 계산. **Union-Find 알고리즘**을 도입하여 범위 검색 시에도 연산 효율을 최적화. |

---

## 3. 데이터 흐름 및 상호작용 (Data Flow)

### 일반적인 작업 흐름
1. **User Action:** 사용자가 `main.py` 또는 `*_tab.py`의 GUI에서 버튼 클릭.
2. **Settings Check:** UI 컨트롤 변수(`tk.StringVar` 등) 또는 설정 파일에서 옵션 확인.
3. **Logic Invocation:**
   - 간단한 작업: `FileManager`, `RenameProcessor` 등을 직접 호출.
   - 무거운 작업: `threading.Thread`를 통해 백그라운드 작업 시작 -> 내부적으로 `multiprocessing.Pool` 또는 `ThreadPoolExecutor` 사용.
4. **Processing:** 각 `Processor/Engine`이 파일 시스템(FS)에 접근하여 읽기/쓰기 수행.
5. **Feedback:** 처리 결과(성공/실패 수, 로그)를 반환하고 GUI 업데이트.

### 주요 의존성 그래프(폴더 계층 구조아님)
```
main.py
 ├── utils.py
 ├── rename_processor.py
 ├── file_manager.py
 ├── tag_processor.py
 │    └── utils.py
 ├── image_converter_tab.py
 │    ├── image_converter_engine.py
 │    │    ├── image_file_utils.py
 │    │    ├── metadata_utils.py
 │    │    └── app_logger.py
 │    └── image_settings.py
 └── duplicate_finder_tab.py
      └── duplicate_finder.py
```

---

## 4. 유지보수 및 확장 가이드 (Maintenance Tips)

### 새로운 탭(기능) 추가 시
1. `main.py`의 `DatasetOrganizerGUI.create_widgets` 메서드 내 노트북에 새 프레임 추가.
2. UI 코드가 길다면 `new_feature_tab.py`로 분리하여 `main.py`에서 임포트 추천.
3. 로직은 반드시 별도의 클래스나 파일로 분리하여 테스트 용이성 확보.

### 로그 시스템 활용
- `app_logger.py`의 `logger` 객체를 사용하여 로그를 남기면, GUI의 로그 창(Image Converter 등)이나 파일로 기록됩니다.
- 디버깅 시 `print()` 대신 `logger.debug()` 사용을 권장합니다.

### 멀티프로세싱 주의사항
- Windows 환경에서 `multiprocessing` 사용 시, 반드시 실행 코드는 `if __name__ == "__main__":` 블록 보호가 필요합니다. (freeze_support 등)
- `main.py`의 `main()` 함수 내 로직을 참고하세요.

### 메타데이터/스테가노그래피 확장
- 새로운 메타데이터 형식을 지원하려면 `metadata_utils.py`의 `extract_all_metadata` 및 `prepare_save_options`를 수정하세요.
- 스테가노그래피 알고리즘 확장은 `stego_utils.py`에 구현되어 있습니다.

---

## 5. 버전별 개발 현황 (Version History)

### v1.0.5 (2026-02-09)
- **Tag Processor (태그 처리) 기능 대폭 확장**:
    - **인접 태그 수정**: 특정 타겟 태그를 기준으로 앞/뒤 태그의 접두사/접미사를 수정하는 정교한 편집 기능 추가.
    - **CSV 기반 특수 처리**: 대규모 CSV 데이터베이스를 활용하여 특정 카테고리(캐릭터, 아티스트 등) 태그들을 일괄적으로 추가(Prefix/Suffix), 치환, 삭제하는 기능 추가.
    - **태그 정규화 매칭**: 언더바(`_`)와 공백(` `)을 동일하게 취급하고 대소문자를 구분하지 않는 정규화 로직을 도입하여 CSV 매칭 정확도 극대화.
- **Duplicate Finder 기능 개선**:
    - **독립 경로 사용**: 상단 공통 폴더 설정과 무관하게 탭 내에서 독립적인 검색 경로를 지정할 수 있는 옵션 추가.
- **UI/UX 및 설정 관리**:
    - 새로운 기능들에 대한 설정(CSV 경로, 모드, 독립 경로 등)이 `settings.json`에 영구 저장 및 자동 로드되도록 통합.

### v1.0.4 (2026-02-01)
- **Duplicate Finder 기능 확장**:
    - **태그 내용 기반 검색**: 이미지뿐만 아니라 짝이 되는 캡션 파일(.txt)의 내용을 비교하여 유사한 이미지를 찾는 기능 추가 (Jaccard Similarity 활용).
    - **텍스트 파일 동반 처리**: 중복 이미지 삭제/이동 시, 연결된 캡션 파일(.txt)도 함께 처리하는 옵션 추가.
- **아키텍처 개선**:
    - `duplicate_finder.py`에 태그 비교 및 로딩 로직 통합.
    - `ImageInfo` 구조체에 `tag_set` 필드 추가.

### v1.0.3 (2026-01-19)
- **EXE 패키징 안정화**:
    - 설정 파일(`settings.json`, `converter_config.json`) 저장 경로 로직 개선.
    - PyInstaller 패키징 환경(OneFile)에서도 설정이 휘발되지 않고 실행 파일과 동일한 위치에 영구 저장되도록 수정하여 사용자 편의성 증대.

### v1.0.2 (2026-01-19)
- **Tag Processor (태그 처리) 기능 강화**:
    - **조건부 추가/삭제**: 특정 태그가 존재할 때만 태그를 추가하거나 삭제하는 조건부 로직 도입.
    - **실행 취소 (Undo)**: 태그 처리 작업에 대한 실행 취소 기능 추가.
    - **하위 폴더 검색**: 태그 탭에서도 하위 폴더 포함 검색 옵션 지원.
    - **미리보기 개선**: 실제로 변경이 발생하는 파일의 수만 정확히 집계하여 표시.
- **시스템 안정성 및 관리 개선**:
    - **로그 시스템 개편**: `logs/app_YYYY-MM-DD.log` 형식으로 날짜별 로그 파일 자동 생성.
    - **Undo 시스템 개편**: `logs/undo/` 폴더에 타임스탬프가 포함된 JSON 파일로 이력을 관리하여 데이터 안전성 확보.

### v1.0.1 (2026-01-17)
- **Duplicate Finder 기능 대폭 강화**:
    - **유사도 그룹 검색 (Range Search)**: 사용자가 지정한 유사도 범위(Start~End) 내의 모든 그룹을 한 번에 검색.
    - **성능 최적화**: Union-Find 자료구조를 도입하여 범위 검색 시에도 연산 횟수를 단일 검색 수준으로 유지.
    - **UI 개선**: 검색 소요 시간 표시 추가 및 메인 설정의 '사용 코어' 수 반영.
    - **사용자 경험(UX) 개선**: 범위 입력 시 시작값이 종료값보다 클 경우 자동으로 보정(Swap)하는 편의 기능 추가.

### v1.0.0 (2026-01-17) - First Release
- **Initial Release**: 데이터셋 관리를 위한 통합 툴킷 완성.
- **주요 기능**:
    - **Renaming**: 이미지-텍스트 쌍 유지 및 Undo 기능 지원.
    - **Single Finder**: 짝 없는 파일 탐색 및 일괄 정리 기능.
    - **Tag Processor**: 태그 치환/삭제/이동 및 누락된 인원수 태그 자동 주입.
    - **Image Converter**: 병렬 처리를 이용한 고속 변환 및 메타데이터(Stealth PNG 등) 보존.
    - **Duplicate Finder**: MD5 및 dHash 기반의 중복/유사 이미지 탐색.
- **기반 기술**: Python 3.8+, Tkinter, Pillow, Multiprocessing.
