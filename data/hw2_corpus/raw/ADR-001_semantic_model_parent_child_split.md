# ADR-001: Two-Tier Parent and Child Semantic Models in Power BI

Doc ID: ADR-001 | Version: 1.1 | Effective Date: 2025-01-20 | Type: adr | Report: PLATFORM-WIDE | Status: ACTIVE

## 1. Контекст та прийняте архітектурне рішення

До 2025 року кожен .pbix звіт мав власну копію імпортованих таблиць Databricks, що призводило до розбіжностей базових формул виторгу між департаментами.

Прийнято рішення розділити семантичний шар на єдину сертифіковану Parent модель (Import / DirectLake з Databricks) та тонкі Child моделі у режимі DirectQuery для конкретних звітів та RDL.

- Базові виміри (dim_region, dim_customer, dim_profit_center) та RLS адмініструються тільки в Parent моделі.
- Департаментські міри додаються в Child моделях виключно за наявності затвердженої специфікації SPEC-*.
