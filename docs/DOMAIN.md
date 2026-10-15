# Domain model — SAP → Databricks → Power BI

## Ticket types

| Type | Meaning |
|------|---------|
| **Bug** | Something is wrong vs expected data or vs specification |
| **Change Request** | Spec / report / pipeline should be changed on purpose |

## Actors

| Role | Owns |
|------|------|
| **Financial analyst** | Specification, acceptance rules |
| **Report developer** | Power BI report & dataset |
| **Data Pull team** | SAP → Databricks load |

## Pipeline (where bugs can appear)

```
SAP Fiori  →  Databricks (Data Pull)  →  Power BI report (DEV / PROD)
                    ↑
             Specification (financial analysts)
```

Discrepancies can be filed at **any** stage. Root-cause analysis must reconcile:

1. **SAP Fiori vs Databricks** — did Data Pull load correctly?
2. **Databricks vs Power BI** — did the report/dataset transform correctly?
3. **Power BI vs Specification** — does the report match requirements?

Point 3 matters: numbers can “match the database” and still be a bug if they **do not match the spec**.

## Deployment pipeline (after a fix / CR)

```
implement fix  →  deploy DEV  →  approval (usually FA)  →  deploy PROD
```

Rules:

- Never deploy a fix straight to **PROD**
- Re-run reconciliation on **DEV** before approval
- After PROD deploy, re-check on **PROD**

See `data/reference/deployment.json`.

## Extraction contract

See `src/schema.py` (`TicketExtraction`): every ticket must fill report DEV/PROD,
SAP Fiori refs, specification refs, ownership, `reconciliation`, and `deployment`.
