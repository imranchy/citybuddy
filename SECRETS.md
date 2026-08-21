# CityBuddy secret management

CityBuddy keeps real credentials outside version control.

## Local development

Use `backend/.env` for local environment values. It is ignored by Git. The tracked `backend/.env.example` contains names and safe defaults only.

Sensitive values currently used by the project:

- `POSTGRES_PASSWORD` and/or credentials embedded in `DATABASE_URL`
- `VLLM_API_KEY`
- `LANGSMITH_API_KEY` when optional LangSmith tracing is used
- Azure Static Web Apps deployment token (kept in GitHub Actions Secrets, not in `backend/.env`)
- GitHub-provided `GITHUB_TOKEN` (managed automatically by GitHub Actions)

Configuration values that are not secrets but are useful to keep alongside the local environment include `VLLM_BASE_URL`, model names, Ollama URLs, RAG settings, and database host/name settings.

## Production

Keep production values in the platform secret stores:

- Render environment variables: `DATABASE_URL`, `VLLM_API_KEY`, `VLLM_BASE_URL`, model/RAG configuration.
- GitHub Actions Secrets: Azure Static Web Apps deployment token.

Do not copy production credentials into tracked files, workflow YAML, documentation, tests, issues, commit messages, or screenshots.

## vLLM key

The existing vLLM API key is stored outside the repository in WSL at `~/.config/citybuddy/vllm_api_key`. It can be copied into the ignored `backend/.env` when local Windows-side tooling needs the same key. Do not print the key to the terminal or chat.

The current vLLM key was displayed during earlier debugging, so rotate it after deployment is stable and update both the local secret store and Render.

## Before every push

Run a secret scan and inspect `git diff --cached`. Never commit `backend/.env`, `.secrets/`, private keys, database URLs containing passwords, or API tokens.
