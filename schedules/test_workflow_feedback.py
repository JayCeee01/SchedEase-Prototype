from datetime import time
from django.contrib.auth.models import User
from django.urls import reverse
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.publication import publish


class WorkflowFeedbackTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin=User.objects.create_superuser('workflow-admin')
        self.client.force_login(self.admin)
        self.schedule=m.Schedule.objects.create(term=self.term,name='Workflow draft')

    def fill(self, conflict=False):
        for i,meeting in enumerate(self.meetings):
            start=8 if conflict else 8+i
            self.schedule.entries.create(assignment=meeting,room=self.room,day=0,
                start_time=time(start),end_time=time(start+1))

    def test_empty_draft_not_presented_as_publishable(self):
        response=self.client.get(reverse('schedule_detail',args=[self.schedule.pk]))
        self.assertContains(response,'This draft has no meetings')
        self.assertContains(response,'disabled aria-describedby="schedule-validation"')
        self.assertNotContains(response,'No blocking issues detected')

    def test_conflict_link_preserves_filters_and_issues_cover_hidden_entries(self):
        self.fill(conflict=True)
        response=self.client.get(reverse('schedule_detail',args=[self.schedule.pk]),
            {'q':'not-visible','view':'timetable','week':'2026-08-03'})
        self.assertContains(response,'blocking publication')
        self.assertContains(response,'including meetings hidden by filters')
        url=response.context['check_conflicts_url']
        for text in ('q=not-visible','view=timetable','week=2026-08-03','check=1','#schedule-validation'):
            self.assertIn(text,url)
        self.assertContains(response,'Fix Conflict')

    def test_valid_draft_and_published_navigation(self):
        self.fill()
        response=self.client.get(reverse('schedule_detail',args=[self.schedule.pk]))
        self.assertContains(response,'Publication will revalidate')
        self.assertNotContains(response,'disabled aria-describedby="schedule-validation"')
        publish(self.schedule,self.admin)
        response=self.client.get(reverse('schedule_detail',args=[self.schedule.pk]))
        self.assertContains(response,'Browse this published schedule')
        self.assertContains(response,'Read-only historical schedule')
        self.assertNotContains(response,'data-publication-form')

    def test_generation_guidance_and_invalid_fields(self):
        response=self.client.get(reverse('generate_schedule'))
        self.assertContains(response,'Generation creates a draft for review')
        response=self.client.post(reverse('generate_schedule'),{'term':self.term.pk,'name':'','settings':''})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Review the highlighted errors')
        self.assertFalse(m.GenerationRun.objects.exists())
