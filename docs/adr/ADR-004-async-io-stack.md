# ADR-004: Use asynchronous I/O for API and persistence

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS §18.1, §10.4

## Context

The system is I/O-heavy: PostgreSQL, Redis, payment APIs, email, storage, scanning, and downloads. The approved stack selects FastAPI, SQLAlchemy 2 async and arq.

## Decision

Use async FastAPI handlers and SQLAlchemy 2 async. Async-capable external adapters expose async interfaces. Blocking/CPU-heavy work must not run directly on the event loop. STL bytes are transferred by nginx after API authorization, not streamed through FastAPI.

## Consequences

+ Efficient concurrency for I/O workloads
+ Matches the approved stack
+ Keeps large binary transfer out of Python request workers
- Hidden blocking calls can damage the whole event loop
- Some libraries need worker/thread adaptation

## Alternatives rejected

- **Fully synchronous stack** — Conflicts with the approved async stack and expected I/O profile.
- **Stream STL through FastAPI** — Would consume application capacity during large transfers.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
