# [Feature/Epic Name] — Tasks
Spec ID: [e.g., 007]

---

## Implementation Order & Dependency Map
[Brief note on sequencing: what must be built first to unblock parallel work]

## Tasks

### Phase 1: Foundation
- [ ] T-01: [Task title] — REQ: US-01 — Est: [S/M/L]
  - Implement: [one-line description of exact code/file changes]
  - Done when: [verifiable condition — e.g., "unit test T-01 passes"]

- [ ] T-02: [Task title] — REQ: US-01 — Est: [S/M/L]
  - Implement: ...
  - Done when: ...

### Phase 2: Core Logic
- [ ] T-03: ... (depends on T-01)
- [ ] T-04: ... (depends on T-01, T-02)

### Phase 3: Integration & Edge Cases
- [ ] T-05: Handle EC-01 (file > 10MB validation)
- [ ] T-06: Handle EC-03 (retry with idempotency key)

### Phase 4: Testing
- [ ] T-07: Write unit tests for [Component A] (covers US-01 AC-1, AC-2)
- [ ] T-08: Write integration test for [full upload flow]
- [ ] T-09: Write edge case tests (EC-01 through EC-04)

---

## Verification Checklist
[The final gate before this spec is closed — maps back to requirements.md]
- [ ] All acceptance criteria in US-01 through US-N are passing
- [ ] All edge cases EC-01 through EC-N are handled and tested
- [ ] All NFRs (performance, security, accessibility) verified
- [ ] No open questions in requirements.md
- [ ] constitution.md boundaries not violated
- [ ] No new tech debt introduced without a tracked item