# GLiNER2.5-Decide case study

This is a sourced, caveated case study — not an independently reproduced
benchmark. The Hugging Face model card retrieved on 2026-09-25 reports 60.2%
average exact-match accuracy and describes the checkpoint as 340M. Fastino's
blog retrieved the same day reports 60.1%, 340M, and latency measurements on
named systems. Hugging Face API metadata reports 486,444,053 F32 parameters.

LWI therefore preserves the disagreement and returns `incomplete` under
`param-v1` rather than choosing the number that would make the model look best.
No baseline latency is invented. The workload is specialized Fast Decisions
classification; it is not evidence that GLiNER2.5-Decide is generally
smarter or better than 4B models.
