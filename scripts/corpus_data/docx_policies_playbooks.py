"""DOCX documents (Part A): Deployment policies, Triage, Reconciliation, and SLA playbooks."""

from __future__ import annotations

from scripts.corpus_data.schema import CorpusDocSpec, SectionSpec

_TRIAGE_SECTIONS = [
    SectionSpec(
        heading="1. Критерії розмежування Bug та Change Request у проєкті BUGS",
        paragraphs=[
            "Кожне звернення у Jira-проєкті BUGS класифікується за двома типами: Bug (невідповідність цифр затвердженій специфікації або розсинхронізація між SAP Fiori, Databricks і Power BI) та Change Request (цілеспрямована зміна бізнес-правил, формул або складу полів).",
            "Навіть якщо цифри у Power BI повністю збігаються з вітриною Databricks, але суперечать чинній спеці SPEC-* (наприклад, BUGS-42), тікет є повноцінним Bug із категорією spec_mismatch.",
        ],
        bullets=[
            "Data Mismatch: розбіжність SAP Fiori проти Databricks (зона відповідальності Data Pull).",
            "Transform / Filter / RLS Bug: вітрина коректна, але семантична модель або DAX спотворює результат (Report Developer).",
            "Change Request (CR): запит фінансового аналітика на нову розбивку або зміну логіки (наприклад, BUGS-46, BUGS-47, BUGS-48).",
        ],
    ),
    SectionSpec(
        heading="2. Матриця призначення відповідальних ролей (Ownership)",
        paragraphs=[
            "Для усунення затримок між командами кожен тікет отримує основного виконавця (primary_assignee_role) відповідно до підозрюваної ланки пайплайну.",
        ],
        table_headers=["Підозрювана ланка", "Primary Assignee Role", "Співвиконавці", "Обов'язкова перевірка"],
        table_rows=[
            ["SAP Fiori -> Databricks", "data_pull", "financial_analyst", "SAP CDS vs mart.* / wh.*"],
            ["Semantic Model / DAX / RLS", "report_developer", "financial_analyst", "Databricks SQL vs Power BI visual"],
            ["Ambiguous User Filter / CR", "financial_analyst", "report_developer, data_pull", "Узгодження періоду та версії SPEC-*"],
        ],
    ),
]

DOCX_POLICIES_PLAYBOOKS: list[CorpusDocSpec] = [
    CorpusDocSpec(
        filename="POL-DEP-001_v1.0_deployment_policy_legacy.docx",
        fmt="docx",
        doc_id="POL-DEP-001",
        title="POL-DEP-001: Deployment and Release Governance Policy (Legacy v1.0)",
        version="1.0",
        date="2024-01-15",
        doc_type="policy",
        report_id=None,
        is_latest=False,
        sections=[
            SectionSpec(
                heading="1. Статус застарілого регламенту деплою v1.0",
                paragraphs=[
                    "УВАГА: Редакція POL-DEP-001 v1.0 від 2024-01-15 скасована з 2025-04-01 у зв'язку з переходом на регламент v1.3.",
                    "У 2024 році регламент v1.0 дозволяв екстрений прямий хотфікс у середовище PROD без попередньої публікації на DEV за умови пост-фактум рев'ю протягом 48 годин.",
                ],
                table_headers=["Правило релізу", "Застаріла редакція v1.0 (2024)", "Чинний стандарт v1.3 (2025)"],
                table_rows=[
                    ["Прямий деплой у PROD", "Дозволявся для hotfix P1", "СУВОРО ЗАБОРОНЕНО без винятків"],
                    ["Погодження Financial Analyst", "Можливе пост-фактум за 48 год", "Обов'язкове ДО промоушену на PROD"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="POL-DEP-001_v1.3_deployment_and_reconciliation_policy.docx",
        fmt="docx",
        doc_id="POL-DEP-001",
        title="POL-DEP-001: Deployment and Reconciliation Governance Policy",
        version="1.3",
        date="2025-04-01",
        doc_type="policy",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Обов'язковий маршрут релізу змін (DEV -> Approval -> PROD)",
                paragraphs=[
                    "Регламент POL-DEP-001 (версія 1.3) встановлює безальтернативний порядок викатки виправлень багів та Change Requests для всіх звітів Power BI, семантичних моделей і пайплайнів Databricks.",
                    "Жодна зміна не може бути опублікована напряму в PROD в обхід середовища DEV або без зафіксованого погодження фінансового аналітика — навіть під час закриття місяця.",
                ],
                bullets=[
                    "Крок 1 (in_development): розробка фіксу у гілці або тестовому датасеті.",
                    "Крок 2 (deployed_to_dev): публікація на DEV та прогін контрольних звірок.",
                    "Крок 3 (pending_approval -> approved_for_prod): верифікація цифр Financial Analyst проти специфікації.",
                    "Крок 4 (deployed_to_prod): реліз у PROD із фінальною пост-деплойною звіркою.",
                ],
            ),
            SectionSpec(
                heading="2. Контрольні критерії виходу з кожного етапу",
                paragraphs=[
                    "Перехід між етапами фіксується у Jira-тікеті з прикріпленням протоколу звірки на DEV.",
                ],
                table_headers=["Етап", "Середовище", "Власник етапу", "Критерій завершення (Exit Criteria)"],
                table_rows=[
                    ["in_development", "feature/local", "report_developer / data_pull", "Код і міри готові до публікації на DEV"],
                    ["deployed_to_dev", "dev", "report_developer", "Зміни доступні на DEV; звірка виконана"],
                    ["approved_for_prod", "dev", "financial_analyst", "Явний апрув відповідності цифр спеці SPEC-*"],
                    ["deployed_to_prod", "prod", "report_developer", "Реліз у PROD та контрольна перевірка візуалів"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="PLAYBOOK-TRIAGE-001_v2.1_jira_bug_vs_cr_triage.docx",
        fmt="docx",
        doc_id="PLAYBOOK-TRIAGE-001",
        title="PLAYBOOK-TRIAGE-001: Jira Ticket Triage — Bug vs Change Request",
        version="2.1",
        date="2025-03-10",
        doc_type="playbook",
        report_id=None,
        is_latest=True,
        sections=_TRIAGE_SECTIONS,
    ),
    CorpusDocSpec(
        filename="PLAYBOOK-TRIAGE-001_v2.1_jira_bug_vs_cr_backup.docx",
        fmt="docx",
        doc_id="PLAYBOOK-TRIAGE-001",
        title="PLAYBOOK-TRIAGE-001: Jira Ticket Triage — Bug vs Change Request",
        version="2.1",
        date="2025-03-10",
        doc_type="playbook",
        report_id=None,
        is_latest=True,
        sections=_TRIAGE_SECTIONS,
        mirror_variant=True,
    ),
    CorpusDocSpec(
        filename="PLAYBOOK-RECON-002_v1.4_sap_dbx_pbi_reconciliation.docx",
        fmt="docx",
        doc_id="PLAYBOOK-RECON-002",
        title="PLAYBOOK-RECON-002: End-to-End Reconciliation Checklist",
        version="1.4",
        date="2025-03-18",
        doc_type="playbook",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Чотири контрольні точки звірки (4-Way Reconciliation)",
                paragraphs=[
                    "Для локалізації дефекту команда проходить ланцюг перевірок зверху вниз: від SAP Fiori до специфікації. Пропуск перевірки Report vs Specification заборонений, оскільки візуал може точно відтворювати помилкову логіку вітрини.",
                ],
                table_headers=["Перевірка", "Що порівнюємо", "Типова першопричина розбіжності"],
                table_rows=[
                    ["1. SAP Fiori vs Databricks", "Екстракт CDS view проти таблиці mart.* / wh.*", "Пропущена партиція Airflow, дубль join-ів"],
                    ["2. Databricks vs Semantic Model", "SQL-агрегат вітрини проти Parent/Child моделі", "Неоновлений датасет, фільтр імпорту"],
                    ["3. Semantic Model vs Power BI", "Міра датасету проти візуалу .pbix / RDL", "Visual-level фільтр, активний RLS, кеш"],
                    ["4. Power BI vs Specification", "Фактична формула звіту проти чинної SPEC-*", "Застаріла DAX-формула або неврахований виняток"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="PLAYBOOK-SLA-003_v1.2_incident_severity_month_close.docx",
        fmt="docx",
        doc_id="PLAYBOOK-SLA-003",
        title="PLAYBOOK-SLA-003: Incident Severity and Month-End Close SLA",
        version="1.2",
        date="2025-02-20",
        doc_type="playbook",
        report_id=None,
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Рівні пріоритетів та режим закриття періоду (Month-End Close)",
                paragraphs=[
                    "У робочі дні WD1–WD5 триває фінансове закриття місяця. Будь-яке викривлення сум на PROD у фінансових звітах RPT-SALES-001, RPT-FIN-004 або RPT-FX-005 отримує прапорець is_blocker = true та пріоритет Critical.",
                ],
                table_headers=["Пріоритет", "Час першої реакції", "Цільовий час фіксу на DEV", "Умова присвоєння"],
                table_rows=[
                    ["Critical (Blocker)", "15 хвилин", "2 години", "Викривлення фінансових цифр на PROD у WD1–WD5"],
                    ["High", "1 година", "6 годин", "Помилка фільтрації або пропущений інкремент даних"],
                    ["Medium", "4 години", "2 робочі дні", "Плановий Change Request або помилка фільтра користувача"],
                ],
            ),
        ],
    ),
]
