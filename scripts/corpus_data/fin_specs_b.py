"""PDF specifications (Part B): FX Conversion, Inventory, OTIF, and Revenue specs."""

from __future__ import annotations

from scripts.corpus_data.schema import CorpusDocSpec, SectionSpec

FIN_SPECS_B: list[CorpusDocSpec] = [
    CorpusDocSpec(
        filename="SPEC-FIN-041_v1.0_fx_conversion_legacy.pdf",
        fmt="pdf",
        doc_id="SPEC-FIN-041",
        title="SPEC-FIN-041: FX Conversion Timing and Rates (Legacy v1.0)",
        version="1.0",
        date="2024-05-20",
        doc_type="kpi_spec",
        report_id="RPT-FX-005",
        is_latest=False,
        sections=[
            SectionSpec(
                heading="1. Статус застарілої редакції SPEC-FIN-041 v1.0",
                paragraphs=[
                    "УВАГА: Версія 1.0 специфікації SPEC-FIN-041 від 2024-05-20 є архівною та замінена версією 1.2 від 2025-04-05. Використання правил v1.0 у поточних релізах FX_Revenue.pbix заборонено.",
                    "У 2024 році вітрина mart.fact_payments зберігала суми у валюті транзакції без перерахунку в EUR.",
                ],
            ),
            SectionSpec(
                heading="2. Застарілий механізм конвертації у DAX за середньомісячним курсом",
                paragraphs=[
                    "У редакції v1.0 валютна конвер-\nтація виконувалася безпосередньо в DAX-мірах звіту FX_Revenue.pbix шляхом множення суми платежу на середньомісячний курс ЄЦБ (monthly average rate).",
                    "Після міграції вітрини mart.fact_payments на перерахунок у EUR на боці Databricks збереження старої DAX-формулі спричинило критичні інциденти подвійної конвертації (див. BUGS-49).",
                ],
                table_headers=["Параметр FX", "Правило у застарілій v1.0", "Чинне правило у v1.2"],
                table_rows=[
                    ["Точка перерахунку", "Power BI DAX measure", "Тільки Databricks mart.fact_payments"],
                    ["Тип курсу", "Середньомісячний курс (Monthly Avg)", "Денний спот-курс ЄЦБ на payment_date"],
                    ["Валюта у mart.fact_payments", "Оригінальна валюта документа", "Нормалізована сума amount_eur"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-FIN-041_v1.2_fx_conversion_timing_rates.pdf",
        fmt="pdf",
        doc_id="SPEC-FIN-041",
        title="SPEC-FIN-041: FX Conversion Timing and Rates",
        version="1.2",
        date="2025-04-05",
        doc_type="kpi_spec",
        report_id="RPT-FX-005",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Єдиний стандарт валютної конвертації у FX Revenue",
                paragraphs=[
                    "Специфікація SPEC-FIN-041 (версія 1.2) визначає правила перерахунку вхідних платежів у звіті FX Revenue (FX_Revenue.pbix, датасет FX_Revenue_Dataset, код RPT-FX-005).",
                    "Первинні документи надходять із SAP Fiori застосунку Incoming Payments (CDS view C_PAYMENTDOCUMENT) та збагачуються курсами з довідника ref.fx_rates при формуванні вітрини mart.fact_payments.",
                ],
                bullets=[
                    "Конвер-\nтація в базову валюту EUR виконується РІВНО ОДИН РАЗ на етапі побудови mart.fact_payments.",
                    "Курс визначається за датою фактичної оплати (payment_date / AUGDT), а не за датою виставлення інвойсу (якщо не затверджено окремий CR, див. BUGS-47).",
                ],
            ),
            SectionSpec(
                heading="2. Заборона повторного множення на fx_rate у Power BI",
                paragraphs=[
                    "Поле mart.fact_payments.amount_eur вже містить фінальну суму в EUR. Семантична модель FX_Revenue_Dataset та візуали FX_Revenue.pbix повинні агрегувати SUM(amount_eur) без повторного множення на ref.fx_rates.",
                    "При звірці користувацьких звернень (див. BUGS-45) аналітик насамперед перевіряє ідентичність фільтра posting period у SAP Fiori та Power BI.",
                ],
                table_headers=["Колонка / Об'єкт", "Шар", "Правило обчислення", "Контроль інваріанта"],
                table_rows=[
                    ["amount_doc_curr", "stg.sap_bsad_payments", "Сума у валюті документа SAP", "Збіг із C_PAYMENTDOCUMENT"],
                    ["fx_rate_to_eur", "ref.fx_rates", "Курс ЄЦБ на дату payment_date (fallback T-1)", "not_null AND > 0"],
                    ["amount_eur", "mart.fact_payments", "ROUND(amount_doc_curr * fx_rate_to_eur, 2)", "Єдиний перерахунок у пайплайні"],
                    ["FX Revenue EUR", "FX_Revenue.pbix", "SUM(mart.fact_payments[amount_eur])", "Заборонено множити на fx_rate вдруге"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-OPS-007_v1.0_daily_inventory_legacy.pdf",
        fmt="pdf",
        doc_id="SPEC-OPS-007",
        title="SPEC-OPS-007: Daily Inventory by Plant (Legacy v1.0)",
        version="1.0",
        date="2024-02-18",
        doc_type="kpi_spec",
        report_id="RPT-INV-002",
        is_latest=False,
        sections=[
            SectionSpec(
                heading="1. Архівна специфікація складських залишків v1.0",
                paragraphs=[
                    "УВАГА: Редакція SPEC-OPS-007 v1.0 від 2024-02-18 виведена з експлуатації після переходу на версію 2.0 у березні 2025 року.",
                    "У версії 1.0 знімок залишків wh.inventory_snapshot формувався раз на добу о 23:00 UTC без урахування товарів у дорозі (in-transit stock) та мав сервісний SLA затримки оновлення до 8 годин.",
                ],
                table_headers=["Параметр SLA / Логіки", "Застаріла v1.0 (2024)", "Актуальна v2.0 (2025)"],
                table_rows=[
                    ["Час фіксації знімка", "23:00 UTC (нічний батч)", "05:30 UTC (ранковий зріз до відкриття змін)"],
                    ["Запаси в дорозі (In-Transit)", "Не враховувалися", "Включено окремою колонкою in_transit_qty"],
                    ["Максимальний SLA затримки", "8 годин", "2 години з автоматичним алертингом"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-OPS-007_v2.0_daily_inventory_by_plant.pdf",
        fmt="pdf",
        doc_id="SPEC-OPS-007",
        title="SPEC-OPS-007: Daily Inventory by Plant",
        version="2.0",
        date="2025-03-22",
        doc_type="kpi_spec",
        report_id="RPT-INV-002",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Призначення звіту Inventory Snapshot (v2.0)",
                paragraphs=[
                    "Специфікація SPEC-OPS-007 (версія 2.0) визначає правила формування щоденного зрізу запасів за заводами (plants) та складами у звіті Inventory Snapshot (Inventory_Dev.pbix / Inventory_Dataset, код RPT-INV-002).",
                    "Дані вивантажуються із SAP Fiori застосунку Stock Overview (CDS view C_MATERIALSTOCK_V2) у таблицю wh.inventory_snapshot щоранку до 05:30 UTC із жорстким SLA затримки не більше 2 годин.",
                ],
            ),
            SectionSpec(
                heading="2. Категорії запасів та контроль повноти партицій",
                paragraphs=[
                    "У версії 2.0 загальний доступний запас (Total Plant Stock) охоплює вільний залишок (unrestricted_qty), запаси на контролі якості (quality_inspection_qty) та міжзаводський транзит (in_transit_qty). Заблокований брак (blocked_qty) відображається окремо й не додається до доступного до відвантаження залишку.",
                    "Якщо в wh.inventory_snapshot відсутня партиція snapshot_date за вчорашній день при наявності рухів у Fiori Stock Overview (див. BUGS-43), інцидент класифікується як збій Data Pull.",
                ],
                table_headers=["Поле wh.inventory_snapshot", "Джерело C_MATERIALSTOCK_V2", "Включення у Available Stock", "Примітка"],
                table_rows=[
                    ["unrestricted_qty", "MatlWrhsStkQtyInMatlBaseUnit (01)", "Так (+)", "Основний доступний залишок"],
                    ["in_transit_qty", "StockInTransitQty (06)", "Так (+) у v2.0", "Додано у релізі v2.0"],
                    ["blocked_qty", "BlockedStockQty (07)", "Ні (окремий KPI)", "Карантин / списання"],
                    ["plant_code", "Plant (WERKS)", "Ключ групування", "CR BUGS-48 планує ієрархію заводів у v2.1"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-OPS-011_v1.2_order_fulfillment_otif.pdf",
        fmt="pdf",
        doc_id="SPEC-OPS-011",
        title="SPEC-OPS-011: Order Fulfillment and OTIF SLA Rules",
        version="1.2",
        date="2025-02-28",
        doc_type="kpi_spec",
        report_id="RPT-OPS-006",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Визначення метрики OTIF (On-Time In-Full)",
                paragraphs=[
                    "Специфікація SPEC-OPS-011 (версія 1.2) описує логіку розрахунку логістичного KPI OTIF % на базі SAP CDS C_DELIVERYDOC_Q та вітрини Databricks mart.fact_deliveries.",
                    "Замовлення вважається виконаним за стандартом OTIF лише за одночасного виконання обох умов: фактична дата відвантаження не пізніше узгодженої дати клієнта, а доставлена кількість становить не менше 99.0% замовленого обсягу.",
                ],
                table_headers=["Метрика", "Формула у mart.fact_deliveries", "Цільовий поріг SLA"],
                table_rows=[
                    ["On-Time %", "actual_gi_date <= requested_delivery_date", ">= 96.0%"],
                    ["In-Full %", "delivered_qty / ordered_qty >= 0.99", ">= 97.5%"],
                    ["OTIF %", "is_on_time = true AND is_in_full = true", ">= 94.0% (включно з cross-dock)"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-REV-012_v1.4_net_revenue_waterfall.pdf",
        fmt="pdf",
        doc_id="SPEC-REV-012",
        title="SPEC-REV-012: Gross-to-Net Revenue and Rebate Waterfall",
        version="1.4",
        date="2025-03-30",
        doc_type="kpi_spec",
        report_id="RPT-REV-007",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Відмінність Net Revenue Waterfall від Gross Margin та Sales Overview",
                paragraphs=[
                    "Специфікація SPEC-REV-012 (версія 1.4) визначає розрахунок каскаду Gross-to-Net Revenue на основі інвойсів SAP Billing (C_BILLINGDOC_Q -> mart.fact_billing), а не замовлень C_SALESORDER_Q1 чи маржинальності C_PROFITCENTER_Q.",
                    "Аналітики не повинні плутати цей звіт зі SPEC-FIN-014 (де виторг рахується за замовленнями) або зі SPEC-FIN-030 (де від виторгу віднімається собівартість COGS).",
                ],
                table_headers=["Етап каскаду", "Код умови SAP", "Дія у mart.fact_billing", "Вплив на Net Revenue"],
                table_rows=[
                    ["Gross Billed Revenue", "PR00", "Базова сума виставлених інвойсів", "Стартова база (+100%)"],
                    ["On-Invoice Discounts", "K004 / K007", "Торгові знижки у рядку інвойсу", "Зменшує виторг (-)"],
                    ["Contractual Rebates", "BO01 / BO02", "Нараховані ретро-бонуси дистриб'юторам", "Зменшує виторг (-)"],
                    ["Credit Memos & Returns", "G2 / RE", "Підтверджені повернення товару", "Фінальний Net Billed Revenue"],
                ],
            ),
        ],
    ),
    CorpusDocSpec(
        filename="SPEC-REV-019_v1.1_deferred_revenue_recognition.pdf",
        fmt="pdf",
        doc_id="SPEC-REV-019",
        title="SPEC-REV-019: Deferred Revenue and Subscription Recognition",
        version="1.1",
        date="2025-04-12",
        doc_type="kpi_spec",
        report_id="RPT-REV-008",
        is_latest=True,
        sections=[
            SectionSpec(
                heading="1. Графік визнання доходів майбутніх періодів (IFRS-15)",
                paragraphs=[
                    "Специфікація SPEC-REV-019 (версія 1.1) встановлює правила амортизації річних сервісних контрактів із SAP Revenue Accounting (CDS C_RARCONTRACT_Q) у вітрину mart.fact_deferred_rev.",
                    "Агре-\nгація визнаного виторгу виконується пропорційно кількості календарних днів активного сервісного періоду, тоді як невизнаний залишок обліковується на балансі contract_liability_eur.",
                ],
                table_headers=["Показник", "Джерело Databricks", "Правило визнання за місяць"],
                table_rows=[
                    ["Recognized Revenue EUR", "mart.fact_deferred_rev.recognized_eur", "contract_total_eur * (active_days_in_month / total_contract_days)"],
                    ["Deferred Balance EUR", "mart.fact_deferred_rev.deferred_balance_eur", "contract_total_eur - cumulative_recognized_eur"],
                ],
            ),
        ],
    ),
]
