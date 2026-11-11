# Model preparation

The selected models are LiquidAI/LFM3-1.7B and Qwen/Qwen3-4B-Instruct-2507.
Exact revisions, checkpoint metadata hashes and output paths are in
`configs/models.json`. This commit contains preparation tools and public metadata;
weights and llama.cpp have not been installed in this repository.

Install conversion dependencies in the local environment when ready:

```sh
.venv/bin/python -m pip install -r requirements-model-prep.txt
git clone https://github.com/ggml-org/llama.cpp vendor/llama.cpp
git -C vendor/llama.cpp checkout f7591a6a01f9273de03331732bdc0b39721168be
cmake -S vendor/llama.cpp -B vendor/llama.cpp/build -DGGML_CUDA=OFF
cmake --build vendor/llama.cpp/build --target llama-quantize -j 4
```

The CPU build above is for preparing quantized files. CUDA inference builds need
the actual device architecture and a separate hardware check.

Run each step with a unique run ID; repeat for the other selected model:

```sh
.venv/bin/python scripts/prepare_model.py download --model-id LiquidAI/LFM3-1.7B --run-id lfm3-download
.venv/bin/python scripts/prepare_model.py convert --model-id LiquidAI/LFM3-1.7B --run-id lfm3-f16
.venv/bin/python scripts/prepare_model.py quantize --model-id LiquidAI/LFM3-1.7B --run-id lfm3-quants
```

Checkpoint files are verified against pinned upstream hashes before conversion.
Conversion uses the pinned llama.cpp converter and produces an F16 reference plus
a hash receipt. Quantization verifies that receipt and uses the uncompressed
reference directly for Q8_0, Q6_K, Q4_K_M, Q3_K_M and Q2_K. Existing outputs are
never overwritten. Failures, partial files and per-run manifests are retained.
Inspect a failed attempt before making a new run; there are no automatic retries.

Weights stay in ignored `models/`; receipts/logs stay in ignored `results/raw/`.
No model answering, judges, TACC submission or calibration is performed here.
Full conversion and all six formats still need runtime testing. Qwen4 F16 weights
alone exceed the local 7 GiB inference budget; conversion does not prove GPU fit.
