# CEO Mandate: AAO Self Development

| Field | Value |
|---|---|
| Identifier | `CEO-MANDATE-AAO-SELF-DEV-20261019` |
| Version | `1.0` |
| Mandate title | `AAO — Self Development` |
| Authority | CEO |
| Confirmation date | 2026-10-19 |
| Project | AAO — Self Development |
| Status | **CONFIRMED** |

## Decision and objective

The CEO expressly confirmed this strategic mandate on 2026-10-19. Its objective
is to build the minimum functional core that lets AAO manage, develop, test,
audit, and improve its own software as its first managed project. The deliverable
includes both the autonomous backend and AAO Control Center.

This record formalizes the supplied CEO decision. It is not evidence that the
mandate or project has been persisted in a PostgreSQL instance; the persistence
record and event identifiers must be verified separately through the authorized
development API.

## Success criteria

AAO is technically ready for initial use only when it demonstrates an authentic,
small and useful change to AAO through this traceable path:

`AAO -> project -> objective -> task -> executing agent -> bounded execution ->
tests -> independent audit -> PR -> result`.

The project web application must present the same real backend state, provenance,
and status. Endpoints, isolated tests, mock data, or documents alone do not meet
this criterion.

## Scope

Within approved controls, work may implement and operate:

- The minimum backend for authorized objectives, planning, tasks, assignments,
  bounded execution, verification, audit, PR preparation, and durable status.
- AAO Control Center views for organization, the AAO project, tasks, activity,
  evidence, audits, PRs, and reserved decisions, backed by the same real state.
- Small improvements to AAO itself as authentic project work.

## Delegated technical authority

Engineering agents may inspect, implement, test, refactor, prepare PRs, and
operate existing development mechanisms within their already granted identities,
project grants, resource limits, and sandbox controls. The mandate authorizes
the project objective; it does not itself issue credentials or project grants.

## Reserved matters and restrictions

This mandate grants no new execution permission. It does not authorize production
deployment, arbitrary tools or commands, model/provider activation, external
effects, privileged database access, bypass of authentication or review, critical
PR merges, expansion of constitutional powers, or acceptance of high residual
risk. Existing CEO-reserved strategic, constitutional, budgetary, irreversible,
and high-risk decisions remain reserved. The CEO does not perform routine
technical merges; agents may promote only when the applicable autonomous
conformity and authorization controls are demonstrated and satisfied.

Execution is restricted to explicitly authorized development resources and
isolated environments. Do not expose credentials or exceed allocated resources.

## Acceptance boundaries

Keep documentary decision, PostgreSQL persistence, technical verification,
independent audit, risk acceptance, and operational authorization distinct.
Do not declare the mandate MVP complete until the authentic end-to-end path is
observable in AAO Control Center and its execution, test, audit, and PR evidence
is verifiable at exact revisions.

## Decision provenance

Source: the CEO-confirmed directive titled **“AAO — Mandato CEO confirmado:
primer proyecto AAO Self Development”**, dated 2026-10-19 and supplied in the
project continuity context. The runtime mandate/project identifiers and
confirmation/creation event identifiers below were subsequently read from the
authorized development API; they are runtime evidence, not inferred from this
documentary decision.

## Development-instance persistence record

The following state was verified through the authorized development APIs on
2026-10-19. The API was served on loopback at `http://127.0.0.1:8001`; its
readiness route reported PostgreSQL available. The mandate inventory was read
using the configured development CEO authorization, without printing or
persisting the credential. The associated project list was independently
visible to the existing individual AGENT identity through its scoped API.

| Record | Identifier / evidence |
|---|---|
| Confirmed mandate | `65563e55-eb01-4cd6-a5cc-778acc55d2af` |
| Mandate state | `CONFIRMED` |
| Persisted objective | Matches the bootstrap's canonical AAO Self Development objective, including the authentic shared-backend-state requirement. |
| Confirmation event | `db96571d-c9f5-49c1-acac-02377ec26bec` (`mandate.confirmed`, `2026-10-19T17:35:02.16918+00:00`) |
| Active project | `9d17d6c1-d644-424a-a425-fe7e084c3d91`, `AAO — Self Development` |
| Project creation event | `b92790c1-e3ab-424e-b3db-014deebdc114` (`project.created`, `2026-10-19T17:35:02.181103+00:00`) |

This is persistence evidence for the local development instance only. It is not
production state, proof of end-to-end MVP acceptance, independent audit, or
authorization to expand execution. Project registration remains distinct from
provisioning or validating identities and grants.

## Adenda 1 (2026-10-26): objetivo final

**Autoridad:** CEO. **Decisión:** [`CEO-DEC-ENTERPRISE-MODEL-2026-10-26`](decisions/CEO-DEC-ENTERPRISE-MODEL-2026-10-26.md).

1. **Objetivo final.** El objetivo final de este mandato es que AAO funcione como **empresa autónoma de ingeniería de software** conforme a [`AAO_ENTERPRISE_OPERATING_MODEL.md`](architecture/AAO_ENTERPRISE_OPERATING_MODEL.md), con las decisiones D-01 a D-10 y las condiciones de la decisión citada.
2. **Primer hito.** El criterio de éxito de la sección *Success criteria* se mantiene como **primer hito** del mandato.
3. **Criterio de éxito final.** El mandato se considerará cumplido cuando se satisfagan, con evidencia reproducible sobre revisiones exactas:
   - los gates de las fases 0 a 5;
   - el piloto del §14;
   - los 15 escenarios del §19.
4. **Traspaso.** Se rige por el §4 de la decisión citada.
5. **Sin nuevas facultades.** Esta adenda no modifica las secciones *Reserved matters and restrictions* ni *Acceptance boundaries*, ni concede permisos, grants, activaciones o delegaciones.
