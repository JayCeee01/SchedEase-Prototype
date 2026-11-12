from io import BytesIO
from django.urls import reverse
from django.contrib.auth.models import User
from openpyxl import load_workbook
from . import test_schedule_workspace as workspace
from .test_known_defects import SchedulingDefectFixture
from . import models as m


class RoomScheduleExportTests(SchedulingDefectFixture):
    setUp = workspace.ScheduleWorkspaceTests.setUp

    def params(self):
        return {'room': self.room.pk, 'term': self.term.pk, 'schedule': self.schedule.pk}

    def test_formats_scope_and_applied_links(self):
        other = m.Room.objects.create(name='Not selected', capacity=40, room_type='LECTURE')
        response = self.client.get(reverse('room_schedule_export', args=['xlsx']), self.params())
        self.assertEqual(response.status_code, 200)
        ws = load_workbook(BytesIO(response.content)).active
        self.assertEqual(ws.title, 'Room Schedule')
        self.assertEqual(ws.max_row, 5)
        self.assertEqual(ws['I4'].value, self.room.name)
        self.assertEqual(ws.freeze_panes, 'A4')
        self.assertIn('WEEKLY', [ws['B4'].value, ws['B5'].value])
        empty = self.client.get(reverse('room_schedule_export', args=['xlsx']), dict(self.params(), room=other.pk))
        self.assertEqual(load_workbook(BytesIO(empty.content)).active.max_row, 3)
        response = self.client.get(reverse('room_schedule_export', args=['pdf']), self.params())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertIn('attachment;', response['Content-Disposition'])
        page = self.client.get(reverse('room_schedule'), self.params())
        self.assertContains(page, 'Export as PDF')
        self.assertContains(page, f'schedule={self.schedule.pk}&amp;room={self.room.pk}')

    def test_invalid_ids_and_permissions(self):
        url = reverse('room_schedule_export', args=['xlsx'])
        for params in ({}, dict(self.params(), room='bad'), dict(self.params(), schedule=999999), dict(self.params(), term=999999)):
            self.assertEqual(self.client.get(url, params).status_code, 404)
        user = User.objects.create_user('export-denied')
        m.Profile.objects.create(user=user, role='STUDENT')
        self.client.force_login(user)
        self.assertEqual(self.client.get(url, self.params()).status_code, 302)

    def test_dense_pdf_and_review_records(self):
        from copy import deepcopy
        from .services.room_schedule_export import room_schedule_export
        context = self.client.get(reverse('room_schedule'), self.params()).context[0].flatten()
        original = context['timetable_days'][0]['rows'][0]
        items = [dict(deepcopy(original), entry_id=100+i) for i in range(12)]
        context['timetable_days'][0]['rows'] = items
        context['timetable_columns'][0]['blocks'] = [
            {'presentation': item, 'left': str(i*100/12), 'width': str(100/12)}
            for i,item in enumerate(items)]
        context['timetable_unknown'] = [dict(deepcopy(original), entry_id=999)]
        pdf, mime = room_schedule_export(context, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))
        data, _ = room_schedule_export(context, 'xlsx')
        ws = load_workbook(BytesIO(data)).active
        self.assertEqual(ws.max_row, 16)
        self.assertIn('review required', str(list(ws.values)))
