#!/usr/bin/env python3
"""Decoder-policy helpers for paper_05 syndrome streams."""

from __future__ import annotations

import collections
import functools
import math
from dataclasses import dataclass
from typing import Any


POLICIES = ("emw", "uf_like", "bit_flip")
POLICY_ALIASES = {
    "mwpm": "emw",
    "min_weight": "emw",
    "minimum_weight": "emw",
    "uf": "uf_like",
    "bp": "bit_flip",
}


@dataclass(frozen=True)
class DecodeResult:
    policy: str
    correction: tuple[int, ...]
    residual: tuple[int, ...]
    confidence: float
    diagnostics: dict[str, str]


def parse_decoders(value: str) -> tuple[str, ...]:
    decoders: list[str] = []
    for part in value.split(","):
        name = part.strip().lower()
        if not name:
            continue
        name = POLICY_ALIASES.get(name, name)
        if name not in POLICIES:
            aliases = ", ".join(sorted(POLICY_ALIASES))
            raise ValueError(
                f"unknown decoder policy {name!r}; expected one of {', '.join(POLICIES)} "
                f"(legacy aliases: {aliases})"
            )
        if name not in decoders:
            decoders.append(name)
    return tuple(decoders or POLICIES)


def syndrome_from_request(rec: dict[str, Any]) -> list[int]:
    meta = rec.get("metadata", {})
    n_checks = int(meta.get("n_checks", 0))
    if n_checks <= 0:
        n_checks = 1 + max(
            (int(event.get("index", -1)) for event in rec.get("events", []) if str(event.get("type", "Z")).upper() == "Z"),
            default=-1,
        )
    syndrome = [0] * n_checks
    for event in rec.get("events", []):
        if str(event.get("type", "Z")).upper() != "Z":
            continue
        idx = int(event.get("index", -1))
        if 0 <= idx < n_checks:
            syndrome[idx] ^= 1
    return syndrome


def repetition_check_matrix(n_data: int) -> list[list[int]]:
    matrix: list[list[int]] = []
    for row in range(max(0, n_data - 1)):
        bits = [0] * n_data
        bits[row] = 1
        bits[row + 1] = 1
        matrix.append(bits)
    return matrix


def supports_to_check_matrix(n_data: int, supports: list[list[int]]) -> list[list[int]]:
    matrix: list[list[int]] = []
    for support in supports:
        bits = [0] * n_data
        for idx in support:
            if 0 <= idx < n_data:
                bits[idx] ^= 1
        matrix.append(bits)
    return matrix


def correction_syndrome(matrix: list[list[int]], correction: list[int] | tuple[int, ...]) -> list[int]:
    selected = set(int(idx) for idx in correction)
    syndrome: list[int] = []
    for row in matrix:
        parity = 0
        for idx, enabled in enumerate(row):
            if enabled & 1 and idx in selected:
                parity ^= 1
        syndrome.append(parity)
    return syndrome


def residual_syndrome(
    matrix: list[list[int]],
    syndrome: list[int] | tuple[int, ...],
    correction: list[int] | tuple[int, ...],
) -> list[int]:
    produced = correction_syndrome(matrix, correction)
    return [((int(a) & 1) ^ (int(b) & 1)) for a, b in zip(syndrome, produced)]


def matrix_key(matrix: list[list[int]]) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(int(bit) & 1 for bit in row) for row in matrix)


def syndrome_to_int(syndrome: list[int] | tuple[int, ...]) -> int:
    value = 0
    for idx, bit in enumerate(syndrome):
        if int(bit) & 1:
            value |= 1 << idx
    return value


def int_to_syndrome(value: int, n_checks: int) -> tuple[int, ...]:
    return tuple((value >> idx) & 1 for idx in range(n_checks))


def column_masks(key: tuple[tuple[int, ...], ...]) -> tuple[int, ...]:
    if not key:
        return ()
    n_data = len(key[0])
    masks: list[int] = []
    for q in range(n_data):
        mask = 0
        for check_idx, row in enumerate(key):
            if row[q] & 1:
                mask |= 1 << check_idx
        masks.append(mask)
    return tuple(masks)


def _extend_tuple(current: tuple[int, ...], q: int) -> tuple[int, ...] | None:
    if q in current:
        return None
    return tuple(sorted((*current, q)))


@functools.cache
def _decoder_table(key: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...] | None, ...]:
    n_checks = len(key)
    n_states = 1 << n_checks
    masks = column_masks(key)
    corrections: list[tuple[int, ...] | None] = [None] * n_states
    corrections[0] = ()
    queue: collections.deque[int] = collections.deque([0])

    while queue:
        state = queue.popleft()
        current = corrections[state]
        if current is None:
            continue
        for q, mask in enumerate(masks):
            next_state = state ^ mask
            candidate = _extend_tuple(current, q)
            if candidate is None:
                continue
            existing = corrections[next_state]
            if existing is None or (len(candidate), candidate) < (len(existing), existing):
                corrections[next_state] = candidate
                queue.append(next_state)

    return tuple(corrections)


def decode_min_weight(
    matrix: list[list[int]],
    syndrome: list[int] | tuple[int, ...],
    *,
    allowed_columns: tuple[int, ...] | None = None,
) -> tuple[int, ...] | None:
    key = matrix_key(matrix)
    target = syndrome_to_int(tuple(int(bit) & 1 for bit in syndrome))
    if allowed_columns is None:
        table = _decoder_table(key)
        if target >= len(table):
            return None
        return table[target]

    n_checks = len(key)
    n_states = 1 << n_checks
    masks = column_masks(key)
    corrections: list[tuple[int, ...] | None] = [None] * n_states
    corrections[0] = ()
    queue: collections.deque[int] = collections.deque([0])
    allowed = tuple(sorted({idx for idx in allowed_columns if 0 <= idx < len(masks)}))

    while queue:
        state = queue.popleft()
        current = corrections[state]
        if current is None:
            continue
        for q in allowed:
            next_state = state ^ masks[q]
            candidate = _extend_tuple(current, q)
            if candidate is None:
                continue
            existing = corrections[next_state]
            if existing is None or (len(candidate), candidate) < (len(existing), existing):
                corrections[next_state] = candidate
                queue.append(next_state)

    return corrections[target]


def _decode_emw(matrix: list[list[int]], syndrome: list[int]) -> DecodeResult:
    correction = decode_min_weight(matrix, syndrome) or ()
    residual = tuple(residual_syndrome(matrix, syndrome, correction))
    return DecodeResult(
        policy="emw",
        correction=tuple(correction),
        residual=residual,
        confidence=1.0 if not any(residual) else 0.0,
        diagnostics={
            "policy": "exact_binary_minimum_weight",
            "fallback": "0",
        },
    )


def _incident_maps(matrix: list[list[int]]) -> tuple[list[list[int]], list[list[int]]]:
    if not matrix:
        return ([], [])
    n_data = len(matrix[0])
    check_to_vars: list[list[int]] = [[] for _ in matrix]
    var_to_checks: list[list[int]] = [[] for _ in range(n_data)]
    for check_idx, row in enumerate(matrix):
        for q, enabled in enumerate(row):
            if enabled & 1:
                check_to_vars[check_idx].append(q)
                var_to_checks[q].append(check_idx)
    return check_to_vars, var_to_checks


def _decode_uf_like(matrix: list[list[int]], syndrome: list[int]) -> DecodeResult:
    target = [int(bit) & 1 for bit in syndrome]
    if not any(target):
        return DecodeResult(
            policy="uf_like",
            correction=(),
            residual=tuple(0 for _ in target),
            confidence=1.0,
            diagnostics={
                "policy": "union_find_like_greedy_erasure",
                "uf_growth_rounds": "0",
                "uf_erasure_size": "0",
                "uf_greedy_flips": "0",
                "fallback": "0",
            },
        )

    check_to_vars, var_to_checks = _incident_maps(matrix)
    active_checks = {idx for idx, bit in enumerate(target) if bit}
    erasure: set[int] = set()
    for check_idx in active_checks:
        if 0 <= check_idx < len(check_to_vars):
            erasure.update(check_to_vars[check_idx])

    residual = target[:]
    correction_set: set[int] = set()
    greedy_flips = 0
    max_steps = max(1, len(erasure))

    for _ in range(max_steps):
        if not any(residual):
            break
        best_q = -1
        best_gain = 0
        best_unsatisfied = 0
        for q in sorted(erasure):
            if q in correction_set:
                continue
            checks_for_var = var_to_checks[q]
            unsatisfied = sum(residual[check_idx] for check_idx in checks_for_var)
            satisfied = len(checks_for_var) - unsatisfied
            gain = unsatisfied - satisfied
            if (gain, unsatisfied, -q) > (best_gain, best_unsatisfied, -best_q):
                best_q = q
                best_gain = gain
                best_unsatisfied = unsatisfied
        if best_q < 0 or best_gain <= 0:
            break
        correction_set.add(best_q)
        greedy_flips += 1
        for check_idx in var_to_checks[best_q]:
            residual[check_idx] ^= 1

    fallback = "0"
    if any(residual):
        closure = decode_min_weight(matrix, residual) or ()
        correction_set = correction_set.symmetric_difference(closure)
        fallback = "1"

    correction = tuple(sorted(correction_set))
    residual_tuple = tuple(residual_syndrome(matrix, target, correction))
    return DecodeResult(
        policy="uf_like",
        correction=tuple(correction),
        residual=residual_tuple,
        confidence=1.0 if not any(residual_tuple) else 0.0,
        diagnostics={
            "policy": "union_find_like_greedy_erasure",
            "uf_growth_rounds": "1",
            "uf_erasure_size": str(len(erasure)),
            "uf_greedy_flips": str(greedy_flips),
            "fallback": fallback,
        },
    )


def _decode_bit_flip(matrix: list[list[int]], syndrome: list[int], *, prior_p: float = 0.08, max_iter: int = 12) -> DecodeResult:
    target = [int(bit) & 1 for bit in syndrome]
    if not matrix:
        return DecodeResult(
            policy="bit_flip",
            correction=(),
            residual=tuple(target),
            confidence=0.0,
            diagnostics={"policy": "hard_decision_bit_flip", "bit_flip_converged": "0", "fallback": "0"},
        )

    n_data = len(matrix[0])
    check_to_vars, var_to_checks = _incident_maps(matrix)
    best_bits = [0] * n_data
    best_residual = target[:]
    best_score = (sum(best_residual), sum(best_bits), tuple(best_bits))
    converged = False
    iterations = 0
    bits = [0] * n_data
    residual = target[:]

    if not any(residual):
        converged = True

    for iterations in range(1, max_iter + 1):
        if not any(residual):
            converged = True
            break

        best_q = -1
        best_gain = 0
        best_unsatisfied = 0
        for q, checks_for_var in enumerate(var_to_checks):
            if not checks_for_var:
                continue
            unsatisfied = sum(residual[check_idx] for check_idx in checks_for_var)
            satisfied = len(checks_for_var) - unsatisfied
            gain = unsatisfied - satisfied
            if (gain, unsatisfied, -q) > (best_gain, best_unsatisfied, -best_q):
                best_q = q
                best_gain = gain
                best_unsatisfied = unsatisfied

        if best_q < 0 or best_gain <= 0:
            break

        bits[best_q] ^= 1
        for check_idx in var_to_checks[best_q]:
            residual[check_idx] ^= 1

        score = (sum(residual), sum(bits), tuple(bits))
        if score < best_score:
            best_score = score
            best_bits = bits[:]
            best_residual = residual[:]
        if not any(residual):
            converged = True
            best_bits = bits[:]
            best_residual = residual[:]
            break

    correction = tuple(idx for idx, bit in enumerate(best_bits) if bit)
    closure_weight = 0
    fallback = "0"
    if any(best_residual):
        closure = decode_min_weight(matrix, best_residual) or ()
        closure_weight = len(closure)
        correction = tuple(sorted(set(correction).symmetric_difference(closure)))
        fallback = "1"

    residual = tuple(residual_syndrome(matrix, target, correction))
    return DecodeResult(
        policy="bit_flip",
        correction=correction,
        residual=residual,
        confidence=1.0 if converged else (0.8 if not any(residual) else 0.0),
        diagnostics={
            "policy": "hard_decision_bit_flip",
            "bit_flip_converged": "1" if converged else "0",
            "bit_flip_iterations": str(iterations),
            "bit_flip_best_residual_weight": str(sum(best_residual)),
            "bit_flip_closure_weight": str(closure_weight),
            "fallback": fallback,
        },
    )


def decode_policy(
    policy: str,
    matrix: list[list[int]],
    syndrome: list[int],
    *,
    prior_p: float = 0.08,
) -> DecodeResult:
    key = matrix_key(matrix)
    syndrome_key = tuple(int(bit) & 1 for bit in syndrome)
    return _decode_policy_cached(policy, key, syndrome_key, round(float(prior_p), 12))


@functools.cache
def _decode_policy_cached(
    policy: str,
    key: tuple[tuple[int, ...], ...],
    syndrome: tuple[int, ...],
    prior_p: float,
) -> DecodeResult:
    matrix = [list(row) for row in key]
    syndrome_bits = list(syndrome)
    policy = POLICY_ALIASES.get(policy, policy)
    if policy == "emw":
        return _decode_emw(matrix, syndrome_bits)
    if policy == "uf_like":
        return _decode_uf_like(matrix, syndrome_bits)
    if policy == "bit_flip":
        return _decode_bit_flip(matrix, syndrome_bits, prior_p=prior_p)
    raise ValueError(f"unknown decoder policy: {policy}")
