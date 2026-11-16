# FAQ-ANALYSTS-001: Troubleshooting User Discrepancies (SAP Fiori vs Power BI)

Doc ID: FAQ-ANALYSTS-001 | Version: 1.3 | Effective Date: 2025-04-11 | Type: faq | Report: PLATFORM-WIDE | Status: ACTIVE

## 1. Чому цифри користувача у SAP Fiori відрізняються від дашборду без наявності бага?

Близько 25% вхідних звернень у черзі BUGS спричинені неузгодженими параметрами вибірки на боці бізнес-користувача, проте кожне таке звернення все одно проходить базову 4-рівневу верифікацію.

- Різні типи періодів: у FX_Revenue.pbix обрано Payment Period, тоді як у SAP Fiori користувач фільтрує Posting Period (кейс BUGS-45).
- Локальна валюта проти EUR: у Fiori обрано валюту компанії UAH/USD замість звітної валюти групи EUR.
- Активний RLS або збережений персональний bookmark у Power BI Service, що відсікає частину заводів або регіонів.
