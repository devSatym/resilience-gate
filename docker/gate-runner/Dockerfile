# The gate runner is deliberately self-contained.  It carries the reviewed
# orchestration, scoring, and annotation code in the image selected by an
# immutable digest; a mutable ConfigMap must never be able to change a
# promotion verdict after the image has been reviewed.
# python:3.12.14-slim-trixie multi-platform index, resolved when this file was
# reviewed. Pinning the base avoids rebuilding a different runner when its tag
# moves; upgrades are an explicit source change.
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

# Use the repository root as the build context so all copied gate code is part
# of the same reviewed image build.  The AnalysisTemplate does not mount these
# files from Kubernetes.
COPY kubernetes/chaos-experiments/orchestrate.sh /opt/chaos-gate/orchestrate.sh
COPY kubernetes/chaos-experiments/score_experiment.py /opt/chaos-gate/score_experiment.py
COPY kubernetes/chaos-experiments/annotate.py /opt/chaos-gate/annotate.py
COPY kubernetes/chaos-experiments/workflow.yaml /opt/chaos-gate/workflow.yaml

RUN set -eux; \
    chmod 0555 /opt/chaos-gate/orchestrate.sh /opt/chaos-gate/score_experiment.py /opt/chaos-gate/annotate.py; \
    chmod 0444 /opt/chaos-gate/workflow.yaml; \
    chown --recursive 65532:65532 /opt/chaos-gate

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /work
USER 65532:65532

ENTRYPOINT ["/opt/chaos-gate/orchestrate.sh"]
