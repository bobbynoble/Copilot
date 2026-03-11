# CLAUDE.md

This file provides guidance to AI assistants (Claude and others) working in this repository.

## Repository Status

This repository is in initial setup. No source code, configuration, or dependencies have been committed yet. This file serves as a foundation for conventions and workflows that should be followed as the project develops.

## Repository Overview

**Name:** Copilot
**Owner:** bobbynoble
**Branch Convention:** Feature branches use the format `claude/<description>-<session-id>`

## Project Setup (To Be Established)

When initializing this project, update this file with:

- **Language / Runtime:** (e.g., TypeScript/Node.js, Python, Go)
- **Framework:** (e.g., Next.js, FastAPI, Express)
- **Package Manager:** (e.g., npm, yarn, pnpm, pip, cargo)
- **Database:** (e.g., PostgreSQL, SQLite, MongoDB)

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

## Common Commands (Update When Project Is Set Up)

```bash
# Install dependencies
<install command>

# Start development server
<dev command>

# Build for production
<build command>

# Run linter
<lint command>

# Format code
<format command>

# Run type checker
<typecheck command>
```

## Environment Setup

When environment variables are required:

1. Copy `.env.example` to `.env.local` (never commit `.env.local`)
2. Fill in required values
3. Document all variables in `.env.example` with descriptions but no real values

## Directory Structure (To Be Defined)

Update this section when the project structure is established. A typical structure might look like:

```
/
├── src/              # Source code
│   ├── components/   # UI components (if applicable)
│   ├── lib/          # Shared utilities and helpers
│   ├── api/          # API routes or service layer
│   └── types/        # Type definitions
├── tests/            # Test files (or co-located *.test.* files)
├── docs/             # Documentation
├── .github/          # GitHub Actions workflows
├── package.json      # Dependencies and scripts
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
