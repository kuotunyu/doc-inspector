# Doc Inspector portfolio brief

## Product

Doc Inspector is a document preflight product for Taiwan public-service forms.
It accepts images or PDFs, extracts one of two fixed schemas, applies
deterministic checks, and returns a red/yellow/green correction list with
field-level evidence. The product helps a person spot missing or inconsistent
information before submission; it does not decide eligibility or replace an
authority's review.

## Architecture

The pipeline separates uncertain perception from deterministic decisions:
validated document ingestion feeds a switchable structured-output VLM adapter,
strict Pydantic schemas reject malformed fields, and pure Python rules produce
the review result. A provenance resolver then searches the document's own text
layer and emits a page/bounding box only when the evidence location is unique.
Gradio presents next actions first and keeps full extraction, JSON, and Excel
exports available for inspection.

## Evidence

- The deterministic decision layer matched **24 / 24** fixed synthetic cases.
- Synthetic provenance covered 61 fields with 0% false verified results; this
  evaluates resolver policy, not real-document extraction accuracy.
- On the frozen XFUND Chinese extraction benchmark, micro F1 was **0.4471** for
  `gemini-3.5-flash-lite` and **0.4819** for `gpt-5-mini`.
- Those XFUND results are **below production-grade extraction**. They show why
  evidence review and deterministic rules remain necessary rather than proving
  real-case readiness.
- The optional fixed ColQwen2 page-retrieval benchmark recorded Recall@1 0.95
  and Recall@3 1.00; it is a small benchmark, not a general deployment claim.

## Deployment lineage

[GitHub](https://github.com/kuotunyu/doc-inspector) is the source of truth. The
public [Hugging Face Docker
Space](https://huggingface.co/spaces/steven0226/doc-inspector) is produced from a
clean archive of a reviewed Git commit with Space-specific metadata. Release
and deployment verification compare a fixed runtime-critical allowlist: 19 non-README files byte-for-byte plus README metadata/body. Git archive hygiene separately excludes private/planning paths; local caches, secrets, raw documents, benchmark rows, model weights, and logs are excluded. This brief documents the verified `v1.1.3` baseline and does not publish or rebuild the Space.

## Boundaries

The **provider/privacy boundary** is explicit: a cloud provider receives a
document only after user consent, provider keys and model IDs stay in local or
host configuration, and the product does not retain raw provider responses.
Uploaded files can contain sensitive data, so the public demo should use
synthetic samples unless the user understands the transfer. Provider
availability, cost, and extraction quality remain external dependencies.
Green means only that the current technical rules found no issue; it is not
approval, legal advice, benefits advice, or a production extraction guarantee.
