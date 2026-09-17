# Paper 05: Hardware-in-the-loop and digitized-GKP syndrome extraction

This workflow demonstrates syndrome extraction and decoder replay for four
branches:

- repetition-code circuits;
- compact CSS/Steane Z-check circuits;
- \(5\times5\) planar surface-check Z-layer circuits;
- a PennyLane-backed digitized-GKP companion branch.

The first three branches can run locally and, when credentials are configured,
on IBM Quantum hardware. The digitized-GKP branch is off-hardware by design:
IBM gate-model backends do not provide oscillator-mode GKP state preparation or
quadrature measurement. The default branch uses PennyLane `default.gaussian` as
a finite-squeezed Gaussian-CV readout proxy before modular binning into outer
Z-check bits. It tests the LiDMaS+ request interface for GKP-derived digitized
syndromes without claiming physical GKP execution.

Each decode stage replays every extracted syndrome stream through three
policies: exact binary minimum weight (`emw`), a union-find-like greedy
heuristic (`uf_like`), and a hard-decision bit-flip heuristic (`bit_flip`).
The code also accepts historical aliases (`mwpm`, `uf`, and `bp`) so older
generated filenames remain readable; these aliases do not imply that a matching
graph or full BP/min-sum update was used. The manuscript plots default to the
EMW baseline, while the heuristic rows are written into the generated decoder
response files and `decoded_shots.csv`.

## Revision evidence

The `revision_evidence/` directory contains the fixed reviewer-facing artifacts
cited by the FCS electronic supplement: `mapping_validation.csv`,
`decoder_closure_audit.csv`, `support_metrics.csv`, `gkp_sensitivity.csv`, the
surface-check matrix/support exports, the hardware data-register audit, and the
revision validation figure.

Run the local workflow:

```bash
./examples/paper_runs/paper_05/run_all.sh
```

This runs all local branches. It skips IBM Runtime submission unless
`LIDMAS_P5_HARDWARE=1` is set.

Run the IBM Runtime path after configuring an IBM Quantum account:

```bash
LIDMAS_P5_HARDWARE=1 \
LIDMAS_P5_IBM_BACKEND=ibm_brisbane \
IBM_QUANTUM_INSTANCE=your/hub/group/project \
./examples/paper_runs/paper_05/run_all.sh
```

For a manuscript-scale hardware demonstration, use all single-data-qubit
injections and at least 4096 shots per circuit. Submit without waiting, then
fetch and analyze after IBM marks the job complete:

```bash
LIDMAS_P5_TARGETS=all \
LIDMAS_P5_SHOTS=4096 \
./examples/paper_runs/paper_05/01_build_syndrome_circuits.sh

LIDMAS_P5_TARGETS=all \
LIDMAS_P5_SHOTS=4096 \
./examples/paper_runs/paper_05/02_run_local_simulation.sh

LIDMAS_P5_TARGETS=all \
LIDMAS_P5_IBM_SHOTS=4096 \
LIDMAS_P5_IBM_WAIT=0 \
./examples/paper_runs/paper_05/03_submit_ibm_runtime.sh
```

Check the queued job without fetching results:

```bash
LIDMAS_P5_IBM_STATUS_ONLY=1 \
./examples/paper_runs/paper_05/03_fetch_ibm_runtime_results.sh
```

Once the status is complete, run:

```bash
./examples/paper_runs/paper_05/03_fetch_ibm_runtime_results.sh
./examples/paper_runs/paper_05/04_ingest_results.sh
./examples/paper_runs/paper_05/05_decode_live_syndromes.sh
./examples/paper_runs/paper_05/06_analyze_and_plot.sh
```

Run the compact CSS/Steane path:

```bash
LIDMAS_P5_QLDPC_TARGETS=all \
LIDMAS_P5_QLDPC_SHOTS=4096 \
./examples/paper_runs/paper_05/11_build_qldpc_syndrome_circuits.sh

LIDMAS_P5_QLDPC_TARGETS=all \
LIDMAS_P5_QLDPC_SHOTS=4096 \
./examples/paper_runs/paper_05/12_run_qldpc_local_simulation.sh
```

The compact CSS path uses the Steane CSS parity-check matrix as a small
hardware-facing interface check. It measures the Z-check half for clean and
single-X injected data-qubit circuits. This is suitable for live syndrome
extraction and correction-localization tests, but it should not be described as
a large asymptotic qLDPC memory. The `LIDMAS_P5_QLDPC_*` environment-variable
prefix is retained only as a historical compatibility alias for this compact
CSS/Steane branch.

Submit and fetch the matching IBM Runtime job:

```bash
LIDMAS_P5_QLDPC_TARGETS=all \
LIDMAS_P5_QLDPC_IBM_SHOTS=4096 \
LIDMAS_P5_QLDPC_IBM_WAIT=0 \
./examples/paper_runs/paper_05/13_submit_qldpc_ibm_runtime.sh

LIDMAS_P5_QLDPC_IBM_STATUS_ONLY=1 \
./examples/paper_runs/paper_05/13_fetch_qldpc_ibm_runtime_results.sh

./examples/paper_runs/paper_05/13_fetch_qldpc_ibm_runtime_results.sh
./examples/paper_runs/paper_05/14_ingest_qldpc_results.sh
./examples/paper_runs/paper_05/15_decode_qldpc_syndromes.sh
./examples/paper_runs/paper_05/16_analyze_qldpc.sh
```

Run the \(5\times5\) planar surface-check Z-layer path:

```bash
LIDMAS_P5_SURFACE_DISTANCE=5 \
LIDMAS_P5_SURFACE_TARGETS=representative \
./examples/paper_runs/paper_05/21_build_surface_syndrome_circuits.sh

LIDMAS_P5_SURFACE_DISTANCE=5 \
LIDMAS_P5_SURFACE_TARGETS=representative \
LIDMAS_P5_SURFACE_SHOTS=4096 \
./examples/paper_runs/paper_05/22_run_surface_local_simulation.sh
```

The surface-check path measures only the Z-check half for injected-X
correction. The default representative target set avoids running all 40
single-data-qubit injections while still using a \(5\times5\), 56-active-qubit
circuit. It is an interface audit, not a demonstration of an encoded logical
qubit or code distance.

Submit and fetch the matching IBM Runtime job:

```bash
LIDMAS_P5_SURFACE_DISTANCE=5 \
LIDMAS_P5_SURFACE_TARGETS=representative \
LIDMAS_P5_SURFACE_IBM_SHOTS=4096 \
LIDMAS_P5_SURFACE_IBM_WAIT=0 \
./examples/paper_runs/paper_05/23_submit_surface_ibm_runtime.sh

LIDMAS_P5_SURFACE_IBM_STATUS_ONLY=1 \
./examples/paper_runs/paper_05/23_fetch_surface_ibm_runtime_results.sh

./examples/paper_runs/paper_05/23_fetch_surface_ibm_runtime_results.sh
./examples/paper_runs/paper_05/24_ingest_surface_results.sh
./examples/paper_runs/paper_05/25_decode_surface_syndromes.sh
./examples/paper_runs/paper_05/26_analyze_surface.sh
```

Run the PennyLane-backed digitized-GKP companion branch:

```bash
LIDMAS_P5_GKP_DISTANCE=5 \
LIDMAS_P5_GKP_TARGETS=representative \
./examples/paper_runs/paper_05/31_build_gkp_digitized_model.sh

LIDMAS_P5_GKP_DISTANCE=5 \
LIDMAS_P5_GKP_TARGETS=representative \
LIDMAS_P5_GKP_SHOTS=4096 \
LIDMAS_P5_GKP_ROUNDS=3 \
LIDMAS_P5_GKP_PENNYLANE_MODE=required \
./examples/paper_runs/paper_05/32_run_gkp_digitized_sampler.sh

./examples/paper_runs/paper_05/33_ingest_gkp_results.sh
./examples/paper_runs/paper_05/34_decode_gkp_syndromes.sh
./examples/paper_runs/paper_05/35_analyze_gkp.sh
./examples/paper_runs/paper_05/36_render_gkp_figures.sh
```

The digitized-GKP summary table is
`results/35_gkp_analysis/table_gkp_digitized_syndrome_summary.csv`. Its
manuscript figures are written under
`results/35_gkp_analysis/manuscript_figures`.

The scripts do not write credentials. Use a saved Qiskit Runtime account or
environment-provided credentials. If credentials are missing, step 03 exits with a
message explaining what to set.

For convenience, you can also create an ignored local file:

```text
examples/paper_runs/paper_05/ibm_credentials.local.json
```

Use the shape in `ibm_credentials.example.json`. The local file is ignored by git.
