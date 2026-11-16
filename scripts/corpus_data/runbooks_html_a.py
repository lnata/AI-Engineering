"""HTML portal runbooks (Part A): Databricks & Airflow ingestion pipelines 001–005."""

from __future__ import annotations

from scripts.corpus_data.schema import CorpusDocSpec, SectionSpec

RUNBOOKS_HTML_A: list[CorpusDocSpec] = [
    CorpusDocSpec(
        filename="RUNBOOK-DBX-001_sap_sales_orders_ingest.html",
        fmt="html",
        doc_id="RUNBOOK-DBX-001",
        title="RUNBOOK-DBX-001: Airflow & Databricks Pipeline — SAP Sales Orders",
        version="1.4",
        date="2025-03-12",
        doc_type="runbook",
        report_id="RPT-SALES-001",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Конфігурація пайплайну dag_sap_sales_orders_cdpos",
                paragraphs=[
                    "Пайплайн dag_sap_sales_orders_cdpos оркеструє щоденне інкрементальне вивантаження замовлень із SAP S/4HANA CDS C_SALESORDER_Q1 у шар stg.sap_vbak_vbap та фінальну вітрину mart.fact_orders.",
                    "Розклад запуску в Airflow: щодня о 05:15 UTC, цільовий час готовності вітрини до 06:00 UTC для оновлення Sales_Overview_Dataset.",
                ],
                bullets=[
                    "Ключ дедуплікації у Delta MERGE: order_id (рівень заголовка замовлення VBAK).",
                    "Вікно інкрементального захоплення змін (lookback window): останні 3 доби за полем LastChangeDateTime.",
                ],
            ),
            SectionSpec(
                heading="2. Діагностика розбіжностей гранулярності та затримок партицій",
                paragraphs=[
                    "Якщо сума виторгу в mart.fact_orders нижча за SAP Fiori Manage Sales Orders (кейс BUGS-41), інженер Data Pull перевіряє статус таски extract_sap_odata_delta та повноту партицій posting_month.",
                    "Якщо сума на DEV завищена у декілька разів (кейс BUGS-50), перевіряється відсутність некоректного join із позиціями VBAP без попередньої агрегації до order_id.",
                ],
                table_headers=["Симптом інциденту", "SQL перевірка у Databricks", "Дія відновлення (Remediation)"],
                table_rows=[
                    ["Заниження виторгу за місяць", "SELECT max(_ingested_at), count(*) FROM mart.fact_orders WHERE posting_ym='2025-03'", "Перезапуск backfill за діапазон дат у Airflow"],
                    ["Дублікати order_id після join", "SELECT order_id, count(*) FROM mart.fact_orders GROUP BY 1 HAVING count(*)>1", "Відкат коміту трансформації на DEV та MERGE по заголовку"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="RUNBOOK-DBX-002_inventory_snapshot_wh.html",
        fmt="html",
        doc_id="RUNBOOK-DBX-002",
        title="RUNBOOK-DBX-002: Daily Inventory Snapshot Pipeline (wh.inventory_snapshot)",
        version="2.0",
        date="2025-03-24",
        doc_type="runbook",
        report_id="RPT-INV-002",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Архітектура DAG dag_sap_inventory_daily",
                paragraphs=[
                    "Пайплайн dag_sap_inventory_daily реалізує специфікацію SPEC-OPS-007 v2.0 і формує щоденні партиції snapshot_date у таблиці wh.inventory_snapshot на основі CDS C_MATERIALSTOCK_V2.",
                    "Старт екстракту о 04:45 UTC, жорсткий дедлайн запису партиції — 05:30 UTC (максимальний SLA відновлення — 2 години).",
                ],
            ),
            SectionSpec(
                heading="2. Відновлення пропущених рухів запасів (Late SAP Postings)",
                paragraphs=[
                    "При зверненні типу BUGS-43 (у Fiori Stock Overview є вчорашні рухи, а wh.inventory_snapshot порожній за вчора) черговий інженер Data Pull виконує перевірку водяного знака екстрактора OData.",
                ],
                table_headers=["Крок Runbook", "Команда / Перевірка", "Очікуваний результат"],
                table_rows=[
                    ["1. Перевірка партиції", "SHOW PARTITIONS wh.inventory_snapshot", "Присутня дата current_date - 1"],
                    ["2. Перевірка stg шару", "SELECT count(*) FROM stg.sap_mard_marc WHERE load_date = current_date", "Кількість рядків > 0 по всіх активних WERKS"],
                    ["3. Ручний Backfill", "airflow dags trigger dag_sap_inventory_daily --conf '{\"snapshot_date\":\"YYYY-MM-DD\"}'", "Партиція записана, рефреш Inventory_Dataset виконано"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="RUNBOOK-DBX-003_customer_master_scd2.html",
        fmt="html",
        doc_id="RUNBOOK-DBX-003",
        title="RUNBOOK-DBX-003: Customer Master Sync and Soft-Delete Mapping",
        version="1.2",
        date="2025-02-14",
        doc_type="runbook",
        report_id="RPT-CUST-003",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Правила синхронізації C_CUSTOMER_MASTER -> mart.dim_customer",
                paragraphs=[
                    "Таблиця виміру mart.dim_customer оновлюється пайплайном dag_sap_customer_master щоночі о 03:30 UTC з підтримкою прапорця м'якого видалення is_deleted.",
                    "Записи ніколи не видаляються фізично (DELETE заборонено), щоб зберегти цілісність зовнішніх ключів в історичних фактах продажів.",
                ],
                table_headers=["Поле SAP KNA1 / CDS", "Поле mart.dim_customer", "Логіка трансформації"],
                table_rows=[
                    ["KUNNR", "customer_id", "Нормалізація ведучих нулів (LPAD 10)"],
                    ["LOEVM / CentralDeletionFlag", "is_deleted", "CASE WHEN LOEVM = 'X' THEN true ELSE false END"],
                    ["LAND1", "country_code", "ISO-2 код країни для звіту Customers by Region"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="RUNBOOK-DBX-004_profit_center_revenue_cogs.html",
        fmt="html",
        doc_id="RUNBOOK-DBX-004",
        title="RUNBOOK-DBX-004: Profit Center Revenue & COGS Marts Pipeline",
        version="1.3",
        date="2025-03-19",
        doc_type="runbook",
        report_id="RPT-FIN-004",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Формування mart.fact_revenue та mart.fact_cogs",
                paragraphs=[
                    "Пайплайн dag_sap_fi_margin_marts завантажує проводки Головної книги ACDOCA через C_PROFITCENTER_Q та розділяє їх на вітрини виторгу й собівартості відповідно до SPEC-FIN-030 v1.3.",
                    "Ключове правило класифікації: якщо поле TradingPartner (VBUND) у проводці SAP непорожнє, рядок маркується is_intercompany = true.",
                ],
                table_headers=["Діапазон рахунків GL", "Цільова таблиця", "Класифікація cost_type / rev_type"],
                table_rows=[
                    ["400000–489999", "mart.fact_revenue", "GROSS_REVENUE та SALES_DEDUCTIONS"],
                    ["500000–549999", "mart.fact_cogs", "DIRECT (пряма собівартість реалізації)"],
                    ["551000–552999", "mart.fact_cogs", "INBOUND_FREIGHT_EUR (додано до COGS у v1.3)"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="RUNBOOK-DBX-005_fx_rates_and_payments.html",
        fmt="html",
        doc_id="RUNBOOK-DBX-005",
        title="RUNBOOK-DBX-005: Incoming Payments and ECB FX Rates Pipeline",
        version="1.2",
        date="2025-04-06",
        doc_type="runbook",
        report_id="RPT-FX-005",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Одноразова конвертація валют у dag_sap_payments_fx",
                paragraphs=[
                    "Пайплайн dag_sap_payments_fx спочатку оновлює довідник курсів ЄЦБ ref.fx_rates о 04:00 UTC, після чого приєднує курс за датою оплати payment_date до вивантаження C_PAYMENTDOCUMENT.",
                    "Для вихідних та святкових днів застосовується останній доступний робочий курс (LOCF window lookback до 5 днів). Результат записується в mart.fact_payments.amount_eur.",
                ],
                bullets=[
                    "Якщо документ у SAP вже проведений у валюті EUR, коефіцієнт fx_rate_to_eur примусово дорівнює 1.000000.",
                    "Будь-яка спроба повторного множення на fx_rate у шарі Power BI порушує інваріант SPEC-FIN-041 v1.2.",
                ],
            ),
        ],
    ),
]
