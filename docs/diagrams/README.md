# Diagram sources

`architecture.mmd` and `architecture.py` are the current conceptual source for
the Resilience Gate architecture diagram. Run:

```bash
python3 docs/diagrams/architecture.py --check
```

to verify they match, or omit `--check` to regenerate the Mermaid source.

The diagram describes source configuration, not observed infrastructure. It
does not prove that a cloud project, Kubernetes controller, payment, promotion,
telemetry pipeline, or chaos run exists.

Some image files in this working tree are inherited snapshots rather than
current C095 diagram sources. They are not evidence, are not referenced by the
current architecture documentation, and should not be staged as part of this
documentation change without independent review and regeneration.
