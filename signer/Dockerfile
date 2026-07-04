# The signer is a private-key boundary. Install only the reviewed lock and run
# it as an unprivileged numeric user so Kubernetes can enforce the same policy.
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --prefix=/install --requirement requirements.lock

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

RUN addgroup --system --gid 10001 signer \
    && adduser --system --uid 10001 --ingroup signer --home /nonexistent --no-create-home signer

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=10001:10001 main.py permit2.py ./

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/health', timeout=2).read()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
