"""Write a report dataset (ordered field names + dict rows) as CSV, Excel or PDF.

Every export job ends here: `render(path, fmt, fieldnames, rows, title=...)`.
CSV is the plain data; Excel and PDF add a title block (institution, report
name, filters, generated-at) so the file can go into an accreditation
(NAAC/NBA) binder as it is. Column headings come from the field names
(`roll_number` -> "Roll Number") unless `labels` overrides them.
"""

from datetime import datetime

from flask import current_app, has_app_context

FORMATS = ('csv', 'xlsx', 'pdf')
EXTENSIONS = {'csv': '.csv', 'xlsx': '.xlsx', 'pdf': '.pdf'}
MIMETYPES = {
    'csv': 'text/csv',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'pdf': 'application/pdf',
}
_LABELS = {
    'id': 'ID', 'ip_address': 'IP address', 'user_agent': 'User agent', 'full_name': 'Name',
    'attendance_percentage': 'Attendance %', 'percentage': 'Attendance %', 'total_classes': 'Countable',
}


def normalise_format(value):
    text = str(value or 'csv').strip().lower()
    return text if text in FORMATS else None


def label_for(field, labels=None):
    if labels and field in labels:
        return labels[field]
    if field in _LABELS:
        return _LABELS[field]
    return field.replace('_', ' ').strip().capitalize()


def institution_name():
    if not has_app_context():
        return ''
    return current_app.config.get('INSTITUTION_NAME') or current_app.config.get('INSTITUTION_SHORT_NAME') or ''


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, float):
        return round(value, 2)
    if hasattr(value, 'isoformat') and not isinstance(value, str):
        text = value.isoformat(sep=' ') if hasattr(value, 'hour') else value.isoformat()
        return text[:19]
    if hasattr(value, 'total_seconds'):  # timedelta from a TIME column
        seconds = int(value.total_seconds())
        return f'{seconds // 3600:02d}:{seconds % 3600 // 60:02d}'
    return value


def _meta_lines(title, subtitle, meta):
    lines = []
    name = institution_name()
    if name:
        lines.append(name)
    lines.append(title or 'Report')
    if subtitle:
        lines.append(subtitle)
    for key, value in (meta or {}).items():
        if value not in (None, ''):
            lines.append(f'{label_for(str(key))}: {value}')
    lines.append(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return lines


def render(path, fmt, fieldnames, rows, *, title='Report', subtitle=None, meta=None, labels=None):
    """Write the dataset to `path` in `fmt`. Returns the number of data rows written."""
    fmt = normalise_format(fmt)
    if fmt is None:
        raise ValueError('format')
    if fmt == 'csv':
        return write_csv(path, fieldnames, rows, labels=labels)
    if fmt == 'xlsx':
        return write_xlsx(path, fieldnames, rows, title=title, subtitle=subtitle, meta=meta, labels=labels)
    return write_pdf(path, fieldnames, rows, title=title, subtitle=subtitle, meta=meta, labels=labels)


def write_csv(path, fieldnames, rows, labels=None):
    """CSV keeps the raw field names as headings (scripts read them); explicit `labels` override individual columns."""
    import csv

    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow([(labels or {}).get(field, field) for field in fieldnames])
        count = 0
        for row in rows:
            writer.writerow([_cell(row.get(field, '')) for field in fieldnames])
            count += 1
    return count


def write_xlsx(path, fieldnames, rows, *, title='Report', subtitle=None, meta=None, labels=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    book = Workbook()
    sheet = book.active
    sheet.title = (title or 'Report')[:31].replace('/', '-').replace(':', '-') or 'Report'
    row_index = 1
    for index, line in enumerate(_meta_lines(title, subtitle, meta)):
        cell = sheet.cell(row=row_index, column=1, value=line)
        cell.font = Font(bold=index < 2, size=14 if index == 0 else 11)
        row_index += 1
    row_index += 1
    header_fill = PatternFill('solid', fgColor='1F2937')
    for column, field in enumerate(fieldnames, start=1):
        cell = sheet.cell(row=row_index, column=column, value=label_for(field, labels))
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(vertical='center')
    sheet.freeze_panes = sheet.cell(row=row_index + 1, column=1)
    widths = [len(label_for(field, labels)) for field in fieldnames]
    count = 0
    for row in rows:
        row_index += 1
        for column, field in enumerate(fieldnames, start=1):
            value = _cell(row.get(field, ''))
            sheet.cell(row=row_index, column=column, value=value)
            widths[column - 1] = max(widths[column - 1], min(60, len(str(value))))
        count += 1
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width + 2
    book.save(path)
    return count


def write_pdf(path, fieldnames, rows, *, title='Report', subtitle=None, meta=None, labels=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    page = landscape(A4) if len(fieldnames) > 7 else A4
    document = SimpleDocTemplate(
        path, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=title or 'Report', author=institution_name() or 'Timetable Management',
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=7.5, leading=9)
    story = []
    for index, line in enumerate(_meta_lines(title, subtitle, meta)):
        style = styles['Title'] if index == 0 else styles['Heading3'] if index == 1 else styles['Normal']
        story.append(Paragraph(_escape(line), style))
    story.append(Spacer(1, 4 * mm))

    def para(text):
        return Paragraph(_escape(str(text)), small)

    data = [[para(label_for(field, labels)) for field in fieldnames]]
    count = 0
    for row in rows:
        data.append([para(_cell(row.get(field, ''))) for field in fieldnames])
        count += 1
    if count == 0:
        data.append([para('No rows')] + [para('')] * (len(fieldnames) - 1))
    available = page[0] - 24 * mm
    table = Table(data, colWidths=[available / max(1, len(fieldnames))] * len(fieldnames), repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#9CA3AF')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(table)

    def footer(canvas, _document):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.drawRightString(page[0] - 12 * mm, 7 * mm, f'Page {canvas.getPageNumber()}')
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return count


def _escape(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
