# 02 — Offline IQL train job

**What to build:** A train entrypoint that consumes the mixed dataset manifest under FrozenAssumptions (assumptions hash recorded), runs distributional IQLTrainer for a configured step budget, and writes a safetensors checkpoint plus train metrics. A tiny fixture mix is enough to demo.

**Blocked by:** 01 — Mixed dataset manifest

**Status:** done

- [x] Job refuses to start without a valid manifest + FrozenAssumptions hash
- [x] IQLTrainer steps complete on logged-action batches from the mix
- [x] Checkpoint written via safetensors (no pickle / torch.load of untrusted blobs)
- [x] Train metrics and assumptions hash are persisted beside the checkpoint
- [x] Unit/integration test with tiny fixture mix proves end-to-end train without GPU requirement for CI
