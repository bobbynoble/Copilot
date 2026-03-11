# CLAUDE.md

This file provides guidance to AI assistants (Claude and others) working in this repository.

## Repository Status

Active development. This repository contains an RFP Analysis Agent — a Claude-powered REST API for scoring and analysing RFP responses, compatible with Microsoft Copilot Studio.

## Repository Overview

**Name:** Copilot
**Owner:** bobbynoble
**Branch Convention:** Feature branches use the format `claude/<description>-<session-id>`

## Project Setup

- **Language / Runtime:** Python 3.11+
- **Framework:** FastAPI + Uvicorn
- **Package Manager:** pip (`requirements.txt`)
- **AI Model:** Claude Opus 4.6 via Anthropic Python SDK
- **Database:** None (stateless API)

## Development Workflow

### Branch Strategy

- **Main branch:** `main` (or `master`) — protected, no direct pushes
- **Feature branches:** `claude/<feature-description>-<session-id>` for AI-assisted work
- **Human feature branches:** `feature/<description>` or `<username>/<description>`
- Always create a new branch for changes; never commit directly to `main`

### Commit Conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

<optional body>

<optional footer>
```

**Types:**
- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation changes only
- `style` — formatting, missing semicolons (no logic change)
- `refactor` — code restructuring (no feature/fix)
- `test` — adding or updating tests
- `chore` — build process, dependency updates, tooling

**Examples:**
```
feat(auth): add OAuth2 login flow
fix(api): handle null response from upstream service
docs: update README with setup instructions
```

### Pull Requests

- Keep PRs focused and small (one logical change per PR)
- Include a clear description of what changed and why
- Reference any related issues: `Closes #123`
- Ensure all checks pass before requesting review

## Code Quality Standards

### General Principles

- **Simplicity first:** Write the minimum code needed to solve the problem
- **No premature abstractions:** Don't create helpers/utilities for one-time use
- **No speculative features:** Only implement what is currently needed
- **Avoid backwards-compat hacks:** Remove unused code instead of commenting it out
- **No unnecessary comments:** Only add comments where logic is non-obvious

### Security

- Never commit secrets, API keys, or credentials — use environment variables
- Validate all user input at system boundaries
- Sanitize output to prevent XSS/injection attacks
- Use parameterized queries for database operations
- Follow the principle of least privilege for permissions

### Error Handling

- Only add error handling for scenarios that can actually occur
- Trust framework and internal code guarantees; validate at system boundaries
- Propagate errors with sufficient context for debugging

## Testing

When a test framework is established, document here:

- **Test runner:** (e.g., Jest, Vitest, pytest, go test)
- **Coverage target:** (e.g., 80%+ line coverage)
- **Test file convention:** (e.g., `*.test.ts` co-located with source, or `tests/` directory)

**Commands to run (update when project is set up):**
```bash
# Run all tests
<command>

# Run tests in watch mode
<command>

# Run with coverage
<command>
```

Always run tests before committing. Fix failures before pushing.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start development server (auto-reload)
uvicorn src.main:app --reload --port 8000

# Start production server
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4

# View interactive API docs
open http://localhost:8000/docs

# Download OpenAPI spec (for Copilot Studio import)
curl http://localhost:8000/openapi.json -o openapi.json
```

## Environment Setup

1. Copy `.env.example` to `.env` (never commit `.env`)
2. Set `ANTHROPIC_API_KEY` — required
3. Set `RFP_API_KEY` — optional; when set, callers must send `X-API-Key: <value>`
4. Set `CORS_ORIGINS` — optional; defaults to `*`

## Directory Structure

```
/
├── src/
│   ├── __init__.py
│   ├── main.py       # FastAPI app — routes, CORS, auth middleware
│   ├── agent.py      # Claude Opus 4.6 RFP analysis logic
│   └── models.py     # Pydantic request/response schemas
├── requirements.txt
├── .env.example      # Environment variable template
└── CLAUDE.md         # This file
```

## AI Assistant Guidelines

### When Making Changes

1. **Read before editing:** Always read the relevant files before modifying them
2. **Understand context:** Review related code to understand patterns and conventions
3. **Minimal changes:** Make only the changes necessary for the task
4. **No scope creep:** Don't refactor or "improve" code that wasn't part of the request
5. **Test your work:** Run tests and linters after making changes

### What to Avoid

- Adding docstrings/comments to code you didn't change
- Introducing new dependencies without explicit need
- Over-engineering with abstractions for single-use cases
- Adding error handling for impossible scenarios
- Creating backwards-compatibility shims for removed code

### Git Operations

- Develop on the designated feature branch
- Use descriptive commit messages following the convention above
- Push to `origin <branch-name>` using `-u` flag
- Never force-push to shared branches

## Updating This File

This CLAUDE.md should be updated as the project evolves:

- When a tech stack is chosen, fill in the relevant sections
- When conventions are established, document them here
- When new tooling is added, update the commands section
- Keep this file accurate — outdated guidance is worse than no guidance
