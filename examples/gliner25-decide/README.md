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

## Observation classification

| Observation | Evidence class | Scope and limitation |
|---|---|---|
| 60.2% exact-match accuracy | `model_card` | Fastino/Hugging Face model-card report; not independently reproduced here. |
| 60.1% exact-match accuracy | `vendor_reported` | Fastino blog report; preserved as a disagreement with 60.2%, not averaged. |
| 340M parameter label | `model_card` / `vendor_reported` | Conflicting external labels, not a measured parameter count. |
| 486,444,053 F32 metadata parameters | `derived` | Derived from the cited Hugging Face API metadata representation; semantic equivalence to the 340M label is not assumed. |
| Named vendor latency figures | `vendor_reported` | No matching baseline latency or independent reproduction is present. |
| Qwen comparison-row accuracy/parameter values | `disputed` / `model_card` | The row is not an independently attributable Qwen checkpoint observation; its rounded parameter label and quality value remain incomplete. |

The fixture therefore keeps both parameter claims disputed where checkpoint
identity is unavailable, contains no serving
metrics, and returns `incomplete` under `param-v1`. It must not be presented as
an independently reproduced LWI score or as universal model superiority.
