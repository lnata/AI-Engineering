# Сквозной курсовой проект (кейсы 1–4)

**Тема:** Analytics Ticket Copilot — AI по Jira-тикетам отчётности  
**Цепочка данных (где может жить баг):**

```
SAP Fiori
  → Databricks tables
    → Parent semantic model
      → Child model (DirectQuery + своя логика)
        → RDL / Power BI report
```

Плюс сверка со **спецификацией** (financial analyst) и деплой **DEV → approval → PROD**.

| Кейс | Что делаем | Результат |
|------|------------|-----------|
| **1. Structured Extraction** | Грязный Jira → JSON по Pydantic; cloud vs local; версии промптов | Этот репозиторий + `REPORT.md` |
| **2. RAG** | Поиск по тикетам / спекам / reference; ответ со ссылкой на источник | Retrieval + QA-тесты |
| **3. Agent** | Анализ → сверка со спекой → найти звено цепочки → черновик фикса → комментарий в Jira | Multi-step tools |
| **4. Service** | API, auth, мониторинг, учёт стоимости | Demo Day |

Полное описание идеи: [`PROJECT.md`](PROJECT.md) · домен: [`DOMAIN.md`](DOMAIN.md)
