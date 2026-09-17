#!/usr/bin/env python3
"""Small compact CSS/Steane syndrome helpers for paper_05.

The default matrix is the Steane [[7,1,3]] CSS parity-check matrix. This is a
hardware-safe compact CSS proxy for live syndrome extraction: it is low-density,
has unique single-X syndromes, and needs only one ancilla per Z check.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import Any


STEANE_HZ: list[list[int]] = [
    [1, 1, 1, 0, 1, 0, 0],
    [1, 1, 0, 1, 0, 1, 0],
    [1, 0, 1, 1, 0, 0, 1],
]


@dataclass(frozen=True)
class ExperimentSpec:
    circuit_id: str
    injected_x: int | None
    label: str


def sanitize_label(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    clean = clean.strip("_")
    return clean or "dataset"


def hz_matrix() -> list[list[int]]:
    return [row[:] for row in STEANE_HZ]


def n_data() -> int:
    return len(STEANE_HZ[0])


def n_checks() -> int:
    return len(STEANE_HZ)


def parse_targets(targets: str) -> list[int | None]:
    value = targets.strip().lower()
    if value in {"all", "all_injected"}:
        return [None, *range(n_data())]
    if value in {"middle", "mid"}:
        return [None, n_data() // 2]
    if value in {"clean", "none"}:
        return [None]

    out: list[int | None] = [None]
    for part in targets.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part in {"clean", "none"}:
            continue
        idx = int(part)
        if idx < 0 or idx >= n_data():
            raise ValueError(f"target index {idx} outside [0, {n_data() - 1}]")
        out.append(idx)
    return out


def experiment_specs(targets: str) -> list[ExperimentSpec]:
    specs: list[ExperimentSpec] = []
    seen: set[int | None] = set()
    for target in parse_targets(targets):
        if target in seen:
            continue
        seen.add(target)
        if target is None:
            specs.append(ExperimentSpec(circuit_id="clean", injected_x=None, label="clean"))
        else:
            specs.append(ExperimentSpec(circuit_id=f"x_data_{target}", injected_x=target, label=f"X on data {target}"))
    return specs


def syndrome_from_data_bits(data_bits: list[int]) -> list[int]:
    return [sum((bit & 1) * h for bit, h in zip(data_bits, row)) & 1 for row in STEANE_HZ]


def expected_syndrome(injected_x: int | None) -> list[int]:
    data_bits = [0] * n_data()
    if injected_x is not None:
        data_bits[injected_x] = 1
    return syndrome_from_data_bits(data_bits)


def cbit_values_to_bitstring(cbits_low_to_high: list[int]) -> str:
    return "".join(str(int(v) & 1) for v in reversed(cbits_low_to_high))


def parse_bitstring(bitstring: str) -> tuple[list[int], list[int]]:
    compact = bitstring.replace(" ", "").strip()
    expected = n_checks() + n_data()
    if len(compact) != expected:
        raise ValueError(f"bitstring length {len(compact)} does not match expected {expected}: {bitstring!r}")
    c_low_to_high = [int(ch) for ch in reversed(compact)]
    syndrome = c_low_to_high[: n_checks()]
    data = c_low_to_high[n_checks() : n_checks() + n_data()]
    return syndrome, data


def syndrome_to_events(syndrome: list[int], *, time_ns: int = 1000) -> list[dict[str, Any]]:
    return [{"index": idx, "time_ns": time_ns, "type": "Z"} for idx, bit in enumerate(syndrome) if bit & 1]


def decode_min_weight(syndrome: list[int]) -> list[int]:
    """Return a minimum-Hamming-weight X correction matching the Z-check syndrome."""
    target = [bit & 1 for bit in syndrome]
    best: tuple[int, tuple[int, ...]] | None = None
    for bits in itertools.product((0, 1), repeat=n_data()):
        if syndrome_from_data_bits(list(bits)) != target:
            continue
        weight = sum(bits)
        if best is None or (weight, bits) < best:
            best = (weight, bits)
    if best is None:
        return []
    return [idx for idx, bit in enumerate(best[1]) if bit]


def correction_syndrome(correction_indices: list[int]) -> list[int]:
    bits = [0] * n_data()
    for idx in correction_indices:
        if 0 <= idx < n_data():
            bits[idx] ^= 1
    return syndrome_from_data_bits(bits)


def build_qiskit_circuit(spec: ExperimentSpec) -> Any:
    try:
        from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional environment
        raise SystemExit("Qiskit is required to build compact CSS/Steane syndrome circuits.") from exc

    data = QuantumRegister(n_data(), "d")
    anc = QuantumRegister(n_checks(), "z")
    meas = ClassicalRegister(n_checks() + n_data(), "meas")
    qc = QuantumCircuit(data, anc, meas, name=spec.circuit_id)

    if spec.injected_x is not None:
        qc.x(data[spec.injected_x])
        qc.barrier(data)

    for check_idx, row in enumerate(STEANE_HZ):
        for data_idx, enabled in enumerate(row):
            if enabled & 1:
                qc.cx(data[data_idx], anc[check_idx])

    qc.barrier(data, anc)
    for idx in range(n_checks()):
        qc.measure(anc[idx], meas[idx])
    for idx in range(n_data()):
        qc.measure(data[idx], meas[n_checks() + idx])
    return qc


def circuit_metadata(spec: ExperimentSpec) -> dict[str, Any]:
    return {
        "circuit_id": spec.circuit_id,
        "label": spec.label,
        "code_family": "css_ldpc",
        "code_name": "steane_z_checks",
        "n_data": n_data(),
        "n_checks": n_checks(),
        "injected_x": "" if spec.injected_x is None else spec.injected_x,
        "expected_syndrome": "".join(str(bit) for bit in expected_syndrome(spec.injected_x)),
        "check_matrix": hz_matrix(),
        "check_type": "Z",
        "classical_bit_order": "low-to-high: syndrome[0..n_checks-1], data[0..n_data-1]",
        "bitstring_order": "Qiskit count keys are parsed as high-to-low classical bits.",
    }
