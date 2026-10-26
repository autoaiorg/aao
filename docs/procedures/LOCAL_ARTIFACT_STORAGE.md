# Local AAO artifact storage

Use XDG directories rather than creating `aao-*` files at the top level of a user's home:

- **Recoverable session/run state and logs:** `${XDG_STATE_HOME:-$HOME/.local/state}/aao/`.
- **Evidence, reports, exports, and backups that must survive between runs:** `${XDG_DATA_HOME:-$HOME/.local/share}/aao/`.

Within either root, group artifacts by purpose and UTC date/run ID. Directories containing audit or identity evidence must be private (`0700`) and files private (`0600`) unless a documented consumer requires narrower sharing. Reject relative XDG overrides; do not silently fall back to a different path after an invalid override.

Historical references are provenance, not instructions to recreate the old home-root layout. When migrating an existing artifact, keep its bytes unchanged, record source and destination paths plus SHA-256 (tree digest for directories), and retain the original checksum files. Do not delete evidence based on age or size alone. A migration must be reversible and must not grant a role account additional access to another identity's evidence.

The standard XDG layout for current producers is:

| Artifact | Destination |
|---|---|
| CEO session transcript/source checkout | `state/aao/sessions/YYYY/MM/<timestamp-id>/` |
| Trial and trust-root execution logs | `state/aao/runs/<purpose>/` |
| Audit reports and attestations | `share/aao/evidence/audits/<revision>[-prompt]/` |
| Trial evidence and setup records | `share/aao/evidence/trials/<purpose>/YYYY/MM/...` |
| Identity-separation evidence | `share/aao/evidence/identity-separation/YYYY/MM/<run-id>/` |
| Archived trial bundles | `share/aao/evidence/trials/archives/YYYY/MM/` |

See the host-specific, non-repository migration manifest under `~/.local/state/aao/home-artifact-migration/` for any already-existing artifacts and their path references. It intentionally stays outside the repository because it inventories a user's private host files.
