
# BridgOps Architecture Decisions

This document records important technical decisions, their reasoning, and known tradeoffs.

## ADR-001: Modular Backend Before Microservices

Status: Accepted

Decision:
Start with one modular FastAPI backend.

Reasons:
- Faster local development
- Easier debugging
- Simpler deployment
- Clear separation between API, services, and models
- Lower resource consumption

Tradeoff:
Modules are not independently deployable.

We will introduce separate workers and services when asynchronous processing and integration workloads justify them.

## ADR-002: PostgreSQL as Primary Database

Status: Accepted

Decision:
Use PostgreSQL for persistent application data.

Reasons:
- Relational business data
- Transaction support
- Constraints and indexing
- Strong SQL support
- Compatibility with SQLAlchemy and Alembic

Tradeoff:
Schema changes require planning and migrations.

## ADR-003: Shared Database for Multi-Tenancy

Status: Accepted for initial architecture

Decision:
Use one PostgreSQL database for multiple businesses.

Reasons:
- Lower operational complexity
- Lower infrastructure cost
- Simpler local development

Tradeoff:
Application code must enforce strict tenant ownership and authorization.

Current limitation:
Tenant-level authorization has not been implemented.

Potential future improvement:
PostgreSQL Row-Level Security.

## ADR-004: React with TypeScript

Status: Accepted

Decision:
Use React, TypeScript, and Vite for the frontend.

Reasons:
- Typed API contracts
- Reusable components
- Maintainable frontend code
- Fast development workflow

Tradeoff:
Additional type definitions and configuration compared with JavaScript.

## ADR-005: Docker Compose for Local Infrastructure

Status: Accepted

Decision:
Use Docker Compose for PostgreSQL and future local infrastructure services.

Reasons:
- Reproducible local services
- No separate PostgreSQL installation required
- Persistent Docker volumes
- Low cloud costs

Tradeoff:
Local Docker behavior is not identical to production infrastructure.

## ADR-006: Alembic for Database Migrations

Status: Accepted

Decision:
Manage PostgreSQL schema changes through Alembic.

Reasons:
- Version-controlled schema changes
- Repeatable database setup
- Clear migration history
- Compatibility with SQLAlchemy

Tradeoff:
Generated migrations require developer review.

## ADR-007: Introduce CI Early

Status: Accepted

Decision:
Add GitHub Actions during Stage 1 instead of waiting until Stage 8.

Reasons:
- Detect errors early
- Validate changes automatically
- Establish repeatable engineering practices
- Prepare the repository for future collaboration

Current scope:
Backend pytest and frontend test, lint, and build checks.

Future improvements:
Backend linting, PostgreSQL integration tests, migration validation, and deployment checks.

## ADR-008: Delay Kafka Until Order Workflows Exist

Status: Accepted

Decision:
Implement synchronous order processing before introducing Kafka.

Reasons:
- Validate business rules first
- Understand actual asynchronous requirements
- Avoid unnecessary infrastructure
- Simplify initial debugging

Tradeoff:
Initial operations will not benefit from asynchronous decoupling.

Kafka will be introduced when event-driven workflow processing is implemented.
