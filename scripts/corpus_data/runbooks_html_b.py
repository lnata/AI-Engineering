"""HTML portal runbooks (Part B): Gateway, Lineage Catalog, Postmortems, and DQ checks."""

from __future__ import annotations

from scripts.corpus_data.schema import CorpusDocSpec, SectionSpec

RUNBOOKS_HTML_B: list[CorpusDocSpec] = [
    CorpusDocSpec(
        filename="RUNBOOK-PBI-006_gateway_and_dataset_refresh.html",
        fmt="html",
        doc_id="RUNBOOK-PBI-006",
        title="RUNBOOK-PBI-006: Power BI Gateway and Semantic Model Refresh Runbook",
        version="1.3",
        date="2025-03-08",
        doc_type="runbook",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Діагностика помилок оновлення Parent та Child датасетів",
                paragraphs=[
                    "Оновлення корпоративних Parent семантичних моделей стартує автоматично через REST webhook із Airflow після успішного завершення вітрин mart.* та wh.* у Databricks SQL Warehouse.",
                    "Якщо бізнес бачить застарілі вчорашні цифри в Power BI при коректних даних у Databricks, черговий розробник перевіряє історію рефрешу кластера On-Premises / VNet Data Gateway.",
                ],
                table_headers=["Код помилки PBI", "Причина збою", "Стандартна дія усунення"],
                table_rows=[
                    ["DM_GWPipeline_Gateway_Timeout", "Запит імпорту перевищив 120 хв на великій партиції", "Увімкнути Incremental Refresh та перевірити Photon cluster"],
                    ["OAuthTokenRefreshFailed", "Прострочений токен сервіс-принципала Databricks", "Оновити секрет у KeyVault та перезапустити рефреш"],
                    ["DirectQuery_MaxRowsExceeded", "Візуал Child моделі запитує > 1 млн рядків без фільтра", "Додати обов'язковий фільтр періоду або агрегат у Parent"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="LINEAGE-CAT-001_sap_cds_to_databricks_matrix.html",
        fmt="html",
        doc_id="LINEAGE-CAT-001",
        title="LINEAGE-CAT-001: End-to-End Lineage Matrix (SAP Fiori -> Databricks -> Power BI)",
        version="1.5",
        date="2025-04-10",
        doc_type="lineage",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Канонічний реєстр залежностей п'яти базових звітів",
                paragraphs=[
                    "Матриця нижче є єдиним довідником трасування об'єктів між SAP Fiori CDS views, таблицями Databricks, датасетами Power BI та затвердженими специфікаціями.",
                ],
                table_headers=["Код звіту", "SAP Fiori / CDS", "Об'єкти Databricks", "PBIX / Dataset", "Чинна SPEC"],
                table_rows=[
                    ["RPT-SALES-001", "Manage Sales Orders (C_SALESORDER_Q1)", "mart.fact_orders, mart.dim_region", "Sales_Overview_v3.pbix / Sales_Overview_Dataset", "SPEC-FIN-014 v1.3"],
                    ["RPT-INV-002", "Stock Overview (C_MATERIALSTOCK_V2)", "wh.inventory_snapshot", "Inventory_Dev.pbix / Inventory_Dataset", "SPEC-OPS-007 v2.0"],
                    ["RPT-CUST-003", "Customer Master (C_CUSTOMER_MASTER)", "mart.dim_customer", "Customers_Prod.pbix / Customers_Prod", "SPEC-FIN-021 v1.1"],
                    ["RPT-FIN-004", "Profit Center Analysis (C_PROFITCENTER_Q)", "mart.fact_revenue, mart.fact_cogs", "Finance_Dev.pbix / Finance_Margin_Dataset", "SPEC-FIN-030 v1.3"],
                    ["RPT-FX-005", "Incoming Payments (C_PAYMENTDOCUMENT)", "mart.fact_payments, ref.fx_rates", "FX_Revenue.pbix / FX_Revenue_Dataset", "SPEC-FIN-041 v1.2"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="INCIDENT-POSTMORTEM-001_march_sales_discrepancy.html",
        fmt="html",
        doc_id="INCIDENT-POSTMORTEM-001",
        title="INCIDENT-POSTMORTEM-001: March Sales Discrepancy & Line-Grain Regression",
        version="1.0",
        date="2025-03-29",
        doc_type="postmortem",
        report_id="RPT-SALES-001",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Хронологія інцидентів BUGS-41 та BUGS-50 у звіті Sales Overview",
                paragraphs=[
                    "У березні 2025 року зафіксовано два пов'язані дефекти у пайплайні звіту RPT-SALES-001: на PROD виторг за березень у mart.fact_orders становив 1.24M EUR проти 1.31M EUR у SAP Fiori Manage Sales Orders (BUGS-41) через пропущену дельта-партицію від 28 березня.",
                    "Під час підготовки патчу на DEV розробник Data Pull помилково приєднав позиції замовлень VBAP без групування до заголовка замовлення, що викликало завищення сум відносно C_SALESORDER_Q1 (BUGS-50).",
                ],
                bullets=[
                    "Першопричина PROD (BUGS-41): обрив OData пагінації при ротації сертифіката SAP Gateway.",
                    "Першопричина DEV (BUGS-50): порушення гранулярності header net value зі спеки SPEC-FIN-014 v1.3.",
                    "Запобіжник: додано dbt-тест unique(order_id) на mart.fact_orders перед публікацією на DEV.",
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="INCIDENT-POSTMORTEM-002_fx_double_conversion.html",
        fmt="html",
        doc_id="INCIDENT-POSTMORTEM-002",
        title="INCIDENT-POSTMORTEM-002: Double FX Conversion in FX_Revenue.pbix (BUGS-49)",
        version="1.0",
        date="2025-04-09",
        doc_type="postmortem",
        report_id="RPT-FX-005",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Розбір критичного блокера закриття місяця BUGS-49",
                paragraphs=[
                    "Під час квітневого закриття періоду виявлено викривлення сум у звіті FX_Revenue.pbix на PROD: вітрина mart.fact_payments вже містила сконвертовані суми в EUR, проте застаріла DAX-міра спадщини SPEC-FIN-041 v1.0 повторно множила суму на курс із ref.fx_rates.",
                    "Згідно з регламентом POL-DEP-001 v1.3 виправлення DAX-міри було спочатку розгорнуто на DEV, звірено фінансовим аналітиком проти SAP Fiori Incoming Payments і лише після затвердження перенесено на PROD.",
                ],
                table_headers=["Етап реагування", "Фактичний час", "Результат перевірки"],
                table_rows=[
                    ["Локалізація шару", "20 хвилин", "SAP = Databricks (EUR), дефект у Power BI DAX"],
                    ["Деплой фіксу на DEV + звірка FA", "55 хвилин", "Повний збіг 0.00 EUR з C_PAYMENTDOCUMENT"],
                    ["Промоушен на PROD", "15 хвилин після апруву", "Інцидент закрито без порушення POL-DEP-001 v1.3"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="RUNBOOK-DQ-007_great_expectations_checks.html",
        fmt="html",
        doc_id="RUNBOOK-DQ-007",
        title="RUNBOOK-DQ-007: Automated Data Quality Gates before Semantic Refresh",
        version="1.1",
        date="2025-03-31",
        doc_type="runbook",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Блокуючі перевірки якості даних (Circuit Breakers)",
                paragraphs=[
                    "Щоб не поширювати порожні партиції або дублікати у звіти Power BI, кожен DAG у Airflow запускає набір блокуючих dbt та Lakehouse Monitoring тестів перед викликом рефрешу датасету.",
                ],
                table_headers=["Назва перевірки", "Цільова вітрина", "Умова падіння пайплайну"],
                table_rows=[
                    ["chk_orders_header_unique", "mart.fact_orders", "Знайдено хоча б один неунікальний order_id"],
                    ["chk_inventory_rowcount_nonzero", "wh.inventory_snapshot", "Кількість рядків за current_date - 1 дорівнює 0"],
                    ["chk_fx_rate_positive", "ref.fx_rates", "Пропущений або нульовий курс для активної валюти"],
                    ["chk_margin_sap_delta", "mart.fact_revenue", "Відхилення суми від SAP control total > 0.15%"],
                ],
            ),
        ],
    ),
]
