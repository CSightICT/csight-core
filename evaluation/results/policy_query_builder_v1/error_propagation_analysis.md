# Error Propagation Analysis

Gold Extraction was evaluated for RAW and deterministic builders. Model Extraction and the real LLM
builder were not evaluated because the approved external Qwen endpoint was unavailable. Filling
those cells with deterministic Mock output would hide extraction and provider error propagation.

On Gold input, deterministic preserved Recall@10 but reduced Dev MRR@10 and nDCG@10 versus RAW.
The remaining errors therefore cannot be attributed to model extraction. They arise from query
formulation/ranking and the frozen candidate-recall ceiling. Model-versus-builder decomposition stays
open until an external Dev qualification is available.
