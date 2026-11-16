"""DOCX documents (Part B): Power BI dashboard and semantic model architecture guides."""

from __future__ import annotations

from scripts.corpus_data.schema import CorpusDocSpec, SectionSpec

DOCX_BI_GUIDES: list[CorpusDocSpec] = [
    CorpusDocSpec(
        filename="GUIDE-PBI-001_v1.5_sales_overview_dashboard.docx",
        fmt="docx",
        doc_id="GUIDE-PBI-001",
        title="GUIDE-PBI-001: Sales Overview Power BI Technical Guide",
        version="1.5",
        date="2025-03-05",
        doc_type="bi_guide",
        report_id="RPT-SALES-001",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Структура файлу Sales_Overview_v3.pbix та датасету",
                paragraphs=[
                    "Звіт Sales Overview (код RPT-SALES-001, файл Sales_Overview_v3.pbix) підключений у режимі DirectQuery до дочірньої моделі Sales_Overview_Dataset, яка наслідує базові таблиці mart.fact_orders та mart.dim_region із корпоративної Parent моделі.",
                    "Власником розробки звіту є команда Report Development, бізнес-власником — Financial Analysts (специфікація SPEC-FIN-014 v1.3).",
                ],
                bullets=[
                    "Базова міра Net Sales EUR обчислює SUM(fact_orders[net_revenue_eur]) без локальних валютних коефіцієнтів.",
                    "У версії v3 розріз каналу збуту прихований у візуалах до реалізації Change Request BUGS-46 (перехід на SPEC-FIN-014 v1.4).",
                ],
            ),
            SectionSpec(
                heading="2. Ключові DAX-міри та відомі обмеження",
                paragraphs=[
                    "Усі візуали головної сторінки використовують календар dim_calendar за полем order_posting_date.",
                ],
                table_headers=["DAX Міра", "Вираз / Джерело", "Правило валідації"],
                table_rows=[
                    ["Net Sales EUR", "SUM('mart_fact_orders'[net_revenue_eur])", "Збіг із C_SALESORDER_Q1 на рівні заголовків"],
                    ["Orders Count", "DISTINCTCOUNT('mart_fact_orders'[order_id])", "Захист від дублювання позицій замовлення"],
                    ["YoY Growth %", "DIVIDE([Net Sales EUR] - [Net Sales PY], [Net Sales PY])", "Порожнє значення при нульовій базі PY"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="GUIDE-PBI-002_v1.3_gross_margin_dashboard.docx",
        fmt="docx",
        doc_id="GUIDE-PBI-002",
        title="GUIDE-PBI-002: Gross Margin Dashboard Power BI Guide",
        version="1.3",
        date="2025-03-25",
        doc_type="bi_guide",
        report_id="RPT-FIN-004",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Налаштування Finance_Dev.pbix та семантичної моделі маржі",
                paragraphs=[
                    "Звіт Gross Margin Dashboard (RPT-FIN-004, робочий файл Finance_Dev.pbix, датасет Finance_Margin_Dataset) реалізує вимоги актуальної специфікації SPEC-FIN-030 v1.3.",
                    "Модель об'єднує вітрини mart.fact_revenue та mart.fact_cogs через спільні виміри dim_profit_center і dim_calendar.",
                ],
            ),
            SectionSpec(
                heading="2. Обов'язковий фільтр Intercompany та налаштування RLS",
                paragraphs=[
                    "Кожна базова DAX-міра у Finance_Margin_Dataset повинна містити предикат 'mart_fact_revenue'[is_intercompany] = FALSE() та 'mart_fact_cogs'[is_intercompany] = FALSE(). Перенесення цього фільтра лише на рівень окремого візуалу заборонено, оскільки експорт у Excel або RDL ігнорує візуальні фільтри.",
                ],
                table_headers=["Елемент моделі", "Технічне правило", "Пов'язана вимога"],
                table_rows=[
                    ["External Revenue EUR", "CALCULATE(SUM(revenue_eur), is_intercompany = FALSE())", "SPEC-FIN-030 v1.3 розд. 2"],
                    ["Total COGS EUR", "Direct COGS + Inbound Freight EUR (is_intercompany = FALSE())", "Оновлення формули v1.3"],
                    ["Profit Center RLS", "Фільтрація dim_profit_center за AD-групою регіонального контролера", "Може приховувати рядки без прав"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="GUIDE-PBI-003_v1.2_fx_revenue_and_customers.docx",
        fmt="docx",
        doc_id="GUIDE-PBI-003",
        title="GUIDE-PBI-003: FX Revenue and Customers by Region BI Guide",
        version="1.2",
        date="2025-04-08",
        doc_type="bi_guide",
        report_id="RPT-FX-005",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Особливості звіту FX_Revenue.pbix (RPT-FX-005)",
                paragraphs=[
                    "Звіт FX_Revenue.pbix працює на датасеті FX_Revenue_Dataset і відображає вхідні валютні надходження відповідно до SPEC-FIN-041 v1.2.",
                    "На сторінці звіту виведено два незалежні слайсери календарів: Payment Period та SAP Posting Period. Невідповідність обраного користувачем слайсера у Fiori та PBI є типовою причиною хибних звернень (див. BUGS-45).",
                ],
                bullets=[
                    "Категорично заборонено створювати розрахункові колонки або DAX-міри, що множать amount_eur на ref_fx_rates[fx_rate].",
                    "Для звіту Customers_Prod.pbix (RPT-CUST-003) на рівні всіх сторінок діє обов'язковий предикат dim_customer[is_deleted] = FALSE().",
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="GUIDE-SEMANTIC-004_v2.0_parent_child_directquery_rls.docx",
        fmt="docx",
        doc_id="GUIDE-SEMANTIC-004",
        title="GUIDE-SEMANTIC-004: Parent/Child Semantic Models and RDL Architecture",
        version="2.0",
        date="2025-03-28",
        doc_type="bi_guide",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Дворівнева архітектура семантичних моделей Power BI",
                paragraphs=[
                    "Корпоративна платформа аналітики розділяє шар даних Power BI на сертифіковану Parent модель (пряме читання вітрин Databricks SQL Warehouse) та спеціалізовані Child моделі (DirectQuery до Parent моделі + департаментські DAX-міри).",
                    "Пагіновані звіти RDL та інтерактивні .pbix підключаються виключно до відповідної Child моделі.",
                ],
                table_headers=["Шар Power BI", "Режим підключення", "Що дозволено змінювати", "Типовий клас багів"],
                table_rows=[
                    ["Parent Semantic Model", "Import / DirectLake з Databricks", "Зв'язки таблиць, базові KPI, RLS ролі", "Застарілий розклад оновлення датасету"],
                    ["Child Semantic Model", "DirectQuery до Parent моделі", "Локальні DAX-міри, форматування", "Помилкова переозначена DAX-формула"],
                    ["PBIX / RDL Report", "Live Connect до Child моделі", "Візуали, слайсери, параметри сторінки", "Прихований visual filter або обрізка RDL"],
                ],
            ),
        ],
    ),
]
