# Architecture

## Principle

The model may propose an action, but deterministic application code decides whether that
action is allowed. Analysis and publication are separate workflows with separate GitHub
permissions.

## Analysis flow

```text
GitHub event
  -> deterministic PR filter
  -> read-only PR snapshot
  -> reviewer selection from labels
  -> model analysis
  -> schema validation
  -> duplicate and confidence filtering
  -> review.json artifact
```

The analysis workflow has read-only GitHub permissions. Its output always contains
`publish_allowed: false`.

## Publication flow

```text
human selects findings
  -> explicit approval
  -> verify repository, PR and head SHA
  -> publish only selected comments
  -> audit result
```

The publication workflow is the only component with `pull-requests: write`. It never
accepts free-form tool calls from a model.

## Analysis backend boundary

Every model integration implements the same application-owned contract:

```text
review(PRSnapshot, ReviewProfile) -> ReviewResult
```

An analysis backend can be a harness authenticated with a subscription (Codex CLI or Claude Code),
a direct provider API, or a local Ollama runtime. Provider credentials and harness login tokens are
supplied at runtime. They are never written to the public configuration file.

## MCP boundary

MCP support is optional. Servers and allowed tools are explicitly configured. The first
release permits read-only MCP tools only; all returned content is treated as untrusted.
