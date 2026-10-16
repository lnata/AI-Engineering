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
SAP Fiori
  → Databricks tables (Data Pull)
    → Parent semantic model (from Databricks)
      → Child model (DirectQuery to parent + own logic/build)
        → RDL / Power BI report (design + build) on DEV / PROD
                    ↑
             Specification (financial analysts)
```

A bug or CR can sit in **any** link: RDL design/build, child model build,
child↔parent DirectQuery/logic, parent↔Databricks, Databricks↔SAP, or
**report vs specification** (numbers can match DBX and still be wrong vs spec).

Root-cause checks:

1. **SAP Fiori vs Databricks** — did Data Pull load correctly?
2. **Databricks vs parent / child models** — did semantic models transform correctly?
3. **Models vs RDL / Power BI** — did the report build/design correctly?
4. **Power BI vs Specification** — does the report match requirements?

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
