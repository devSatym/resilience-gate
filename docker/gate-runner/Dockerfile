# C085 snapshot: the first runner image packages the already-tested scorer.
# C086 adds orchestration; C088 adds optional Grafana annotation support.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

ARG KUBECTL_VERSION=v1.34.1
ARG TARGETARCH

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64|arm64) kubectl_arch="$TARGETARCH" ;; \
      *) echo "unsupported target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    apt-get update; \
    apt-get install --yes --no-install-recommends bash ca-certificates curl; \
    curl --fail --silent --show-error --location \
      --output /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${kubectl_arch}/kubectl"; \
    chmod 0555 /usr/local/bin/kubectl; \
    kubectl version --client --output=yaml; \
    apt-get purge --yes curl; \
    apt-get autoremove --yes; \
    rm -rf /var/lib/apt/lists/*; \
    install --directory --mode=0755 --owner=65532 --group=65532 /opt/chaos-gate /results /work

COPY kubernetes/chaos-experiments/score_experiment.py /opt/chaos-gate/score_experiment.py

RUN set -eux; \
    chmod 0555 /opt/chaos-gate/score_experiment.py; \
    chown --recursive 65532:65532 /opt/chaos-gate

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /work
USER 65532:65532

ENTRYPOINT ["/opt/chaos-gate/score_experiment.py"]
