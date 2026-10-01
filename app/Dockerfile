FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Kubernetes must be able to prove that this image's configured user is
# non-root when the chart sets runAsNonRoot. Keep both IDs explicit rather
# than relying on the distribution's system-user allocation.
RUN addgroup --gid 10001 --system app \
    && adduser --uid 10001 --system --ingroup app app

WORKDIR /app

# Install the reviewed transitive lock before application code so ordinary
# source edits retain the dependency layer in local and CI builds.
COPY requirements.lock ./requirements.lock
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.lock

# The application imports itself as the ``app`` package (for example,
# ``from app.payment import ...``).  Keep the build context under that
# package directory rather than flattening its modules into /app.
COPY --chown=10001:10001 . ./app/

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
