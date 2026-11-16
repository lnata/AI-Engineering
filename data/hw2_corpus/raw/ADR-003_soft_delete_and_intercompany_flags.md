# ADR-003: Standardized Boolean Flags is_deleted and is_intercompany

Doc ID: ADR-003 | Version: 1.1 | Effective Date: 2025-03-14 | Type: adr | Report: PLATFORM-WIDE | Status: ACTIVE

## 1. Уніфікація системних прапорців у вітринах mart.*

У SAP S/4HANA ознаки видалення та внутрішньогрупових операцій кодуються десятками технічних полів (LOEVM, VBUND, FKSTO). Передача сирих кодів SAP у Power BI провокувала помилки фільтрації (BUGS-42, BUGS-44).

Відтепер команда Data Pull трансформує ці коди на етапі побудови mart.* у два стандартні булеві поля: is_deleted (BOOLEAN NOT NULL) та is_intercompany (BOOLEAN NOT NULL).
