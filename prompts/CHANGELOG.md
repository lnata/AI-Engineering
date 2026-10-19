# Prompt changelog

## v2.1 — 2026-10-19 (review fix)

- Removed concrete report-name examples that overlapped the golden set
  (`Sales Overview`, `Gross Margin Dashboard`, etc.) — risk of answer leakage.
- Clarified: invent nothing; optional fields → `null` if absent from ticket text.
- Clarified: `deployment.status` only from progress wording in THIS ticket.
- Ownership: copy names as written; null if role not mentioned.

## v2 — 2026-10-15

- Tightened `priority` rules (critical only for PROD finance / explicit blockers).
- Tightened `deployment.status` inference (not_started vs in_development vs
  deployed_to_dev / pending_approval / approved_for_prod / deployed_to_prod).
- Prefer human `report.name` over `.pbix` filenames.
- Clearer `primary_assignee_role` mapping by pipeline layer.
- Reason: v1 Gemini field accuracy ~79%; weakest fields were priority (40%),
  deployment.status (30%), report.name (20%).

## v1 — 2026-10-15

- Baseline extraction prompt for Bug + Change Request tickets.
- Covers SAP Fiori → Databricks → Power BI, specification, ownership, reconciliation, and DEV→approval→PROD deployment.
- Instructs the model to always fill `reconciliation` and `deployment` even when details are missing (use nulls / unknown enums).
