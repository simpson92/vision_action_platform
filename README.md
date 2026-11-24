# Vision Action Platform

<p align="center"><img src="docs/images/banner.jpg" width="100%" alt="Vision Action Platform"></p>

## 1. 프로젝트 소개

Vision Action Platform은 영상 속 사람의 동작을 AI로 인식하는 웹 서비스입니다. 동작 인식 모델을 스크립트로 돌릴 필요 없이, 브라우저에서 분석을 요청하고 결과를 기록으로 남길 수 있습니다.

<p align="center"><img src="docs/images/overview_calm.svg" width="100%" alt="입력 → 결과 → 관리"></p>

<p align="center">
<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"> <img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"> <img src="https://img.shields.io/badge/DRF-A30000?style=for-the-badge&logo=django&logoColor=white" alt="DRF"> <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"><br>
<img src="https://img.shields.io/badge/Celery-37814A?style=for-the-badge&logo=celery&logoColor=white" alt="Celery"> <img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis"> <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"> <img src="https://img.shields.io/badge/Docker_Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Compose"><br>
<img src="https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white" alt="scikit-learn"> <img src="https://img.shields.io/badge/YOLO11_Pose-111F68?style=for-the-badge&logo=ultralytics&logoColor=white" alt="YOLO11 Pose"> <img src="https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white" alt="Chart.js">
</p>

> 확률이 낮거나 1·2등 차이가 작으면 답을 확정하지 않고 **판단 보류**로 표시합니다. 결과는 참고용이며 위험 행동 판정이 아닙니다.

## 2. 실행 방법

<p align="center"><img src="docs/images/run_steps_calm.svg" width="100%" alt="저장소 받기 → 모델 확인 → 실행 → 관리자 계정 → 접속"></p>

**준비물** &nbsp; <img src="https://img.shields.io/badge/Docker_Desktop-WSL2-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker Desktop"> <img src="https://img.shields.io/badge/Git-F05032?style=flat-square&logo=git&logoColor=white" alt="Git">

#### 1️⃣ 저장소 받기 · `.env` 만들기

```bash
git clone https://github.com/simpson92/vision_action_platform.git
cd vision_action_platform
cp .env.example .env
```

`.env`에서 비밀번호와 IP Webcam 주소만 바꾸면 됩니다. `.env`는 Git에 올라가지 않습니다.

#### 2️⃣ 모델 파일 확인

모델은 저장소에 함께 들어 있어서 따로 받을 필요가 없습니다(`ai_service/models/`, 약 6.6MB).

<details>
<summary>파일 목록 보기</summary>

```text
ai_service/models/
├── rf_action_baseline.joblib   # Random Forest (300 trees, 입력 1,140)
├── rf_feature_columns.json     # 1,140개 Feature 이름과 순서
├── rf_training_info.json       # 6 Class, 30 Step, min_valid_frames 10
├── yolo11n-pose.pt             # YOLO Pose 가중치
└── SHA256SUMS.txt
```

</details>

> [!NOTE]
> AI 서버는 시작할 때 `SHA256SUMS.txt`로 파일이 바뀌지 않았는지 확인한 뒤에만 모델을 불러옵니다.

#### 3️⃣ 실행

```bash
docker compose up --build -d
docker compose ps
```

5개 서비스가 모두 `running`/`healthy`면 준비 완료입니다. **마이그레이션은 django가 시작할 때 자동으로 적용**됩니다. 직접 하려면 `docker compose exec django python manage.py migrate`를 실행합니다.

#### 4️⃣ 관리자 계정 만들기

```bash
docker compose exec django python manage.py createsuperuser
```

> [!TIP]
> `.env`에 `DJANGO_SUPERUSER_*` 값을 채워 두면 처음 실행할 때 관리자 계정이 자동으로 만들어져서 이 단계를 건너뛸 수 있습니다.

#### 5️⃣ 접속

| | 화면 | 주소 |
|:---:|---|---|
| 🙋 | 사용자 화면 (회원가입 → AI 분석) | http://localhost:8000/ |
| 🛠️ | Django Admin | http://localhost:8000/admin/ |
| 📊 | 관리자 대시보드 | http://localhost:8000/dashboard/ |
| ⚡ | FastAPI 문서 (개발용) | http://localhost:8001/docs |

<details>
<summary>🧪 테스트 실행</summary>

```bash
docker compose exec django python manage.py test           # 웹·권한·Celery 저장 23개
docker compose exec fastapi python -m pytest -q tests      # AI 서버 7개 (테스트 영상이 있으면 실제 추론까지)
```

</details>

## 3. 전체 아키텍처

<p align="center"><img src="docs/images/architecture_calm.svg" width="100%" alt="전체 아키텍처"></p>

`compose.yaml`이 서비스 5개를 띄웁니다. 밖으로 열린 문은 **django(8000) 하나**이고, 서비스끼리는 `localhost`가 아니라 서비스 이름(`fastapi`, `redis`, `postgres`)으로 대화합니다.

| | 서비스 | 하는 일 | 하지 않는 일 |
|:---:|---|---|---|
| <img src="docs/images/dots/green.svg" width="12" alt=""> | **django** | 회원, 분석 요청 CRUD, 권한, 화면, Admin, 대시보드 집계 | AI 추론, 모델 학습 |
| <img src="docs/images/dots/red.svg" width="12" alt=""> | **redis** | Celery 메시지 브로커 | 업무 데이터 영구 저장 |
| <img src="docs/images/dots/amber.svg" width="12" alt=""> | **celery** | 영상 확보(업로드 파일 / IP Webcam 수집), FastAPI 호출, 결과 저장, 재시도 | 화면 렌더링 |
| <img src="docs/images/dots/sky.svg" width="12" alt=""> | **fastapi** | 영상 → Pose·Tracking → Feature → Random Forest → JSON | DB·ORM·회원 관리 |
| <img src="docs/images/dots/purple.svg" width="12" alt=""> | **postgres** | 사용자·작업·사람별 예측 영구 저장 (`postgres_data` 볼륨) | — |

## 4. DB 설계 (ERD)

<p align="center"><img src="docs/images/erd_calm.svg" width="100%" alt="ERD"></p>

📁 직접 작성한 모델은 [`backend/analyses/models.py`](backend/analyses/models.py)에 있습니다. `auth_user`는 Django 기본 테이블입니다.

- <img src="docs/images/dots/green.svg" width="12" alt=""> **auth_user**: 회원 아이디, 비밀번호 해시, 관리자 여부
- <img src="docs/images/dots/amber.svg" width="12" alt=""> **AnalysisJob**: 분석 요청 1건. 누가, 어떤 입력으로 요청했고 지금 어떤 상태인지
- <img src="docs/images/dots/sky.svg" width="12" alt=""> **PersonPrediction**: 그 작업에 나온 사람 1명의 예측과 판단 근거. 두 사람이 나오면 2행

> [!NOTE]
> 영상 파일은 DB가 아니라 Media 볼륨에 두고 경로만 저장합니다. IP Webcam 주소도 DB에 남기지 않고 카메라 번호만 저장합니다.

<details>
<summary>전체 필드 보기</summary>

```mermaid
erDiagram
    auth_user ||--o{ AnalysisJob : "requests"
    AnalysisJob ||--o{ PersonPrediction : "contains"
    auth_user {
        int id PK
        string username
        string password "hash"
        bool is_staff
    }
    AnalysisJob {
        bigint id PK
        int user_id FK
        string title
        text memo
        string input_type "upload | ip_webcam"
        string video "Media 경로"
        int camera_index "허용 목록 번호"
        float capture_seconds
        string expected_action "사용자 선택, 정답 아님"
        string status "PENDING | STARTED | SUCCESS | FAILURE"
        string celery_task_id
        text error_message
        int processing_ms
        float video_duration_sec
        json video_meta "fps, frame_count, 해상도"
        datetime created_at
        datetime completed_at
    }
    PersonPrediction {
        bigint id PK
        bigint job_id FK
        int track_id "작업 안의 추적 번호"
        string action_label "6개 동작 | UNCERTAIN | INSUFFICIENT_INPUT"
        string raw_label
        float confidence
        float margin
        json probabilities "최종 6개 동작 확률"
        json details "판단 근거: 구간별 확률, 구간 일치율, 관절 인식"
        int window_count
        int valid_frames
        string input_quality
    }
```

</details>

## 5. AI 추론 버튼 구현 흐름

<p align="center"><img src="docs/images/ai_flow_icons_calm.svg" width="100%" alt="AI 추론 버튼 흐름"></p>

**AI 분석 시작** 버튼을 누르면 웹 서버는 분석을 기다리지 않고 작업 ID부터 돌려줍니다(②). 무거운 추론은 Celery가 뒤에서 처리하고(③~⑥), 화면은 상태를 주기적으로 물어 결과를 받아 그립니다(⑦).

> [!TIP]
> 화면의 지표와 그래프는 누적 통계가 아니라 **지금 보는 영상 한 건**의 값입니다. 이력에서 다른 행을 누르면 그 영상의 결과로 바뀝니다. 전체 누적 통계는 관리자 대시보드에서 봅니다.

<details>
<summary>자세한 순서도 보기 (오류 분기 포함)</summary>

```mermaid
sequenceDiagram
    autonumber
    actor U as 사용자
    participant JS as static/js/analyses.js
    participant V as analyses/views.py (DRF)
    participant S as analyses/serializers.py
    participant DB as PostgreSQL
    participant R as Redis
    participant T as analyses/tasks.py (Celery)
    participant F as ai_service/routers/predictions.py
    participant AI as services/pose_pipeline.py + action_inference.py

    U->>JS: AI 분석 시작 클릭
    JS->>V: POST /api/analyses/ (FormData)
    V->>S: 입력 검증 (확장자·용량·허용 카메라)
    alt 잘못된 입력
        S-->>JS: 400 + 오류 메시지
    else 정상
        V->>DB: AnalysisJob 생성 (PENDING)
        V-->>JS: 202 + 작업 ID (분석을 기다리지 않음)
        V->>R: transaction.on_commit → run_analysis.delay(id)
    end
    R->>T: 작업 전달
    T->>DB: STARTED
    opt IP Webcam
        T->>T: camera_capture.py 8초 수집 → MP4
    end
    T->>F: POST /predict/video (영상)
    F->>AI: Pose·ByteTrack → 38-D Feature → 30 Step → RandomForest
    AI-->>F: track_id별 action·confidence + 구간별 확률(timeline)
    F-->>T: predictions JSON (or 422 오류)
    T->>DB: ORM: PersonPrediction(+details) 저장 + SUCCESS / FAILURE
    loop 1초 간격 (점점 느리게)
        JS->>V: GET /api/analyses/{id}/status/
        V-->>JS: 상태 · 사람별 결과
    end
    JS-->>U: 진행 단계 · 사람별 카드 · 영상 지표 4개 · 그래프 2개
```

</details>

## 6. 사용한 모델과 입력 형식

<p align="center"><img src="docs/images/model_pipeline_calm.svg" width="100%" alt="모델 파이프라인과 지원 동작"></p>

영상에서 사람마다 관절 17개를 찾고(YOLO11 Pose), 30 Step 동안의 움직임을 1,140개 숫자로 바꾼 뒤 Random Forest가 6개 동작 중 하나로 분류합니다. 모델 파일은 모두 `ai_service/models/`에 있습니다.

- 📹 **업로드:** MP4 등 영상, 최대 50MB. 전신이 보이는 3~10초 영상이 가장 잘 맞습니다.
- 📱 **IP Webcam:** `.env`의 `IP_WEBCAM_ALLOWED_URLS`에 등록한 카메라만, **8초** 수집합니다.

#### ⚡ FastAPI가 받는 것과 돌려주는 것

| 엔드포인트 | 받는 것 | 돌려주는 것 |
|---|---|---|
| `GET /health` | 없음 | 모델 준비 여부, Class 6개, Feature 1,140 |
| `POST /predict/video` | 영상 파일 (multipart `file`) | 사람(`track_id`)마다 동작 · Confidence · 1·2등 차이 · 구간별 확률 + 처리 시간 |

> [!NOTE]
> 읽을 수 없는 영상은 `422`, 지원하지 않는 형식·빈 파일은 `400`, 모델 미준비는 `503`을 돌려줍니다. 사람이 없으면 `200`과 `status: "no_person"`입니다. Celery는 `422`·`400`이면 바로 실패로 저장하고, `503`·타임아웃은 2번 다시 시도합니다.

<details>
<summary>응답 예시 보기 (JSON)</summary>

```json
{
  "status": "ok",
  "video": {"filename": "S03_A001_T01.mp4", "fps": 25.0, "frame_count": 62, "duration_sec": 2.48},
  "predictions": [
    {"track_id": 1, "action_label": "bend_return", "raw_label": "bend_return",
     "confidence": 0.25, "margin": 0.057, "window_count": 1, "window_agreement": 1.0,
     "valid_frames": 62, "detected_frames": 62, "interpolated_joints": 0, "mean_keypoint_conf": 0.95,
     "input_quality": "good", "probabilities": {"bend_return": 0.25, "leg_raise_lower": 0.193, "...": 0},
     "whole_probabilities": {"...": 0}, "window_mean_probabilities": {"...": 0},
     "timeline": [{"start_sec": 0.0, "end_sec": 2.44, "label": "bend_return", "probabilities": {"...": 0}}]}
  ],
  "processing_ms": 3100
}
```

`timeline`은 2초 구간(0.5초씩 이동)마다의 확률이고, `window_agreement`는 그 구간들 중 최종 1등과 같은 답을 낸 비율입니다. 화면의 "구간 일치율"과 그래프가 이 값을 씁니다.

</details>

## 7. 실행 결과와 검증

#### 📊 모델 재사용 검증

<p align="center"><img src="docs/images/cards/eval.png" width="100%" alt="모델 재사용 검증"></p>

5일차 영상 12개(S02 검증용, S03 테스트용)를 서비스와 같은 코드로 분석했습니다(`ai_service/scripts/evaluate_videos.py`, 결과 [`docs/evaluation_S02_S03.txt`](docs/evaluation_S02_S03.txt)). 기준값은 **S02로만** 골랐고 S03은 마지막 확인에만 썼습니다. 틀린 답은 모두 1·2등 차이가 작아 "판단 보류"로 표시됐고, 확정한 답은 모두 맞았습니다. 효과가 없어 반영하지 않은 실험은 [`docs/inference_experiments.md`](docs/inference_experiments.md)에 있습니다.

#### 🖥️ 실행 화면

과제가 요구하는 화면 4개(정상 분석·오류·관리자 화면·대시보드)에 "판단 보류" 1개를 더했습니다. 카드를 누르면 원본 캡처가 열립니다.

<p align="center"><a href="docs/images/analysis.png"><img src="docs/images/cards/case1.png" width="100%" alt="정상 분석"></a></p>
<p align="center"><a href="docs/images/failure.png"><img src="docs/images/cards/case2.png" width="100%" alt="오류·실패"></a></p>
<p align="center"><a href="docs/images/admin_jobs.png"><img src="docs/images/cards/case3.png" width="100%" alt="관리자 화면"></a></p>
<p align="center"><a href="docs/images/dashboard.png"><img src="docs/images/cards/case4.png" width="100%" alt="관리자 대시보드"></a></p>
<p align="center"><a href="docs/images/uncertain.png"><img src="docs/images/cards/case5.png" width="100%" alt="판단 보류"></a></p>

> [!NOTE]
> 캡처는 시연 PC(Windows + WSL2 Docker)에서 5개 서비스를 띄우고 찍었습니다. "판단 보류"만 같은 코드로 개발 환경에서 찍었습니다. 일반 회원이 `/admin/`에 들어가면 [접근이 막힙니다](docs/images/admin_denied.png).

#### ✅ 기능 테스트 (T01~T10)

<p align="center">
<a href="docs/images/t01_health.png"><img src="docs/images/cards/t01.png" width="49%" alt="T01"></a>
<a href="docs/images/analysis.png"><img src="docs/images/cards/t02.png" width="49%" alt="T02"></a>
</p>
<p align="center">
<img src="docs/images/cards/t03.png" width="49%" alt="T03">
<a href="docs/images/admin_predictions.png"><img src="docs/images/cards/t04.png" width="49%" alt="T04"></a>
</p>
<p align="center">
<a href="docs/images/t05_async.png"><img src="docs/images/cards/t05.png" width="49%" alt="T05"></a>
<a href="docs/images/history.png"><img src="docs/images/cards/t06.png" width="49%" alt="T06"></a>
</p>
<p align="center">
<a href="docs/images/t07_forbidden.png"><img src="docs/images/cards/t07.png" width="49%" alt="T07"></a>
<a href="docs/images/dashboard.png"><img src="docs/images/cards/t08.png" width="49%" alt="T08"></a>
</p>
<p align="center">
<a href="docs/images/failure.png"><img src="docs/images/cards/t09.png" width="49%" alt="T09"></a>
<a href="docs/images/t10_restart.png"><img src="docs/images/cards/t10.png" width="49%" alt="T10"></a>
</p>

## 8. 교재와 다르게 구현한 점과 이유

<details>
<summary>펼쳐 보기 (7가지 항목과 참고 논문)</summary>

| 항목 | 교재·6~8일차 | 이 서비스 | 이유 |
|---|---|---|---|
| 판단 보류 기준 | 확률 0.55 미만이면 UNKNOWN | 확률 0.20 미만 **또는 1·2등 차이 0.03 미만**이면 판단 보류 | 6 clip으로 학습한 RF는 확률이 0.2~0.3대라 0.55면 7일차처럼 전부 UNKNOWN. S02로 기준을 다시 맞춤 |
| 예측 안정화 | 최근 5개 예측 다수결 | 전체 구간 확률 + 2초 Window 확률 평균을 반씩 | 다수결은 확률 정보를 버림. S02 Top-1 2/6 → 4/6 |
| 결측 관절 | 그대로 사용 | Confidence 0.3 미만 관절을 같은 사람의 앞뒤 Frame으로 보간 | 순간적으로 튀는 관절 값 완화 (Puchała 외, 2023) |
| 모델 파일 로드 | `joblib.load()` 바로 호출 | SHA256 해시 확인 후 로드 | `joblib.load`는 pickle 실행 → 우리 파일인지 확인 |
| 입력 품질 | 없음 | 검출 Frame 비율·관절 Confidence로 좋음/보통/나쁨 표시 | 과제 문서: "Confidence와 입력 품질을 함께 표시" |
| 카메라 주소 | 사용자 입력 | `.env` 허용 목록에서 번호로만 선택 | 임의 URL 호출(SSRF) 방지, 접속정보 비노출 |
| 결과 화면 | 동작 이름과 확률 | 영상 한 건의 판단 근거(구간별 확률 그래프, 구간 일치율, 관절 인식 품질)를 함께 표시 | 확률이 낮은 모델이라 숫자 하나보다 "왜 이 답인지, 왜 보류했는지"를 보여 주는 게 더 정직함 |

참고 논문
- Nunes, Faria, Peixoto (2017). *Pattern Recognition Letters* — 스켈레톤 Feature + Random Forest
- Puchała, Kasprzak, Piwowarski (2023). *Sensors* 23(14) — 포즈 Tracking + 슬라이딩 Window, 결측 관절 보정
- Yan, Xiong, Lin (2018). *AAAI* — ST-GCN (데이터가 늘면 FastAPI 서버만 교체하는 확장 방향)

</details>

## 9. 문제 해결 기록

<details>
<summary>펼쳐 보기 (해결한 오류 7가지)</summary>

**1) 7일차처럼 모든 결과가 UNKNOWN**
- 보인 문제: 정답 동작이 1등인데도 확률 0.25라 기준 0.55에 걸려 전부 UNKNOWN
- 확인한 곳: `reports/day07/runtime_comparison.md`(평균 Confidence 0.23), S02 영상 6개의 확률 분포
- 바꾼 것: 1등 확률만 보지 않고 1·2등 차이(margin)를 함께 보도록 `action_inference.py` 수정, 기준은 S02로 선택
- 확인: S02·S03에서 확정한 5건 모두 정답, 틀린 건 모두 판단 보류

**2) 6일차 Test 6/6인데 서비스에서는 4/6**
- 보인 문제: 같은 S03 영상인데 정확도가 떨어짐
- 확인한 곳: 학습 스크립트 `34_build_sequence_dataset.py` — Clip 전체를 30 Step으로 리샘플링
- 원인: 긴 영상(5초 초과)은 Window로만 예측해 학습 때와 입력 구간이 달랐음
- 바꾼 것: 학습과 같은 "전체 구간" 예측을 항상 포함하고 Window 평균과 섞음 → S03 5/6, S02 4/6

**3) 원본 `src/common.py`가 설정 파일을 못 찾음**
- 원본은 `configs/project.json`, 새 구조는 `ai_service/project.json` → `CONFIG_PATH` 수정

**4) Tracking 시 `ModuleNotFoundError: lap` / Celery 시작 시 `No module named 'packaging'`**
- `model.track()`(ByteTrack)에 필요한 `lap`, kombu Redis 전송 모듈이 쓰는 `packaging`을 각각 `requirements.txt`에 고정

**5) 대시보드 차트가 인터넷 없는 곳에서 안 보임**
- Chart.js를 CDN 대신 `backend/static/vendor/`에 포함(MIT 라이선스 동봉)

**6) Docker에서 fastapi만 계속 재시작 (`ImportError: libxcb.so.1`)**
- 확인한 곳: `docker compose logs fastapi` → `import cv2`에서 실패
- 원인: `ultralytics`가 의존성으로 화면용 `opencv-python`을 설치해 `opencv-python-headless`를 덮어씀. slim 이미지에는 화면 라이브러리(libxcb·libGL)가 없음
- 바꾼 것: `ai_service/Dockerfile`에서 두 opencv를 지우고 headless판만 다시 설치 (apt로 화면 라이브러리를 까는 것보다 이미지가 작음)

**7) Docker에서 분석 요청 시 `AI 서버 오류 HTTP 500` (`operator torchvision::nms does not exist`)**
- 확인한 곳: `docker compose logs fastapi` → YOLO warmup 중 `import torchvision`에서 실패
- 원인: torch는 CPU 전용 저장소에서, torchvision은 ultralytics 의존성으로 PyPI에서 따로 설치돼 서로 다른 torch 판으로 빌드된 짝이 됨
- 바꾼 것: Dockerfile에서 torch와 torchvision을 같은 CPU 저장소에서 함께 설치

</details>

## 폴더 구조

```text
vision_action_platform/
├── backend/                 # Django·DRF + Celery Worker (같은 이미지)
│   ├── config/              # settings, urls, celery
│   ├── accounts/            # 회원가입·로그인·로그아웃
│   ├── analyses/            # models, serializers, views(API), page_views(화면·대시보드), tasks, services, camera_capture, admin, tests
│   ├── templates/  static/
│   ├── Dockerfile  entrypoint.sh  requirements.txt
├── ai_service/              # FastAPI 추론 서버
│   ├── main.py  settings.py  schemas.py
│   ├── routers/predictions.py
│   ├── services/            # model_loader, pose_pipeline, action_inference
│   ├── src/                 # 6~8일차 원본 모듈 (common.py 경로만 수정)
│   ├── models/              # joblib · JSON · YOLO Pose · SHA256SUMS
│   ├── scripts/             # evaluate_videos(정확도 평가), experiment_inference(추론 방식 실험)
│   ├── tests/
│   ├── Dockerfile  requirements.txt
├── compose.yaml  .env.example  docs/
```
