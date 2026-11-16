"""Markdown documents: ADRs, domain glossary, platform release notes, and analyst FAQ."""

from __future__ import annotations

from scripts.corpus_data.schema import CorpusDocSpec, SectionSpec

MARKDOWN_DOCS: list[CorpusDocSpec] = [
    CorpusDocSpec(
        filename="ADR-001_semantic_model_parent_child_split.md",
        fmt="md",
        doc_id="ADR-001",
        title="ADR-001: Two-Tier Parent and Child Semantic Models in Power BI",
        version="1.1",
        date="2025-01-20",
        doc_type="adr",
        report_id=None,
        is_latest=True,
        utf8_bom=True,
        sections=[
            SectionSpec(
                heading="1. Контекст та прийняте архітектурне рішення",
                paragraphs=[
                    "До 2025 року кожен .pbix звіт мав власну копію імпортованих таблиць Databricks, що призводило до розбіжностей базових формул виторгу між департаментами.",
                    "Прийнято рішення розділити семантичний шар на єдину сертифіковану Parent модель (Import / DirectLake з Databricks) та тонкі Child моделі у режимі DirectQuery для конкретних звітів та RDL.",
                ],
                bullets=[
                    "Базові виміри (dim_region, dim_customer, dim_profit_center) та RLS адмініструються тільки в Parent моделі.",
                    "Департаментські міри додаються в Child моделях виключно за наявності затвердженої специфікації SPEC-*.",
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="ADR-002_single_fx_conversion_in_databricks.md",
        fmt="md",
        doc_id="ADR-002",
        title="ADR-002: Single Point of Currency Conversion in Databricks Marts",
        version="1.2",
        date="2025-04-04",
        doc_type="adr",
        report_id="RPT-FX-005",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Відмова від перерахунку курсів валют у DAX",
                paragraphs=[
                    "Аналіз інцидентів у звітах продажів та платежів показав, що дублювання логіки валютного перерахунку між SQL і DAX неминуче призводить до подвійної конвертації або розбіжності дат курсу.",
                    "Затверджено архітектурний інваріант: перерахунок у EUR виконується один раз у шарі mart.* Databricks на основі таблиці ref.fx_rates. Усі семантичні моделі Power BI споживають готові колонки *_eur.",
                ],
                table_headers=["Критерій", "Перерахунок у DAX (Відхилено)", "Перерахунок у Databricks (Прийнято)"],
                table_rows=[
                    ["Ризик подвійного курсу", "Високий (інцидент BUGS-49)", "Мінімальний при забороні fx_rate у DAX"],
                    ["Швидкість візуалів Power BI", "Повільна ітерація SUMX по днях", "Миттєвий SUM по преагрегованій колонці"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="ADR-003_soft_delete_and_intercompany_flags.md",
        fmt="md",
        doc_id="ADR-003",
        title="ADR-003: Standardized Boolean Flags is_deleted and is_intercompany",
        version="1.1",
        date="2025-03-14",
        doc_type="adr",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Уніфікація системних прапорців у вітринах mart.*",
                paragraphs=[
                    "У SAP S/4HANA ознаки видалення та внутрішньогрупових операцій кодуються десятками технічних полів (LOEVM, VBUND, FKSTO). Передача сирих кодів SAP у Power BI провокувала помилки фільтрації (BUGS-42, BUGS-44).",
                    "Відтепер команда Data Pull трансформує ці коди на етапі побудови mart.* у два стандартні булеві поля: is_deleted (BOOLEAN NOT NULL) та is_intercompany (BOOLEAN NOT NULL).",
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="GLOSSARY-001_analytics_reporting_terms.md",
        fmt="md",
        doc_id="GLOSSARY-001",
        title="GLOSSARY-001: Analytics Ticket Copilot Domain Glossary",
        version="2.0",
        date="2025-04-14",
        doc_type="glossary",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Основні терміни, абревіатури та об'єкти платформи",
                paragraphs=[
                    "Глосарій уніфікує термінологію між командами Financial Analysts, Report Development та Data Pull при розборі тікетів проєкту BUGS.",
                ],
                table_headers=["Термін / Код", "Розшифровка та роль у ланцюжку звітності"],
                table_rows=[
                    ["SAP Fiori / CDS View", "Інтерфейс користувача та шар представлень S/4HANA (наприклад, C_SALESORDER_Q1, C_PROFITCENTER_Q)"],
                    ["Data Pull", "Інженерна команда, відповідальна за інтеграцію SAP -> Databricks (Airflow + Spark Delta)"],
                    ["Parent / Child Model", "Дворівнева архітектура датасетів Power BI (сертифіковане ядро + DirectQuery модель звіту)"],
                    ["RLS (Row-Level Security)", "Обмеження видимості рядків датасету за роллю користувача (може виглядати як 'порожній звіт')"],
                    ["4-Way Reconciliation", "Обов'язкова звірка SAP vs Databricks vs Semantic Model vs Power BI проти чинної SPEC-*"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="RELEASE-NOTES-2025-Q1_reporting_platform.md",
        fmt="md",
        doc_id="RELEASE-NOTES-2025-Q1",
        title="RELEASE-NOTES-2025-Q1: Analytics Reporting Platform Quarterly Changes",
        version="1.0",
        date="2025-04-02",
        doc_type="release_notes",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Зведення оновлених специфікацій та регламентів у Q1 2025",
                paragraphs=[
                    "Протягом першого кварталу 2025 року виведено з обігу три застарілі специфікації v1.0 та оновлено корпоративний регламент деплою.",
                ],
                table_headers=["Документ", "Застаріла версія", "Чинна версія", "Ключова зміна"],
                table_rows=[
                    ["SPEC-FIN-030", "v1.0 (2024-04-10)", "v1.3 (2025-03-15)", "Додано inbound_freight_eur до COGS; поріг звірки 0.15%"],
                    ["SPEC-OPS-007", "v1.0 (2024-02-18)", "v2.0 (2025-03-22)", "Ранковий зріз 05:30 UTC, додано in_transit_qty, SLA 2 год"],
                    ["POL-DEP-001", "v1.0 (2024-01-15)", "v1.3 (2025-04-01)", "Повна заборона прямих hotfix у PROD без DEV та FA апруву"],
                    ["SPEC-FIN-041", "v1.0 (2024-05-20)", "v1.2 (2025-04-05)", "Одноразова конвертація EUR на payment_date у Databricks"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="FAQ-ANALYSTS-001_common_fiori_vs_pbi_questions.md",
        fmt="md",
        doc_id="FAQ-ANALYSTS-001",
        title="FAQ-ANALYSTS-001: Troubleshooting User Discrepancies (SAP Fiori vs Power BI)",
        version="1.3",
        date="2025-04-11",
        doc_type="faq",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Чому цифри користувача у SAP Fiori відрізняються від дашборду без наявності бага?",
                paragraphs=[
                    "Близько 25% вхідних звернень у черзі BUGS спричинені неузгодженими параметрами вибірки на боці бізнес-користувача, проте кожне таке звернення все одно проходить базову 4-рівневу верифікацію.",
                ],
                bullets=[
                    "Різні типи періодів: у FX_Revenue.pbix обрано Payment Period, тоді як у SAP Fiori користувач фільтрує Posting Period (кейс BUGS-45).",
                    "Локальна валюта проти EUR: у Fiori обрано валюту компанії UAH/USD замість звітної валюти групи EUR.",
                    "Активний RLS або збережений персональний bookmark у Power BI Service, що відсікає частину заводів або регіонів.",
                ],
            ),
        ],
    ),
]
