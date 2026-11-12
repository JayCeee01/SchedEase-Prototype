"""Exports the already authorized room timetable projection; performs no queries."""
from io import BytesIO
from xml.sax.saxutils import escape


def records(context):
    rows = [(item, '') for day in context['timetable_days'] for item in day['rows']]
    rows += [(item, 'Meeting dates unavailable - review required') for item in context['timetable_unknown']]
    rows += [(item, 'Weekend SHS meeting - review required') for item in context['timetable_weekend']]
    return sorted(rows, key=lambda pair: (pair[0]['weekday'], pair[0]['start'], pair[0]['end'], pair[0]['entry_id']))


def detail_values(item, warning):
    dates = item.get('meeting_date')
    recurrence = str(dates) if dates else ('; '.join(str(d) for d in item.get('review_dates', [])) or item['recurrence']['kind'])
    return [item['weekday_name'], recurrence, item['start'], item['end'],
            item['subject']['code'], item['subject']['title'], item['primary_section']['label'],
            item['faculty']['label'], item['room']['label'], item['instructional_label'], warning]


def room_schedule_export(context, format):
    from .xlsx_export import sheet, workbook_bytes
    schedule = context['schedule']
    room = context.get('room')
    personal = 'export_identity' in context
    title = 'SchedEase - My Schedule' if personal else 'SchedEase - Room Schedule'
    identity = context['export_identity'] if personal else f'{room.name} | {room.get_room_type_display()}'
    subtitle = f'{schedule.term} | {schedule.name} | {identity}'
    subtitle += f' | Week: {context.get("timetable_week") or "Recurring weekly / review records"}'
    rows = records(context)
    headers = ['Day', 'Date / recurrence', 'Start', 'End', 'Subject', 'Subject name', 'Section', 'Faculty', 'Room', 'Instruction', 'Review notes']
    if format == 'xlsx':
        from openpyxl import Workbook
        workbook = Workbook()
        workbook.remove(workbook.active)
        ws = sheet(workbook, 'My Schedule' if personal else 'Room Schedule', title, subtitle, headers,
                   [detail_values(item, warning) for item, warning in rows],
                   [14, 25, 12, 12, 18, 36, 24, 28, 24, 24, 40])
        for row in ws.iter_rows(min_row=4):
            row[2].number_format = row[3].number_format = 'hh:mm'
        return workbook_bytes(workbook), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.graphics.shapes import Drawing, Rect, String, Line
    from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak, LongTable, TableStyle
    styles = getSampleStyleSheet()
    styles['BodyText'].fontSize = 8
    styles['BodyText'].leading = 10
    def para(value):
        return Paragraph(escape(str(value or '')), styles['BodyText'])
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    story = []
    ids = {id(item): index for index, (item, _) in enumerate(rows, 1)}
    def minutes(t):
        return t.hour * 60 + t.minute + t.second / 60
    # Three-hour panels preserve exact positions; dense/short blocks use numbered
    # references to the complete, wrapping details appendix rather than clipping.
    for begin in range(420, 1140, 180):
        story += [Paragraph(title, styles['Heading2']), para(subtitle),
                  para('Weekly meetings are recurring patterns, not confirmed calendar dates. Numbers refer to complete meeting details. Continued blocks retain their number.')]
        width, height, left = 780, 330, 54
        days = context['timetable_columns'] or [dict(name=day['name'], blocks=[]) for day in context['timetable_days']]
        day_width = (width-left) / len(days)
        drawing = Drawing(width, height+24)
        for offset in range(0, 181, 30):
            y = height - offset / 180 * height
            drawing.add(Line(left, y, width, y, strokeColor=colors.lightgrey))
            value = begin + offset
            drawing.add(String(0, y, f'{value//60:02}:{value%60:02}', fontSize=8))
        for day, column in enumerate(days):
            x = left + day * day_width
            drawing.add(String(x+3, height+8, column['name'], fontSize=9))
            drawing.add(Line(x, 0, x, height, strokeColor=colors.grey))
            for block in column['blocks']:
                item = block['presentation']
                start, end = max(begin, minutes(item['start'])), min(begin+180, minutes(item['end']))
                if end <= start:
                    continue
                bx = x + float(block['left']) / 100 * day_width
                bw = float(block['width']) / 100 * day_width
                by, bh = height-(end-begin)/180*height, (end-start)/180*height
                drawing.add(Rect(bx+1, by, max(1,bw-2), bh, fillColor=colors.HexColor('#e8f5f3'), strokeColor=colors.HexColor('#267c75')))
                text = f'#{ids[id(item)]}'
                if bw > 65:
                    text += ' ' + str(item['subject']['code'])
                drawing.add(String(bx+3, by+max(1,bh-10), text[:max(2,int(bw/4))], fontSize=7))
                if bw > 65 and bh >= 38:
                    drawing.add(String(bx+3, by+bh-20, f'{item["start"]:%H:%M}-{item["end"]:%H:%M}', fontSize=7))
                    drawing.add(String(bx+3, by+bh-30, str(item['instructional_label'])[:int(bw/4)], fontSize=7))
                if bw > 65 and bh >= 50:
                    drawing.add(String(bx+3, by+bh-40, str(item['primary_section']['label'])[:int(bw/4)], fontSize=7))
        story += [drawing, PageBreak()]
    story += [Paragraph('Complete meeting details and review records', styles['Heading2']), para(subtitle)]
    data = [[para(h) for h in ['#', 'Day / date / recurrence', 'Time', 'Subject / instruction', 'Section / faculty / room', 'Review']]]
    for index, (item, warning) in enumerate(rows, 1):
        v = detail_values(item, warning)
        data.append([para(index), para(f'{v[0]} / {v[1]}'), para(f'{v[2]} - {v[3]}'),
                     para(f'{v[4]} - {v[5]} / {v[9]}'), para(f'{v[6]} / {v[7]} / {v[8]}'), para(v[10])])
    if not rows:
        story.append(para('No meetings in the selected room and schedule.'))
    table = LongTable(data, colWidths=[28, 130, 85, 170, 245, 130], repeatRows=1, splitInRow=1)
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'), ('GRID',(0,0),(-1,-1),.4,colors.grey)]))
    story.append(table)
    document.build(story)
    return output.getvalue(), 'application/pdf'
