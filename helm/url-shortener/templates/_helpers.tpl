{{/* Expand the name of the chart. */}}
{{- define "url-shortener.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Create a chart name and version suitable for labels. */}}
{{- define "url-shortener.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a resource name while avoiding a duplicate chart name when the release
already contains it (for example, url-shortener-staging).
*/}}
{{- define "url-shortener.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := include "url-shortener.name" . }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Common labels — applied to every resource. */}}
{{- define "url-shortener.labels" -}}
helm.sh/chart: {{ include "url-shortener.chart" . }}
app.kubernetes.io/name: {{ include "url-shortener.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Selector labels must never change after the first deployment. */}}
{{- define "url-shortener.selectorLabels" -}}
app.kubernetes.io/name: {{ include "url-shortener.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Service account name — use an explicit override or the release fullname. */}}
{{- define "url-shortener.serviceAccountName" -}}
{{- if .Values.serviceAccount.name }}
{{- .Values.serviceAccount.name }}
{{- else }}
{{- include "url-shortener.fullname" . }}
{{- end }}
{{- end }}

{{/*
The application and optional PostgreSQL dependency use this Secret. Environment
overlays provide a stable explicit target name because Helm values cannot
template a subchart's `postgresql.auth.existingSecret` setting.
*/}}
{{- define "url-shortener.credentialsSecretName" -}}
{{- if .Values.externalSecrets.target.name }}
{{- .Values.externalSecrets.target.name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-credentials" (include "url-shortener.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/* Render only immutable OCI image references. */}}
{{- define "url-shortener.image" -}}
{{- $repository := required "image.repository is required" .Values.image.repository -}}
{{- $digest := required "image.digest is required; tags are intentionally unsupported" .Values.image.digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" $digest) -}}
{{- fail "image.digest must be a sha256 digest; mutable image tags are not supported" -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- end }}

{{/* Redis master host supplied by the Bitnami dependency. */}}
{{- define "url-shortener.redisHost" -}}
{{- printf "%s-redis-master.%s.svc.cluster.local" (include "url-shortener.fullname" .) .Release.Namespace -}}
{{- end }}

{{/* PostgreSQL primary host supplied by the Bitnami dependency. */}}
{{- define "url-shortener.postgresHost" -}}
{{- printf "%s-postgresql.%s.svc.cluster.local" (include "url-shortener.fullname" .) .Release.Namespace -}}
{{- end }}
