#!/usr/bin/env python3
"""Submit paper_05 compact CSS/Steane syndrome circuits to IBM Runtime Sampler."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from css_ldpc_syndrome import build_qiskit_circuit, circuit_metadata, experiment_specs, n_checks, n_data
from submit_ibm_repetition_sampler import (
    choose_backend,
    extract_counts,
    job_id_value,
    load_credentials,
    load_service,
    sampler_class,
    transpile_for_backend,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--targets", default="all")
    parser.add_argument("--shots", type=int, default=256)
    parser.add_argument("--backend", default="", help="IBM backend name. If omitted, least-busy hardware is selected.")
    parser.add_argument("--instance", default="", help="Optional IBM Quantum instance/hub/group/project.")
    parser.add_argument("--credentials-file", default="")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--result-timeout", type=float, default=900.0)
    parser.add_argument("--optimization-level", type=int, default=1)
    return parser.parse_args()


def write_submission(
    path: Path,
    *,
    backend_name: str,
    job_id: str,
    shots: int,
    optimization_level: int,
    status: str,
    experiments: list[dict[str, Any]],
) -> None:
    payload = {
        "schema": "paper05_css_ldpc_ibm_submission_v1",
        "source": "ibm_runtime",
        "backend": backend_name,
        "job_id": job_id,
        "shots": shots,
        "code_family": "css_ldpc",
        "code_name": "steane_z_checks",
        "n_data": n_data(),
        "n_checks": n_checks(),
        "optimization_level": optimization_level,
        "status": status,
        "experiments": experiments,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def main() -> int:
    args = parse_args()
    if args.shots <= 0:
        raise SystemExit("Error: --shots must be positive.")

    creds = load_credentials(args.credentials_file)
    token = (
        os.environ.get("IBM_QUANTUM_TOKEN")
        or os.environ.get("QISKIT_IBM_TOKEN")
        or creds.get("token", "")
        or creds.get("ibm_quantum_token", "")
    )
    instance = args.instance or os.environ.get("IBM_QUANTUM_INSTANCE", "") or creds.get("instance", "")
    channel = os.environ.get("IBM_QUANTUM_CHANNEL", "") or creds.get("channel", "") or "ibm_quantum_platform"
    backend_name_arg = args.backend or creds.get("backend", "")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = experiment_specs(args.targets)
    circuits = [build_qiskit_circuit(spec) for spec in specs]
    experiment_metadata = [circuit_metadata(spec) for spec in specs]

    service = load_service(instance, token, channel)
    backend = choose_backend(service, backend_name_arg, min_qubits=n_data() + n_checks())
    backend_name = getattr(backend, "name", None)
    if callable(backend_name):
        backend_name = backend_name()
    backend_name = str(backend_name or backend)

    isa_circuits = transpile_for_backend(circuits, backend, args.optimization_level)
    Sampler = sampler_class()
    sampler = Sampler(backend)
    job = sampler.run(isa_circuits, shots=args.shots)
    job_id = job_id_value(job)
    submission_path = out_dir / "ibm_css_ldpc_submission.json"
    write_submission(
        submission_path,
        backend_name=backend_name,
        job_id=job_id,
        shots=args.shots,
        optimization_level=args.optimization_level,
        status="submitted",
        experiments=experiment_metadata,
    )
    print(f"Submitted IBM Runtime compact CSS/Steane job {job_id} on {backend_name}; wrote {submission_path}")

    if args.no_wait:
        print("Not waiting for results because --no-wait was set.")
        return 0

    try:
        result = job.result(timeout=args.result_timeout)
    except TypeError:
        result = job.result()

    experiments: list[dict[str, Any]] = []
    for spec, pub_result in zip(specs, result):
        experiments.append({**circuit_metadata(spec), "counts": dict(sorted(extract_counts(pub_result).items()))})

    payload = {
        "schema": "paper05_css_ldpc_results_v1",
        "source": "ibm_runtime",
        "backend": backend_name,
        "job_id": job_id,
        "shots": args.shots,
        "code_family": "css_ldpc",
        "code_name": "steane_z_checks",
        "n_data": n_data(),
        "n_checks": n_checks(),
        "optimization_level": args.optimization_level,
        "experiments": experiments,
    }
    out_path = out_dir / "ibm_css_ldpc_results.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    print(f"Wrote IBM Runtime compact CSS/Steane results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
