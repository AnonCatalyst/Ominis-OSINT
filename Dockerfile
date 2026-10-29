# Small runtime image. No compilers: every dependency ships a wheel.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY ominis.py ./
COPY ominis_src ./ominis_src

# Running the container with no arguments prints help instead of waiting for
# a prompt: a guided first run needs a terminal.
ENTRYPOINT ["python", "ominis.py"]
CMD ["--help"]
