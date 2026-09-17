#!/usr/bin/env python3
"""Build paper_05 compact CSS/Steane syndrome circuit artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from css_ldpc_syndrome import build_qiskit_circuit, circuit_metadata, experiment_specs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--targets", default="all")
    return parser.parse_args()


def write_qasm(path: Path, circuit: object) -> None:
    try:
        from qiskit import qasm3  # type: ignore

        text = qasm3.dumps(circuit)
    except Exception:
        try:
            text = circuit.qasm()  # type: ignore[attr-defined]
        except Exception:
            text = "// QASM export unavailable in this Qiskit installation.\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    qasm_dir = out_dir / "qasm"
    out_dir.mkdir(parents=True, exist_ok=True)
    qasm_dir.mkdir(parents=True, exist_ok=True)

    specs = experiment_specs(args.targets)
    manifest_rows: list[dict[str, object]] = []
    drawings: list[str] = []

    for spec in specs:
        circuit = build_qiskit_circuit(spec)
        meta = circuit_metadata(spec)
        qasm_path = qasm_dir / f"{spec.circuit_id}.qasm"
        write_qasm(qasm_path, circuit)
        drawings.append(f"=== {spec.circuit_id} ===\n{circuit.draw(output='text', fold=120)}\n")
        manifest_rows.append(
            {
                **meta,
                "n_qubits_total": circuit.num_qubits,
                "n_clbits": circuit.num_clbits,
                "depth": circuit.depth(),
                "qasm_file": str(qasm_path.relative_to(out_dir)),
            }
        )

    with (out_dir / "circuit_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "code_family": "css_ldpc",
                "code_name": "steane_z_checks",
                "targets": args.targets,
                "circuits": manifest_rows,
            },
            f,
            indent=2,
        )
        f.write("\n")

    fields = [
        "circuit_id",
        "label",
        "code_family",
        "code_name",
        "n_data",
        "n_checks",
        "injected_x",
        "expected_syndrome",
        "check_type",
        "n_qubits_total",
        "n_clbits",
        "depth",
        "qasm_file",
    ]
    with (out_dir / "circuit_manifest.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    (out_dir / "circuit_drawings.txt").write_text("\n".join(drawings), encoding="utf-8")
    print(f"Wrote {len(specs)} compact CSS/Steane syndrome circuits to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
