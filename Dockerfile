FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EASYOCR_MODULE_PATH=/app/app/models

WORKDIR /app

# OpenCV's headless wheel does not need an X server, but these libraries are
# required by its runtime and by Pillow/EasyOCR on Debian slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && grep -Ev '^(torch|torchvision)==' requirements.txt > /tmp/requirements-no-torch.txt \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.5.1+cpu torchvision==0.20.1+cpu \
    && python -m pip install -r /tmp/requirements-no-torch.txt

COPY app ./app

# Download and initialize the Korean/English EasyOCR models during image
# build. A failed model download or incompatible Torch/EasyOCR combination
# must fail the build instead of surfacing only on the first user request.
RUN python -c "import easyocr; r=easyocr.Reader(['ko','en'], gpu=False, verbose=False, model_storage_directory='/app/app/models', user_network_directory='/app/app/models/user_network'); print('EasyOCR model load OK')"

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
