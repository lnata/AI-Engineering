"""Part 3 of human-verified HW2 RAG testset: 4 cross-source HW1 Ticket + HW2 Spec/Policy questions."""

from __future__ import annotations

JIRA_CROSS_SOURCE_QUESTIONS: list[dict] = [
    {
        "id": "QA-25",
        "category": "cross_source_ticket_spec",
        "human_verified": True,
        "curator_note": "Cross-source HW1 BUGS-41 + HW2 SPEC-FIN-014 / RUNBOOK-DBX-001 / Postmortem.",
        "question": "Яка розбіжність сум за березень між SAP Fiori Manage Sales Orders та mart.fact_orders описана в тікеті BUGS-41, і яке правило гранулярності order_id або перевірки партицій вимагає специфікація SPEC-FIN-014?",
        "expected_abstain": False,
        "expected_sources": [
            "data/raw/BUGS-41.json",
            "data/hw2_corpus/raw/SPEC-FIN-014_v1.3_sales_revenue_region_channel.pdf",
            "data/hw2_corpus/raw/RUNBOOK-DBX-001_sap_sales_orders_ingest.html",
            "data/hw2_corpus/raw/INCIDENT-POSTMORTEM-001_march_sales_discrepancy.html",
        ],
        "required_source_groups": [
            ["data/raw/BUGS-41.json"],
            [
                "data/hw2_corpus/raw/SPEC-FIN-014_v1.3_sales_revenue_region_channel.pdf",
                "data/hw2_corpus/raw/RUNBOOK-DBX-001_sap_sales_orders_ingest.html",
                "data/hw2_corpus/raw/INCIDENT-POSTMORTEM-001_march_sales_discrepancy.html",
            ],
        ],
        "expected_sections": [
            "1. Картка та опис Jira-тікета BUGS-41",
            "1. Огляд звіту Sales Overview та джерел даних",
            "2. Правила агрегації та мапінг полів",
            "3. Контроль звірки між шарами пайплайну",
            "1. Хронологія інцидентів BUGS-41 та BUGS-50 у звіті Sales Overview",
        ],
        "required_facts": ["1.31M", "1.24M", "SPEC-FIN-014"],
        "forbidden_facts": [],
        "reference_answer": "У тікеті BUGS-41 на PROD у SAP Fiori Manage Sales Orders (C_SALESORDER_Q1) виторг за березень становив 1.31M проти 1.24M у mart.fact_orders та Sales_Overview_v3.pbix; за SPEC-FIN-014 v1.3 вітрина агрегується на рівні заголовка замовлення order_id та звіряється за дельта-партиціями ERDAT із допуском <= 0.05%.",
    },
    {
        "id": "QA-26",
        "category": "cross_source_ticket_spec",
        "human_verified": True,
        "curator_note": "Cross-source HW1 BUGS-44 + HW2 SPEC-FIN-021 active customer filter.",
        "question": "Які цифри по країні UA наведено у тікеті BUGS-44 для Customers_Prod.pbix проти mart.dim_customer, і яку точну умову фільтрації soft-deleted записів встановлює специфікація SPEC-FIN-021?",
        "expected_abstain": False,
        "expected_sources": [
            "data/raw/BUGS-44.json",
            "data/hw2_corpus/raw/SPEC-FIN-021_v1.1_active_customers_by_country.pdf",
        ],
        "required_source_groups": [
            ["data/raw/BUGS-44.json"],
            ["data/hw2_corpus/raw/SPEC-FIN-021_v1.1_active_customers_by_country.pdf"],
        ],
        "expected_sections": [
            "1. Картка та опис Jira-тікета BUGS-44",
            "1. Визначення активної клієнтської бази",
            "2. Фільтрація soft-deleted записів у Databricks та Power BI",
        ],
        "required_facts": ["11802", "12040", "is_deleted"],
        "forbidden_facts": [],
        "reference_answer": "У тікеті BUGS-44 вітрина mart.dim_customer на PROD містить 11802 активних клієнтів UA, а звіт Customers_Prod.pbix показує 12040 через включення soft-deleted записів; специфікація SPEC-FIN-021 v1.1 зобов'язує явно фільтрувати is_deleted = false / FALSE().",
    },
    {
        "id": "QA-27",
        "category": "cross_source_ticket_spec",
        "human_verified": True,
        "curator_note": "Cross-source HW1 CR BUGS-47 + HW2 SPEC-FIN-041 v1.2.",
        "question": "Що саме пропонує змінити Change Request у тікеті BUGS-47 щодо моменту конвертації валют і яке правило діє зараз у чинній специфікації SPEC-FIN-041?",
        "expected_abstain": False,
        "expected_sources": [
            "data/raw/BUGS-47.json",
            "data/hw2_corpus/raw/SPEC-FIN-041_v1.2_fx_conversion_timing_rates.pdf",
            "data/hw2_corpus/raw/RELEASE-NOTES-2025-Q1_reporting_platform.md",
        ],
        "required_source_groups": [
            ["data/raw/BUGS-47.json"],
            [
                "data/hw2_corpus/raw/SPEC-FIN-041_v1.2_fx_conversion_timing_rates.pdf",
                "data/hw2_corpus/raw/RELEASE-NOTES-2025-Q1_reporting_platform.md",
            ],
        ],
        "expected_sections": [
            "1. Картка та опис Jira-тікета BUGS-47",
            "1. Єдиний стандарт валютної конвертації у FX Revenue",
            "1. Зведення оновлених специфікацій та регламентів у Q1 2025",
        ],
        "required_facts": ["posting date", "payment_date|payment date", "SPEC-FIN-041"],
        "forbidden_facts": ["Monthly Avg"],
        "reference_answer": "Тікет BUGS-47 є запитом на зміну (CR) для переходу на конвертацію за датою проводки posting date замість payment date із релізом спочатку на DEV, потім на PROD; наразі за чинною SPEC-FIN-041 v1.2 одноразова конвертація у mart.fact_payments виконується за курсом на payment_date.",
    },
    {
        "id": "QA-28",
        "category": "cross_source_ticket_spec",
        "human_verified": True,
        "curator_note": "Cross-source HW1 BUGS-53 process breach + HW2 POL-DEP-001 v1.3 / deployment.json.",
        "question": "Яке порушення процесу деплою для звіту Inventory Snapshot описано в тікеті BUGS-53 і який обов'язковий маршрут викатки встановлюють регламент POL-DEP-001 v1.3 та довідник deployment.json?",
        "expected_abstain": False,
        "expected_sources": [
            "data/raw/BUGS-53.json",
            "data/hw2_corpus/raw/POL-DEP-001_v1.3_deployment_and_reconciliation_policy.docx",
            "data/reference/deployment.json",
        ],
        "required_source_groups": [
            ["data/raw/BUGS-53.json"],
            [
                "data/hw2_corpus/raw/POL-DEP-001_v1.3_deployment_and_reconciliation_policy.docx",
                "data/reference/deployment.json",
            ],
        ],
        "expected_sections": [
            "1. Картка та опис Jira-тікета BUGS-53",
            "1. Обов'язковий маршрут релізу змін (DEV -> Approval -> PROD)",
            "1. Правило промоушену релізів та контрольні етапи",
        ],
        "required_facts": ["Inventory Snapshot|hotfix", "DEV", "approval|апрув|погодження", "PROD"],
        "forbidden_facts": ["Дозволявся для hotfix P1"],
        "reference_answer": "У тікеті BUGS-53 зафіксовано процесний інцидент: хотфікс Inventory Snapshot викотили одразу на PROD в обхід DEV та без апруву FA; регламент POL-DEP-001 v1.3 і довідник deployment.json вимагають маршруту DEV deploy -> FA approval -> PROD deploy.",
    },
]
