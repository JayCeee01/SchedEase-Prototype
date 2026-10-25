"""Printable, wrapped tables for schedule reports."""
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def write_table_pdf(output, title, context, headers, rows, widths):
    page = landscape(letter)
    document = SimpleDocTemplate(output, pagesize=page, leftMargin=30, rightMargin=30,
                                 topMargin=30, bottomMargin=36, title=str(title))
    body = ParagraphStyle('ExportCell', fontName='Helvetica', fontSize=9, leading=12,
                          splitLongWords=True)
    heading = ParagraphStyle('ExportHeading', parent=body, fontName='Helvetica-Bold', fontSize=14, leading=18)
    header = ParagraphStyle('ExportHeader', parent=body, fontName='Helvetica-Bold', textColor=colors.white)

    def paragraph(value, style=body):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)

    data = [[paragraph(value, header) for value in headers]]
    data.extend([paragraph(value) for value in row] for row in rows)
    story = [paragraph(title, heading), Spacer(1, 6), paragraph(context), Spacer(1, 12)]
    if len(data) == 1:
        story.append(paragraph('No entries match this report.'))
    else:
        table = LongTable(data, colWidths=[document.width * width / sum(widths) for width in widths],
                          repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#153b46')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#aab7bd')),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(table)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(30, 18, 'SchedEase')
        canvas.drawRightString(page[0] - 30, 18, f'Page {doc.page}')
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
