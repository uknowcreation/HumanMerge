# PR Review Agent

An open-source, provider-neutral pull request review agent with mandatory human approval.

The initial milestone is intentionally small: configure a frontend or backend reviewer,
decide whether a pull request is eligible, and produce structured comment proposals. It
does not publish anything to GitHub.

## Product invariants

- Never review the current user's own pull requests.
- Never review drafts or closed pull requests.
- Route reviews using repository labels.
- Treat pull request content as untrusted input.
- Never expose model or MCP credentials to pull request code.
- Never publish a review without a separate human-approved operation.

## Try the setup wizard

Python 3.11 or newer is recommended. Install the project first so its interactive prompt
dependency is available:

```bash
uv sync
```

```bash
uv run pr-review-agent
```

The command creates `.pr-review-agent.yml` in the current directory. It stores model
configuration, never credentials. Menus use the up/down arrow keys and Enter. Questions
are conditional: choosing frontend does not ask for a backend label, and every label can
be replaced with a custom value.

The setup order is deliberate:

1. Check the existing GitHub CLI session, or offer browser login when it is missing.
2. Select a personal account or organization.
3. Select one or more accessible repositories.
4. Scan repository languages and labels using read-only GitHub calls.
5. Choose the reviewer and confirm the preselected languages.
6. Choose a repository label, after language selection.
7. Choose how reviews will run, connect the account when needed, and select a detected model.

GitHub credentials remain managed by GitHub CLI and are never copied into the project
configuration.

## Model execution modes

The wizard says **execution mode** instead of mixing up two different concepts:

- A provider operates models: OpenAI or Anthropic.
- A harness runs an agent: Codex CLI, Claude Code, or this Python application through an API.

The currently supported modes are:

- **Codex CLI / ChatGPT subscription**: reuses the official local Codex login and reads its
  account-aware model catalog.
- **Claude Code / Claude subscription**: reuses the official Claude Code login. Claude Code does
  not expose a public model-list command, so the wizard offers its stable aliases; Claude resolves
  the selected alias for the signed-in account when a review runs.
- **OpenAI API**: reads `OPENAI_API_KEY` and requests the models visible to that API project.
- **Anthropic API**: reads `ANTHROPIC_API_KEY` and requests the models visible to that API account.
- **OpenAI-compatible API**: reads `OPENAI_COMPATIBLE_BASE_URL` and
  `OPENAI_COMPATIBLE_API_KEY`, then requests the server's model list.
- **Ollama**: reads the models already installed on the local Ollama server.

No login token or API key is written to `.pr-review-agent.yml`. API keys must be supplied through
environment variables locally and through GitHub Actions secrets in CI.

## Run the tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Roadmap

1. Configuration wizard and deterministic policy.
2. Read-only GitHub adapter and fixture-based PR review.
3. Provider interface and one model implementation.
4. Frontend review rubric and structured findings.
5. Duplicate detection against existing bot reviews.
6. GitHub Action producing a review artifact.
7. Separate human-approved publishing workflow.
8. Optional MCP and additional model providers.

See [`docs/architecture.md`](docs/architecture.md) for the trust boundaries.
