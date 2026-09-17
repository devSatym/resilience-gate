# C086 snapshot: orchestration is added to the reviewed scorer image. C088
# later adds the non-fatal Grafana annotation helper.
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

COPY kubernetes/chaos-experiments/orchestrate.sh /opt/chaos-gate/orchestrate.sh
COPY kubernetes/chaos-experiments/score_experiment.py /opt/chaos-gate/score_experiment.py
COPY kubernetes/chaos-experiments/workflow.yaml /opt/chaos-gate/workflow.yaml

RUN set -eux; \
    chmod 0555 /opt/chaos-gate/orchestrate.sh /opt/chaos-gate/score_experiment.py; \
    chmod 0444 /opt/chaos-gate/workflow.yaml; \
    chown --recursive 65532:65532 /opt/chaos-gate

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /work
USER 65532:65532

ENTRYPOINT ["/opt/chaos-gate/orchestrate.sh"]
