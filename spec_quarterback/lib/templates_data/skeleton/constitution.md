# [Project Name] — Constitution / Steering

## Product Vision
[1-3 sentences: what problem does this product solve, for whom, and why it matters]

## Tech Stack
- Runtime: [e.g., Node.js 22, Python 3.12]
- Framework: [e.g., React 18 + TypeScript, FastAPI]
- Database: [e.g., PostgreSQL 16 + Redis 7]
- Infra: [e.g., Vercel + Supabase + Docker]
- Key dependencies: [list with pinned versions]

## Architecture Principles
[e.g., "DDD bounded contexts", "event-driven", "API-first", "monorepo"]

## Coding Standards
- Style guide: [link or inline rules]
- Naming conventions: [examples]
- Test coverage floor: [e.g., 80% on services]
- [Include one real code snippet that exemplifies the style]

## Project Structure
src/          → Application code
tests/        → Unit and integration tests
specs/        → All spec artifacts
docs/         → Documentation

## Commands
- Build:  [e.g., `npm run build`]
- Test:   [e.g., `npm test -- --coverage`]
- Lint:   [e.g., `npm run lint --fix`]
- Dev:    [e.g., `docker compose up`]

## Boundaries (Three-Tier System)
✅ Always:   [e.g., run tests before commits, log errors, follow naming conventions]
⚠️ Ask first: [e.g., change DB schema, add new dependency, modify CI config]
🚫 Never:    [e.g., commit secrets, edit node_modules/, remove failing tests without approval]

## Git Workflow
- Branch: [e.g., `feat/[spec-id]-[slug]`]
- Commits: [e.g., Conventional Commits — `feat:`, `fix:`, `chore:`]
- PR: [e.g., squash merge, minimum 1 reviewer]