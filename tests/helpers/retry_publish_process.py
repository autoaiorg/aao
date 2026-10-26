"""One-shot child process used to verify W2 retry after the caller exits."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def _state(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {"pull_requests": {}}


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=("push", "open"), required=True)
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()

    from aao.pr_publisher import PublishError, open_pull_request, push_candidate

    store = Path(args.store)
    remote = Path(args.remote)
    state_path = Path(args.state)

    def push(sha: str, branch: str) -> None:
        state = _state(state_path)
        state["push_attempts"] = state.get("push_attempts", 0) + 1
        _save_state(state_path, state)
        subprocess.run(
            ["git", "--git-dir", str(store), "push", "-q", str(remote), f"{sha}:refs/heads/{branch}"],
            check=True,
        )

    def open_pr(branch: str, title: str, body: str) -> dict:
        state = _state(state_path)
        pull_requests = state.setdefault("pull_requests", {})
        head = subprocess.run(
            ["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if branch in pull_requests:
            return {**pull_requests[branch], "head_sha": head}

        result = {
            "number": 7 + len(pull_requests),
            "url": f"https://github.invalid/autoaiorg/aao/pull/{7 + len(pull_requests)}",
            "head_sha": head,
            "title": title,
            "body": body,
        }
        pull_requests[branch] = result
        state["pr_attempts"] = state.get("pr_attempts", 0) + 1
        _save_state(state_path, state)
        if not state.get("pr_response_lost"):
            state["pr_response_lost"] = True
            _save_state(state_path, state)
            raise TimeoutError("PR response lost after remote acceptance")
        return result

    token = os.environ["AAO_TEST_RETRY_PUBLISHER_CREDENTIAL"]
    try:
        result = (push_candidate(args.work_id, token, store=store, push=push) if args.step == "push"
                  else open_pull_request(args.work_id, token, open_pr=open_pr))
    except PublishError as exc:
        print(json.dumps({"pid": os.getpid(), "status": "ERROR", "message": str(exc)}))
        return 1
    print(json.dumps({**result, "pid": os.getpid()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
