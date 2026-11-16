"""PDF specifications (Part A): Sales Revenue, Active Customers, and Gross Margin."""

from __future__ import annotations

from scripts.corpus_data.schema import CorpusDocSpec, SectionSpec

_GM_V13_SECTIONS = [
    SectionSpec(
        heading="1. Призначення та контур звітності",
        paragraphs=[
            "Специфікація SPEC-FIN-030 (версія 1.3) визначає єдиний корпоративний регла-\nмент розрахунку показника Gross Margin % у звіті Gross Margin Dashboard (Finance_Dev.pbix / Finance_Margin_Dataset, код звіту RPT-FIN-004).",
            "Джерелом первинних проводок є SAP Fiori застосунок Profit Center Analysis (CDS view C_PROFITCENTER_Q). Вивантаження у Databricks виконує команда Data Pull у вітрини mart.fact_revenue та mart.fact_cogs.",
        ],
        bullets=[
            "Власник специфікації (Financial Analyst): фінансовий контролінг маржинальності.",
            "Технічний власник вітрин: команда Data Pull (пайплайн dag_sap_fi_margin_marts).",
            "Контур публікації: обов'язкова валідація на DEV перед промоушеном на PROD.",
        ],
    ),
    SectionSpec(
        heading="2. Формула Gross Margin % та виключення оборотів",
        paragraphs=[
            "У версії 1.3 діє жорстке правило очищення виторгу та собівартості від внутрішньогрупових операцій: усі inter-\ncompany проводки (прапорець is_intercompany = true або заповнений код партнера VBUND у SAP) підлягають повному виключенню до агрегації.",
            "На відміну від застарілої редакції v1.0, у собівартість реалізованої продукції (COGS) обов'язково включаються витрати на вхідну логістику (inbound_freight_eur), а допустиме відхилення звірки SAP проти Databricks зменшено з 1.0% до 0.15%. Показник класифікується як управлінська non-GAAP метрика.",
        ],
        table_headers=["Компонент", "Об'єкт Databricks", "Фільтр / Правило", "Роль у формулі"],
        table_rows=[
            ["Net External Revenue", "mart.fact_revenue", "is_intercompany = false AND doc_status = 'POSTED'", "Чисельник та знаменник"],
            ["Direct COGS", "mart.fact_cogs", "is_intercompany = false AND cost_type = 'DIRECT'", "Віднімається у чисельнику"],
            ["Inbound Freight", "mart.fact_cogs", "cost_type = 'INBOUND_FREIGHT_EUR'", "Додається до COGS у v1.3"],
            ["Gross Margin %", "Finance_Margin_Dataset", "DIVIDE(Revenue - Total_COGS, Revenue)", "Цільовий KPI звіту"],
        ],
    ),
    SectionSpec(
        heading="3. Критерії приймання та типові помилки звірки",
        paragraphs=[
            "Перед передачею змін на затвердження фінансовому аналітику розробник звіту зобов'язаний звірити суму Net External Revenue та Gross Margin % між C_PROFITCENTER_Q, вітринами Databricks і візуалами Power BI у розрізі Profit Center за закритий місяць.",
            "Найчастіший дефект на DEV (див. кейс BUGS-42) виникає, коли DAX-міра у Finance_Dev.pbix ігнорує фільтр is_intercompany = false, хоча у вітрині mart.fact_revenue поле вже коректно розраховане.",
        ],
        bullets=[
            "Максимальна розбіжність між SAP Fiori та Databricks: не більше 0.15% по кожному Profit Center.",
            "Розбіжність між Databricks та Power BI при однакових фільтрах періоду: строго 0.00 EUR.",
            "Заборонено деплоїти виправлення DAX-міри напряму у PROD без регресійної звірки на DEV.",
        ],
    ),
]

FIN_SPECS_A: list[CorpusDocSpec] = [
    CorpusDocSpec(
        filename="SPEC-FIN-014_v1.3_sales_revenue_region_channel.pdf",
        fmt="pdf",
        doc_id="SPEC-FIN-014",
        title="SPEC-FIN-014: Sales Revenue by Region and Channel",
        version="1.3",
        date="2025-02-15",
        doc_type="kpi_spec",
        report_id="RPT-SALES-001",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Огляд звіту Sales Overview та джерел даних",
                paragraphs=[
                    "Специфікація SPEC-FIN-014 (версія 1.3) регла-\nментує розрахунок чистого виторгу за регіонами та каналами збуту у звіті Sales Overview (Sales_Overview_v3.pbix, датасет Sales_Overview_Dataset, код RPT-SALES-001).",
                    "Первинні замовлення формуються в SAP Fiori застосунку Manage Sales Orders на базі CDS view C_SALESORDER_Q1 та реплікуються у вітрини mart.fact_orders і mart.dim_region.",
                ],
                bullets=[
                    "Рівень гранулярності вітрини mart.fact_orders: заголовок замовлення (order header net value).",
                    "Валюта звітності: EUR після нормалізації в шарі Databricks.",
                    "Частота оновлення: щоденно о 06:00 UTC після завершення інкрементального екстракту SAP.",
                ],
            ),
            SectionSpec(
                heading="2. Правила агрегації та мапінг полів",
                paragraphs=[
                    "Критична вимога гранулярності: C_SALESORDER_Q1 повертає суму Netwr на рівні заголовка замовлення. Якщо пайплайн Data Pull виконує join позицій замовлення без дедуплікації ключів, виникає завищення суми (див. інцидент BUGS-50).",
                    "Усі скасовані замовлення (rejection_status = 'C') та внутрішні тестові замовлення (order_type = 'ZTEST') виключаються під час трансформації stg.sap_vbak_vbap -> mart.fact_orders.",
                ],
                table_headers=["Поле SAP CDS", "Колонка Databricks", "Правило трансформації", "Перевірка якості"],
                table_rows=[
                    ["SalesOrder", "mart.fact_orders.order_id", "PK рівня заголовка (UNIQUE)", "not_null + unique"],
                    ["NetAmountEUR", "mart.fact_orders.net_revenue_eur", "SUM лише по унікальному order_id", "Recon vs Fiori <= 0.05%"],
                    ["SalesOrganization", "mart.dim_region.region_code", "INNER JOIN на активний довідник регіонів", "referential_integrity"],
                    ["DistributionChannel", "mart.fact_orders.channel_code", "Мапінг 10->Direct, 20->Partner, 30->E-com", "accepted_values"],
                ],
            ),
            SectionSpec(
                heading="3. Контроль звірки між шарами пайплайну",
                paragraphs=[
                    "При розслідуванні розбіжностей на PROD (приклад: тікет BUGS-41, де SAP Fiori показував 1.31M EUR проти 1.24M EUR у mart.fact_orders) аналітик перевіряє затримку delta-партицій за датою проводки ERDAT.",
                    "Power BI звіт Sales_Overview_v3.pbix читає дані через Direct-Query із Child семантичної моделі без додаткових коефіцієнтів перерахунку.",
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-FIN-021_v1.1_active_customers_by_country.pdf",
        fmt="pdf",
        doc_id="SPEC-FIN-021",
        title="SPEC-FIN-021: Active Customers by Country",
        version="1.1",
        date="2025-01-25",
        doc_type="kpi_spec",
        report_id="RPT-CUST-003",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Визначення активної клієнтської бази",
                paragraphs=[
                    "Специфікація SPEC-FIN-021 (версія 1.1) встановлює правила підрахунку активних клієнтів за країнами у звіті Customers by Region (Customers_Prod.pbix, датасет Customers_Prod, код RPT-CUST-003).",
                    "Джерелом майстер-даних є SAP Fiori застосунок Customer Master (CDS view C_CUSTOMER_MASTER), який синхро-\nнізується у таблицю виміру mart.dim_customer.",
                ],
                bullets=[
                    "Активним вважається клієнт із прапорцем is_deleted = false та відсутнім блокуванням центрального архіву (LOEVM = '').",
                    "Технічні одноразові рахунки групи CPD (account_group = 'ZCPD') не входять до KPI Active Customers.",
                ],
            ),
            SectionSpec(
                heading="2. Фільтрація soft-deleted записів у Databricks та Power BI",
                paragraphs=[
                    "Вітрина mart.dim_customer зберігає повну історію клієнтів включно із soft-deleted записами для ретроспективних фінансових звітів. Тому семантична модель Customers_Prod та DAX-міра Active_Customer_Count зобов'язані явно накладати фільтр is_deleted = FALSE.",
                    "Відсутність цього фільтра у Power BI призводить до завищення кількості клієнтів на PROD відносно SAP Fiori та Databricks (типовий дефект описано в BUGS-44: 12040 замість 11802 по країні UA).",
                ],
                table_headers=["Шар системи", "Об'єкт / Міра", "Обов'язкова умова активності", "Відповідальна роль"],
                table_rows=[
                    ["SAP Fiori", "C_CUSTOMER_MASTER", "DeletionIndicator IS INITIAL AND BlockingCode = ''", "Financial Analyst"],
                    ["Databricks", "mart.dim_customer", "is_deleted = false AND account_group <> 'ZCPD'", "Data Pull"],
                    ["Power BI", "Customers_Prod.pbix", "CALCULATE(DISTINCTCOUNT(customer_id), is_deleted = FALSE())", "Report Developer"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-FIN-030_v1.0_gross_margin_rules_legacy.pdf",
        fmt="pdf",
        doc_id="SPEC-FIN-030",
        title="SPEC-FIN-030: Gross Margin % Calculation Rules (Legacy v1.0)",
        version="1.0",
        date="2024-04-10",
        doc_type="kpi_spec",
        report_id="RPT-FIN-004",
        is_latest=False,
        sections=[
            SectionSpec(
                heading="1. Загальні положення застарілої редакції v1.0",
                paragraphs=[
                    "УВАГА: Редакція SPEC-FIN-030 версії 1.0 від 2024-04-10 втратила чинність після впровадження версії 1.3 у березні 2025 року та зберігається виключно для аудиту історичних періодів 2024 року.",
                    "Документ описував первинний алгоритм розрахунку Gross Margin % для звіту Gross Margin Dashboard (Finance_Dev.pbix, код RPT-FIN-004) на базі C_PROFITCENTER_Q.",
                ],
            ),
            SectionSpec(
                heading="2. Історична формула v1.0 та застарілі пороги звірки",
                paragraphs=[
                    "Як і в наступних редакціях, базове правило вимагало виключати inter-\ncompany обороти з виторгу. Проте у версії 1.0 витрати на вхідну доставку (inbound_freight_eur) НЕ включалися до COGS і обліковувалися окремо в OPEX.",
                    "Крім того, у версії 1.0 дозволялося враховувати попередні (provisional) квартальні ребейти за оцінкою аналітика, а допустимий поріг розбіжності між SAP Fiori та Databricks становив 1.00%.",
                ],
                table_headers=["Параметр", "Правило у застарілій v1.0 (2024)", "Статус"],
                table_rows=[
                    ["Intercompany Revenue", "Виключається (is_intercompany = false)", "Збережено у v1.3"],
                    ["Inbound Freight EUR", "Не входить до COGS (списується в OPEX)", "СКАСОВАНО у v1.3"],
                    ["Provisional Rebates", "Дозволено оціночне коригування в DAX", "СКАСОВАНО у v1.3"],
                    ["Поріг звірки SAP vs DBX", "До 1.00% на рівень Profit Center", "ЗАМІНЕНО на 0.15% у v1.3"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-FIN-030_v1.3_gross_margin_rules.pdf",
        fmt="pdf",
        doc_id="SPEC-FIN-030",
        title="SPEC-FIN-030: Gross Margin % Calculation Rules",
        version="1.3",
        date="2025-03-15",
        doc_type="kpi_spec",
        report_id="RPT-FIN-004",
        is_latest=True,
        sections=_GM_V13_SECTIONS,
    ),
    CorpusDocSpec(
        filename="SPEC-FIN-030_v1.3_gross_margin_rules_mirror.pdf",
        fmt="pdf",
        doc_id="SPEC-FIN-030",
        title="SPEC-FIN-030: Gross Margin % Calculation Rules",
        version="1.3",
        date="2025-03-15",
        doc_type="kpi_spec",
        report_id="RPT-FIN-004",
        is_latest=True,
        sections=_GM_V13_SECTIONS,
        header_banner="INTERNAL ANALYTICS KB — ARCHIVE MIRROR COPY",
        mirror_variant=True,
    ),
]
