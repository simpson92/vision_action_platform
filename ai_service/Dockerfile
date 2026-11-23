FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    YOLO_OFFLINE=1

# opencv-python-headless는 libGL 등 시스템 패키지가 필요 없어 apt 설치 단계를 두지 않음

WORKDIR /app
# GPU가 없는 컨테이너라 CPU 전용 torch를 먼저 설치 (CUDA 판보다 수 GB 작음)
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
# torchvision도 같은 CPU 저장소에서 함께 설치해야 torch와 짝이 맞음.
# (PyPI의 torchvision을 따로 받으면 다른 torch 판으로 빌드된 것이라 추론 때 "torchvision::nms does not exist" 오류)
RUN pip install --no-cache-dir torch==2.15.0 torchvision --index-url ${TORCH_INDEX_URL}
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ultralytics가 화면용 opencv-python을 같이 설치해 headless판을 덮어씀 → libxcb/libGL을 찾다 시작 실패.
# 둘 다 지우고 headless판만 다시 설치
RUN pip uninstall -y opencv-python opencv-python-headless \
    && pip install --no-cache-dir opencv-python-headless==5.0.0.93

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request,json,sys; sys.exit(0 if json.load(urllib.request.urlopen('http://localhost:8000/health'))['model_ready'] else 1)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
