# Diagram sources

`architecture.mmd` and `architecture.py` are the current conceptual source for
the Resilience Gate architecture diagram. Run:

```bash
python3 docs/diagrams/architecture.py --check
```

to verify they match, or omit `--check` to regenerate the Mermaid source.

The Mermaid diagram describes the current source configuration. Live outcomes
are documented separately in the
[verification report](../verification-report.md); a diagram is never evidence
by itself.

Local PNG snapshots, when present, are inherited editorial artifacts. Some
contain superseded project identifiers, node sizes, namespaces, or replica
counts. They are not canonical architecture or evidence and should not be
published until regenerated from current configuration. The root README
therefore uses an accurate Mermaid diagram instead.
