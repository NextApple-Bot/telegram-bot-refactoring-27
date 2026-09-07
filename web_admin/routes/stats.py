from datetime import date
from io import BytesIO

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from bot.db import get_async_session_factory
from web_admin.routes.stats_helpers import parse_period
from web_admin.routes.stats_report import collect_report
from web_admin.templates import templates

router = APIRouter()


def template_ctx(
    request: Request,
    *,
    mode: str,
    days: int,
    month: str | None,
    start_date: date,
    end_date: date,
    period_label: str,
    data: dict,
) -> dict:
    sales_row = data["sales_row"]
    return {
        "request": request,
        "mode": mode,
        "target_date": end_date.isoformat(),
        "days": days,
        "month": month,
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "period_label": period_label,
        "sales_count": sales_row["count"],
        "devices_count": sales_row.get("devices_count", sales_row["count"]),
        "accessories_count": sales_row.get("accessories_count", 0),
        "preorders_count": data["preorders_row"]["count"],
        "bookings_count": data["bookings_row"]["count"],
        "payment_labels": [
            "Наличные",
            "Терминал",
            "QR",
            "Перевод",
            "По счёту",
            "Рассрочка",
        ],
        "payment_values": [
            float(sales_row["cash"]),
            float(sales_row["terminal"]),
            float(sales_row["qr"]),
            float(sales_row["transfer"]),
            float(sales_row["invoice"]),
            float(sales_row["installment"]),
        ],
        "chart_dates": data["chart_dates"],
        "chart_revenue": data["chart_revenue"],
        "chart_sales": data["chart_sales"],
        "source_labels": data["source_labels"],
        "source_counts": data["source_counts"],
        "source_amounts": data["source_amounts"],
        "sources_table": data["sources_table"],
        "booking_sources_table": data["booking_sources_table"],
        "models_table": data["models_table"],
        "model_labels": data["model_labels"],
        "model_counts": data["model_counts"],
        "has_adjustments": data.get("has_adjustments", False),
    }


@router.get("/")
async def stats_page(
    request: Request,
    target_date: str | None = None,
    days: int = Query(7, ge=1, le=366),
    mode: str = Query("preset"),
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    start_date, end_date, period_label = parse_period(
        target_date, days, mode, month, date_from, date_to
    )
    async_session = get_async_session_factory()
    async with async_session() as session:
        data = await collect_report(session, start_date, end_date)
    return templates.TemplateResponse(
        "stats.html",
        template_ctx(
            request,
            mode=mode,
            days=days,
            month=month,
            start_date=start_date,
            end_date=end_date,
            period_label=period_label,
            data=data,
        ),
    )


@router.get("/export.xlsx")
async def export_excel(
    target_date: str | None = None,
    days: int = Query(7, ge=1, le=366),
    mode: str = Query("preset"),
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    start_date, end_date, period_label = parse_period(
        target_date, days, mode, month, date_from, date_to
    )
    async_session = get_async_session_factory()
    async with async_session() as session:
        data = await collect_report(session, start_date, end_date)

    wb = Workbook()
    header_fill = PatternFill("solid", fgColor="4F46E5")
    header_font = Font(color="FFFFFF", bold=True)

    ws = wb.active
    ws.title = "Сводка"
    ws.append(["Период", period_label])
    if data.get("has_adjustments"):
        ws.append(["Примечание", "Учтены ручные корректировки с дашборда"])
    ws.append([])
    ws.append(["Показатель", "Значение"])
    for cell in ws[ws.max_row]:
        cell.fill = header_fill
        cell.font = header_font
    sales_row = data["sales_row"]
    ws.append(["Продажи (шт)", sales_row["count"]])
    ws.append(["Предзаказы (шт)", data["preorders_row"]["count"]])
    ws.append(["Брони (шт)", data["bookings_row"]["count"]])
    ws.append([])
    ws.append(["Оплата", "Сумма ₽"])
    for cell in ws[ws.max_row]:
        cell.fill = header_fill
        cell.font = header_font
    for label, key in [
        ("Наличные", "cash"),
        ("Терминал", "terminal"),
        ("QR", "qr"),
        ("Перевод", "transfer"),
        ("По счёту", "invoice"),
        ("Рассрочка", "installment"),
    ]:
        ws.append([label, float(sales_row[key])])

    ws2 = wb.create_sheet("Источники")
    ws2.append(["Источник", "Покупок", "Сумма ₽"])
    for cell in ws2[1]:
        cell.fill = header_fill
        cell.font = header_font
    for row in data["sources_table"]:
        ws2.append([row["name"], row["count"], round(row["amount"], 2)])

    ws3 = wb.create_sheet("Топ моделей")
    ws3.append(["Модель / товар", "Кол-во", "Сумма ₽"])
    for cell in ws3[1]:
        cell.fill = header_fill
        cell.font = header_font
    for row in data["models_table"]:
        ws3.append([row["name"], row["count"], round(row["amount"], 2)])

    ws4 = wb.create_sheet("Брони по площадкам")
    ws4.append(["Площадка", "Броней"])
    for cell in ws4[1]:
        cell.fill = header_fill
        cell.font = header_font
    for row in data["booking_sources_table"]:
        ws4.append([row["name"], row["count"]])

    ws5 = wb.create_sheet("По дням")
    ws5.append(["Дата", "Продажи", "Выручка ₽"])
    for cell in ws5[1]:
        cell.fill = header_fill
        cell.font = header_font
    for i, d in enumerate(data["chart_dates"]):
        ws5.append([d, data["chart_sales"][i], data["chart_revenue"][i]])

    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val = str(cell.value) if cell.value is not None else ""
                max_len = max(max_len, min(len(val), 60))
            sheet.column_dimensions[col_letter].width = max(12, max_len + 2)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"stats_{start_date.isoformat()}_{end_date.isoformat()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/print")
async def stats_print(
    request: Request,
    target_date: str | None = None,
    days: int = Query(7, ge=1, le=366),
    mode: str = Query("preset"),
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    start_date, end_date, period_label = parse_period(
        target_date, days, mode, month, date_from, date_to
    )
    async_session = get_async_session_factory()
    async with async_session() as session:
        data = await collect_report(session, start_date, end_date)

    return templates.TemplateResponse(
        "stats_print.html",
        template_ctx(
            request,
            mode=mode,
            days=days,
            month=month,
            start_date=start_date,
            end_date=end_date,
            period_label=period_label,
            data=data,
        ),
    )
