# Сквозной курсовой проект (кейсы 1–4)

**Тема:** AI-система для тикетов отчётности **SAP Fiori → Databricks → Power BI**
(баги + change requests, сверка с спецификацией, деплой DEV → approval → PROD).

| Кейс | Что делаем | Результат |
|------|------------|-----------|
| **1. Structured Extraction** (сейчас) | Из «грязных» Jira-текстов → валидный JSON по Pydantic; сравнение cloud vs local; версия промптов | Этот репозиторий + `REPORT.md` |
| **2. RAG** | Поиск по тикетам / спекам / reference-данным; ответы со ссылкой на источник; тесты качества retrieval | Индекс + QA-эндпоинт поверх `data/` |
| **3. Agent** | Агент с инструментами: найти похожие баги, предложить assignee/роль, проверить checklist сверки, черновик deploy path | Multi-step tool loop |
| **4. Service** | API, auth, мониторинг, учёт стоимости токенов; Demo Day | Production-like сервис |

Домен и роли: [`DOMAIN.md`](DOMAIN.md).
