#!/usr/bin/env python3
"""Fetch a completed paper_05 compact CSS/Steane IBM Runtime job."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from submit_ibm_repetition_sampler import extract_counts, load_credentials, load_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission-json", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--credentials-file", default="")
    parser.add_argument("--result-timeout", type=float, default=300.0)
    parser.add_argument("--status-only", action="store_true")
    return parser.parse_args()


def job_status_value(job: Any) -> str:
    value = getattr(job, "status", "")
    if callable(value):
        value = value()
    return str(value)


def main() -> int:
    args = parse_args()
    submission_path = Path(args.submission_json)
    with submission_path.open("r", encoding="utf-8") as f:
        submission = json.load(f)

    creds = load_credentials(args.credentials_file)
    token = (
        os.environ.get("IBM_QUANTUM_TOKEN")
        or os.environ.get("QISKIT_IBM_TOKEN")
        or creds.get("token", "")
        or creds.get("ibm_quantum_token", "")
    )
    instance = os.environ.get("IBM_QUANTUM_INSTANCE", "") or creds.get("instance", "")
    channel = os.environ.get("IBM_QUANTUM_CHANNEL", "") or creds.get("channel", "") or "ibm_quantum_platform"
    service = load_service(instance, token, channel)

    job_id = str(submission["job_id"])
    job = service.job(job_id)
    status = job_status_value(job)
    print(f"Fetched IBM Runtime compact CSS/Steane job {job_id}; status={status}")
    if args.status_only:
        return 0

    result = job.result(timeout=args.result_timeout)
    experiments: list[dict[str, Any]] = []
    for meta, pub_result in zip(submission.get("experiments", []), result):
        experiments.append({**meta, "counts": dict(sorted(extract_counts(pub_result).items()))})

    payload = {
        "schema": "paper05_css_ldpc_results_v1",
        "source": "ibm_runtime",
        "backend": submission.get("backend", ""),
        "job_id": job_id,
        "shots": int(submission.get("shots", 0)),
        "code_family": "css_ldpc",
        "code_name": "steane_z_checks",
        "n_data": int(submission.get("n_data", 0)),
        "n_checks": int(submission.get("n_checks", 0)),
        "optimization_level": submission.get("optimization_level", ""),
        "experiments": experiments,
    }
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    print(f"Wrote IBM Runtime compact CSS/Steane result payload to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
