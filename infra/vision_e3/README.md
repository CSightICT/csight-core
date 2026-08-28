# CSight E3 host-native Vision runtime

This directory runs the E3 DINOv2 binary any-defect checkpoint as a private,
loopback-only service. It has no Core database access, does not fetch model
weights at runtime, and is not installed into the backend environment or image.

The runtime accepts only the frozen E3 identity. Startup verifies the exact
264,918,248-byte size and SHA-256, scans for unsafe pickle globals, uses
`torch.load(..., weights_only=True, mmap=True)`, validates the checkpoint schema,
and strict-loads an offline architecture. There is no unsafe fallback and no
automatic Mock fallback.

## Run the synthetic scenario demo

Keep `E3_best_epoch10.pt` outside the repository. In one terminal:

```bash
make setup-vision-e3
VISION_E3_CHECKPOINT_PATH=/absolute/path/E3_best_epoch10.pt make start-vision-e3
```

In another terminal:

```bash
make health-vision-e3
make qualify-vision-e3
make up-e3-scenario-poc
make smoke-e3-scenario-vision
```

The host service binds to `127.0.0.1:8093`. Docker Workers reach it through
`http://host.docker.internal:8093`. It uses one process, one serialized inference
at a time, and MPS on Apple Silicon when available; otherwise it uses CUDA or CPU.

## Scope and claims

The E3 score is reviewer evidence only. A score at or above `0.8984375` is a
high-confidence defect candidate. A lower score means human review is still
required and is never a normal-product confirmation. The model cannot provide a
defect type, location, mask, severity, refund, exchange, or final decision.

Kaputt training data is restricted to education and scientific computer-vision
research. This runtime is therefore approved only for the internal, synthetic,
non-commercial scenario demonstration. Do not expose it publicly, use customer
data, or represent it as a commercial/customer pilot without a separate rights
and legal approval. The synthetic connectivity image is not product-domain
qualification.
