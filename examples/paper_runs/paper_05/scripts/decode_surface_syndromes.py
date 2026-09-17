#!/usr/bin/env python3
"""Decode paper_05 planar surface-check Z-layer syndrome request streams."""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
from pathlib import Path
from typing import Any

from paper05_decoder_policies import decode_policy, parse_decoders, supports_to_check_matrix, syndrome_from_request
from surface_syndrome import build_surface_geometry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--decoders", default="emw,uf_like,bit_flip")
    parser.add_argument("--bit-flip-prior", "--bp-prior", dest="bit_flip_prior", type=float, default=0.08)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    decoders = parse_decoders(args.decoders)
    matrices: dict[int, list[list[int]]] = {}
    csv_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []

    for req_path in sorted(in_dir.glob("decoder_requests_*.ndjson")):
        dataset = req_path.stem.replace("decoder_requests_", "", 1)
        resp_paths = {
            decoder: out_dir / f"decoder_responses_{dataset}_surface_{decoder}.ndjson"
            for decoder in decoders
        }
        line_counts = {decoder: 0 for decoder in decoders}
        with contextlib.ExitStack() as stack:
            req_f = stack.enter_context(req_path.open("r", encoding="utf-8"))
            resp_files = {
                decoder: stack.enter_context(path.open("w", encoding="utf-8"))
                for decoder, path in resp_paths.items()
            }
            for line in req_f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                meta = rec.get("metadata", {})
                distance = int(meta.get("distance", "5"))
                if distance not in matrices:
                    geom = build_surface_geometry(distance)
                    matrices[distance] = supports_to_check_matrix(geom.n_data, geom.z_supports)
                matrix = matrices[distance]
                syndrome = syndrome_from_request(rec)
                injected_raw = meta.get("injected_x", "")
                injected = "" if injected_raw == "" else int(injected_raw)
                for decoder in decoders:
                    result = decode_policy(decoder, matrix, syndrome, prior_p=args.bit_flip_prior)
                    correction = list(result.correction)
                    residual = list(result.residual)
                    if injected != "":
                        exact_match: int | str = int(correction == [injected])
                        contains_target: int | str = int(injected in correction)
                    else:
                        exact_match = int(correction == [])
                        contains_target = exact_match

                    diagnostics = {
                        **result.diagnostics,
                        "code_id": rec.get("code_id", ""),
                        "n_qubits": meta.get("n_data", rec.get("n_qubits", "")),
                        "syndrome": "".join(str(bit) for bit in syndrome),
                        "residual_syndrome": "".join(str(bit) for bit in residual),
                        "correction_weight": str(len(correction)),
                    }
                    response = {
                        "correction": {
                            "qubit_flips": correction,
                            "qubit_flips_x": correction,
                            "qubit_flips_z": [],
                            "confidence": result.confidence,
                            "decoder_name": f"surface_{decoder}",
                        },
                        "diagnostics": diagnostics,
                        "metadata": meta,
                    }
                    resp_files[decoder].write(json.dumps(response, separators=(",", ":")) + "\n")
                    csv_rows.append(
                        {
                            "dataset": dataset,
                            "decoder": decoder,
                            "source": meta.get("source", ""),
                            "backend": meta.get("source_backend", ""),
                            "job_id": meta.get("job_id", ""),
                            "circuit_id": meta.get("circuit_id", ""),
                            "injected_x": injected,
                            "shot_index": meta.get("shot_index", ""),
                            "bitstring": meta.get("bitstring", ""),
                            "measured_syndrome": "".join(str(bit) for bit in syndrome),
                            "expected_syndrome": meta.get("expected_syndrome", ""),
                            "syndrome_weight": sum(syndrome),
                            "correction_indices": " ".join(str(idx) for idx in correction),
                            "correction_weight": len(correction),
                            "residual_syndrome": "".join(str(bit) for bit in residual),
                            "exact_intended_match": exact_match,
                            "contains_intended_target": contains_target,
                        }
                    )
                    line_counts[decoder] += 1
        for decoder in decoders:
            manifest_rows.append(
                {
                    "dataset": dataset,
                    "request_file": req_path.name,
                    "response_file": resp_paths[decoder].name,
                    "decoder": decoder,
                    "decoder_name": f"surface_{decoder}",
                    "lines": line_counts[decoder],
                }
            )

    with (out_dir / "decoded_shots.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "dataset",
            "decoder",
            "source",
            "backend",
            "job_id",
            "circuit_id",
            "injected_x",
            "shot_index",
            "bitstring",
            "measured_syndrome",
            "expected_syndrome",
            "syndrome_weight",
            "correction_indices",
            "correction_weight",
            "residual_syndrome",
            "exact_intended_match",
            "contains_intended_target",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)

    with (out_dir / "decode_manifest.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["dataset", "request_file", "response_file", "decoder", "decoder_name", "lines"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"Decoded {len(csv_rows)} surface-check syndrome-policy rows into {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
