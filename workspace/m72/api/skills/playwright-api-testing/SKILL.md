---
name: playwright-api-testing
description: Use when writing Playwright TypeScript test scripts for REST API testing. Covers the request fixture, assertions, file structure, and multi-step system test conventions.
version: 1.0.0
---

# Playwright TypeScript for API Testing

## Overview

Write complete, executable `.spec.ts` files using `@playwright/test`. Every
script must be syntactically valid, runnable standalone, and include proper
assertions for status codes, headers, and response bodies.

## File Structure

```typescript
import { test, expect } from '@playwright/test';

test.describe('Operation / Scenario Group', () => {
  test('specific scenario name', async ({ request }) => {
    // Arrange — prepare request params/body
    // Act — send the request
    const response = await request.get('/api/path');
    // Assert — verify response
    expect(response.status()).toBe(200);
  });
});
```

**Do NOT** wrap the output in markdown code fences. Output raw TypeScript.

## The `request` Fixture

Always use Playwright's built-in `request` fixture for API calls. Never use
`fetch`, `axios`, or other HTTP clients.

**Base URL:** Set it once via `test.use({ baseURL: 'https://api.example.com' })`
at the top of the file:

```typescript
test.use({ baseURL: 'https://api.example.com' });
```

## Assertions

### Status Codes

```typescript
expect(response.status()).toBe(200);
expect(response.status()).toBe(404);
```

### Headers

```typescript
expect(response.headers()['content-type']).toContain('application/json');
```

### Response Body (JSON)

```typescript
const body = await response.json();
expect(body).toHaveProperty('id');
expect(body.id).toBeGreaterThan(0);
expect(body.name).toBe('expected value');
expect(Array.isArray(body)).toBe(true);
expect(body.length).toBeGreaterThan(0);
```

### Soft Assertions

Use `expect.soft` when multiple checks should all run even if one fails:

```typescript
expect.soft(response.status()).toBe(200);
expect.soft(body).toHaveProperty('name');
expect.soft(typeof body.name).toBe('string');
```

## Request Methods

```typescript
// GET
const res = await request.get('/api/pets');

// POST with JSON body
const res = await request.post('/api/pets', {
  data: { name: 'Rex', status: 'available' }
});

// PUT
const res = await request.put('/api/pets/1', {
  data: { name: 'Rex', status: 'sold' }
});

// DELETE
const res = await request.delete('/api/pets/1');

// With query parameters
const res = await request.get('/api/pets', {
  params: { status: 'available' }
});

// With headers
const res = await request.get('/api/pets', {
  headers: { 'Authorization': 'Bearer token' }
});
```

## Multi-Step System Tests

For cross-operation scenarios, use `test.step` to label each API call in the
sequence. Extract data from responses and pass to subsequent calls:

```typescript
test('create → read → delete workflow', async ({ request }) => {
  let petId: number;

  await test.step('POST — create pet', async () => {
    const res = await request.post('/api/pets', {
      data: { name: 'Fluffy', status: 'available' }
    });
    expect(res.status()).toBe(201);
    const body = await res.json();
    petId = body.id;
  });

  await test.step('GET — read created pet', async () => {
    const res = await request.get(`/api/pets/${petId}`);
    expect(res.status()).toBe(200);
  });

  await test.step('DELETE — remove pet', async () => {
    const res = await request.delete(`/api/pets/${petId}`);
    expect(res.status()).toBe(204);
  });
});
```

## Saving Scripts

Save each script to a `.spec.ts` file using `write_file`. Name files
descriptively: `unit-pet-get-by-id.spec.ts` or `system-pet-crud-flow.spec.ts`.
