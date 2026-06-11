# [Feature/Epic Name] — Technical Design
Spec ID: [e.g., 007]
Status: [Draft | Reviewed | Approved]

---

## 1. Architecture Overview
[Narrative: how does this feature fit into the existing system?]
[Include a sequence diagram, component diagram, or ASCII diagram if helpful]

## 2. Component Design
### [Component A]
- Responsibility: [single sentence]
- Interface: [key public methods/endpoints]
- Dependencies: [what it consumes]

### [Component B]
- ...

## 3. Data Model
[Define entities, fields, types, relationships, indexes]
[Include migration strategy if altering existing schema]

### Entity: [Name]
| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK, NOT NULL | Primary key |
| ... | ... | ... | ... |

### Relationships
- [Entity A] 1—N [Entity B] via [foreign key]

## 4. API / Interface Contracts
[REST endpoints, GraphQL schema, WebSocket events, message queue payloads]
[Be specific enough that frontend and backend can be developed in parallel]

### Endpoint: POST /[resource]
- Auth: [required/optional, token type]
- Request body: `{ field: type, ... }`
- Response 200: `{ field: type, ... }`
- Response 4xx/5xx: `{ errorCode: string, message: string, details?: object }`

## 5. Error Handling Strategy
[How errors propagate, logging standards, monitoring hooks]

## 6. Security Considerations
[Auth model, input validation, rate limiting, secrets management]

## 7. Technical Decisions & Rationale
[Document key choices and why — future developers (and agents) need this context]
| Decision | Alternative Considered | Reason Chosen |
|---|---|---|
| Use Redis for presence | PostgreSQL polling | Lower latency; disposable data |
| ... | ... | ... |

## 8. Non-Goals (Technical)
[What this design intentionally does NOT address]

## 9. Dependencies & Risks
| Dependency | Risk | Mitigation |
|---|---|---|
| [External API X] | Rate limits | Implement exponential backoff + cache |
| ... | ... | ... |