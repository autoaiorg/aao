#!/usr/bin/env python3
"""Publish one VERIFIED Self Development task as a pull request (W2b).

Run as the publisher (PM) principal. Its AGENT bearer is read only from the private
runtime file $XDG_RUNTIME_DIR/aao-publisher.token. GitHub Apps are configured with
AAO_PUBLISH_BASE_REPO, AAO_PUBLISH_HEAD_REPO, AAO_PUBLISH_PUSH_APP and AAO_PUBLISH_PR_APP;
their keys must be readable by this uid. The API process never sees them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
PUBLISHER_TOKEN_NAME = "aao-publisher.token"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-id", required=True)
    args = parser.parse_args()
    from run_self_development_worker import _read_agent_token

    os.environ.setdefault("AAO_ENV", "development")
    os.environ.setdefault("AAO_ENV_FILE", ".env.local")
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    store = os.environ.get("AAO_CANDIDATE_REPOSITORY") or str(data_home / "aao" / "candidates.git")
    from aao.pr_publisher import github_publisher, publish

    try:
        token = _read_agent_token(PUBLISHER_TOKEN_NAME)
        push, open_pr = github_publisher(store)
        result = publish(args.work_id, token, store=store, push=push, open_pr=open_pr)
    except (RuntimeError, KeyError, ValueError) as exc:  # WorkerError, PublishError, GitHubAuthError
        print(f"Publication did not complete: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
