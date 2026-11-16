# GLOSSARY-001: Analytics Ticket Copilot Domain Glossary

Doc ID: GLOSSARY-001 | Version: 2.0 | Effective Date: 2025-04-14 | Type: glossary | Report: PLATFORM-WIDE | Status: ACTIVE

## 1. Основні терміни, абревіатури та об'єкти платформи

Глосарій уніфікує термінологію між командами Financial Analysts, Report Development та Data Pull при розборі тікетів проєкту BUGS.

| Термін / Код | Розшифровка та роль у ланцюжку звітності |
| --- | --- |
| SAP Fiori / CDS View | Інтерфейс користувача та шар представлень S/4HANA (наприклад, C_SALESORDER_Q1, C_PROFITCENTER_Q) |
| Data Pull | Інженерна команда, відповідальна за інтеграцію SAP -> Databricks (Airflow + Spark Delta) |
| Parent / Child Model | Дворівнева архітектура датасетів Power BI (сертифіковане ядро + DirectQuery модель звіту) |
| RLS (Row-Level Security) | Обмеження видимості рядків датасету за роллю користувача (може виглядати як 'порожній звіт') |
| 4-Way Reconciliation | Обов'язкова звірка SAP vs Databricks vs Semantic Model vs Power BI проти чинної SPEC-* |
