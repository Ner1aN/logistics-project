from html import escape
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


FONT_NAME = 'Helvetica'


def _register_font():
    global FONT_NAME
    candidates = [
        Path('C:/Windows/Fonts/arial.ttf'),
        Path('C:/Windows/Fonts/calibri.ttf'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    ]
    for font_path in candidates:
        if font_path.exists():
            FONT_NAME = 'ReportRegular'
            pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_path)))
            return FONT_NAME
    return 'Helvetica'


def _paragraph(text, style):
    return Paragraph(escape(str(text or '—')), style)


def _money(value):
    try:
        return f'{float(value):,.2f}'.replace(',', ' ') + ' руб.'
    except (TypeError, ValueError):
        return '0.00 руб.'


def _date(value):
    return value.strftime('%d.%m.%Y') if value else '—'


def _build_table(rows, column_widths, header_color=colors.HexColor('#274c77')):
    table = Table(rows, colWidths=column_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#d9dee7')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f9fb')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return table


def build_reports_pdf(context, filters):
    font_name = _register_font()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ReportTitle',
        parent=styles['Title'],
        fontName=font_name,
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name='ReportHeading',
        parent=styles['Heading2'],
        fontName=font_name,
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name='ReportText',
        parent=styles['BodyText'],
        fontName=font_name,
        fontSize=8,
        leading=10,
    ))

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title='Отчет по грузоперевозкам',
    )

    story = []
    story.append(Paragraph('Отчет по грузоперевозкам', styles['ReportTitle']))
    story.append(Paragraph(f'Дата формирования: {timezone.localtime().strftime("%d.%m.%Y %H:%M")}', styles['ReportText']))

    filter_parts = []
    if filters.get('date_from'):
        filter_parts.append(f"с {filters.get('date_from')}")
    if filters.get('date_to'):
        filter_parts.append(f"по {filters.get('date_to')}")
    if filters.get('status'):
        filter_parts.append(f"статус: {filters.get('status')}")
    if filters.get('client'):
        filter_parts.append(f"клиент ID: {filters.get('client')}")
    if filters.get('cargo_type'):
        filter_parts.append(f"тип груза: {filters.get('cargo_type')}")
    story.append(Paragraph('Фильтры: ' + (', '.join(filter_parts) if filter_parts else 'без фильтров'), styles['ReportText']))
    story.append(Spacer(1, 6))

    metrics_rows = [
        [_paragraph('Показатель', styles['ReportText']), _paragraph('Значение', styles['ReportText'])],
        [_paragraph('Заявок в отчете', styles['ReportText']), _paragraph(context['request_total_count'], styles['ReportText'])],
        [_paragraph('Сумма по заявкам', styles['ReportText']), _paragraph(_money(context['request_total_cost']), styles['ReportText'])],
        [_paragraph('Средняя стоимость', styles['ReportText']), _paragraph(_money(context['average_request_cost']), styles['ReportText'])],
        [_paragraph('Выполнено заявок', styles['ReportText']), _paragraph(f"{context['completed_request_percent']}%", styles['ReportText'])],
        [_paragraph('Просроченные заявки', styles['ReportText']), _paragraph(context['overdue_request_count'], styles['ReportText'])],
        [_paragraph('Активные в срок', styles['ReportText']), _paragraph(context['active_request_count'], styles['ReportText'])],
        [_paragraph('Выполненные перевозки', styles['ReportText']), _paragraph(context['completed_transportation_count'], styles['ReportText'])],
        [_paragraph('Выручка по выполненным', styles['ReportText']), _paragraph(_money(context['completed_transportation_cost']), styles['ReportText'])],
    ]
    story.append(_build_table(metrics_rows, [80 * mm, 55 * mm], colors.HexColor('#157a6e')))

    story.append(Paragraph('Статистика по статусам', styles['ReportHeading']))
    status_rows = [[_paragraph('Статус', styles['ReportText']), _paragraph('Количество', styles['ReportText']), _paragraph('Сумма', styles['ReportText'])]]
    for row in context['status_stats']:
        status_rows.append([
            _paragraph(row['status__name'], styles['ReportText']),
            _paragraph(row['total'], styles['ReportText']),
            _paragraph(_money(row['total_cost'] or 0), styles['ReportText']),
        ])
    story.append(_build_table(status_rows, [70 * mm, 35 * mm, 45 * mm]))

    story.append(Paragraph('Загрузка водителей', styles['ReportHeading']))
    driver_rows = [[_paragraph('Водитель', styles['ReportText']), _paragraph('Выполненных перевозок', styles['ReportText'])]]
    for row in context['driver_load_stats']:
        driver_rows.append([
            _paragraph(row['driver__full_name'], styles['ReportText']),
            _paragraph(row['total'], styles['ReportText']),
        ])
    if len(driver_rows) == 1:
        driver_rows.append([_paragraph('Нет данных', styles['ReportText']), _paragraph('0', styles['ReportText'])])
    story.append(_build_table(driver_rows, [90 * mm, 45 * mm]))

    story.append(Paragraph('Заявки в выборке', styles['ReportHeading']))
    request_rows = [[
        _paragraph('ID', styles['ReportText']),
        _paragraph('Клиент', styles['ReportText']),
        _paragraph('Груз', styles['ReportText']),
        _paragraph('Дата', styles['ReportText']),
        _paragraph('Статус', styles['ReportText']),
        _paragraph('Стоимость', styles['ReportText']),
    ]]
    for request in context['requests']:
        request_rows.append([
            _paragraph(f'#{request.pk}', styles['ReportText']),
            _paragraph(request.client.name, styles['ReportText']),
            _paragraph(request.get_cargo_type_display(), styles['ReportText']),
            _paragraph(_date(request.transportation_date), styles['ReportText']),
            _paragraph(request.status.name, styles['ReportText']),
            _paragraph(_money(request.cost), styles['ReportText']),
        ])
    story.append(_build_table(request_rows, [18 * mm, 60 * mm, 38 * mm, 28 * mm, 35 * mm, 35 * mm]))

    story.append(Paragraph('Выполненные перевозки', styles['ReportHeading']))
    transportation_rows = [[
        _paragraph('Заявка', styles['ReportText']),
        _paragraph('Водитель', styles['ReportText']),
        _paragraph('Транспорт', styles['ReportText']),
        _paragraph('Дата завершения', styles['ReportText']),
    ]]
    for item in context['completed_transportations']:
        transportation_rows.append([
            _paragraph(f'#{item.request.pk}', styles['ReportText']),
            _paragraph(item.driver.full_name, styles['ReportText']),
            _paragraph(item.vehicle.registration_number, styles['ReportText']),
            _paragraph(_date(item.arrival_at or item.request.transportation_date), styles['ReportText']),
        ])
    if len(transportation_rows) == 1:
        transportation_rows.append([_paragraph('Нет данных', styles['ReportText']), '', '', ''])
    story.append(_build_table(transportation_rows, [25 * mm, 70 * mm, 40 * mm, 45 * mm]))

    document.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


