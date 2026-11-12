"""Shared shell preserves existing route, role and query contracts."""
from datetime import time
from django.contrib.auth.models import User
from django.urls import reverse
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .test_publication_helpers import finalize


class ScheduleWorkspaceTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('workspace-admin')
        self.client.force_login(self.admin)
        self.schedule = m.Schedule.objects.create(term=self.term, name='Workspace baseline')
        for i, meeting in enumerate(self.meetings):
            self.schedule.entries.create(assignment=meeting, room=self.room, day=0,
                                         start_time=time(8+i), end_time=time(9+i))
        finalize(self.schedule)
        self.manage = reverse('resource_list', args=['schedules'])
        self.browse = reverse('browse_schedules')

    def test_shared_heading_primary_navigation_and_sidebar(self):
        for url, primary in ((self.manage, 'Manage'), (self.browse, 'Browse Published')):
            response = self.client.get(url)
            self.assertContains(response, '<h1>Manage Schedules</h1>', html=True)
            self.assertContains(response, 'aria-label="Schedule workspace"')
            self.assertContains(response, f'aria-current="page">{primary}</a>')
            self.assertContains(response, f'href="{self.manage}" data-icon="calendar" class="is-active" aria-current="page">Manage Schedules</a>')
            self.assertNotContains(response, 'data-icon="calendar">Browse Published</a>')

    def test_management_subtabs_actions_filters_and_pagination(self):
        for i in range(23):
            m.Schedule.objects.create(term=self.term, name=f'Draft {i:02}')
        response = self.client.get(self.manage, {'tab':'drafts','q':'Draft','term':self.term.pk,'sort':'record_asc','page':2})
        self.assertEqual(response.context['schedule_tab'], 'drafts')
        self.assertEqual(response.context['filtered_count'], 23)
        self.assertEqual(len(response.context['objects']), 3)
        self.assertContains(response, 'name="tab" value="drafts"')
        self.assertContains(response, 'Edit Schedule')
        self.assertContains(response, 'Edit Details')
        self.assertContains(response, 'Delete')
        for tab in ('active','drafts','archived'):
            self.assertIn('q=Draft', response.context['tab_links'][tab])
            self.assertIn(f'tab={tab}', response.context['tab_links'][tab])
        self.assertContains(self.client.get(self.manage, {'tab':'archived'}), 'No records in this view.')
        self.assertEqual(self.client.get(self.manage, {'tab':'invalid'}).context['schedule_tab'],'active')

    def test_old_browse_url_filters_and_table_tools_preserved(self):
        response = self.client.get(self.browse, {'term':self.term.pk,'subject':self.subject.pk})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.context['entries']),2)
        for field in ('term','department','program','year_level','section','subject'):
            self.assertContains(response,f'name="{field}"')
        for label in ('Apply Filters','Section, course, faculty, or room','data-sort','2 entries'):
            self.assertContains(response,label)
        self.assertContains(self.client.get(self.browse, {'term':'invalid'}),'No schedule entries.')

    def test_nonadministrators_have_browse_only_and_no_manage_access(self):
        for role in ('FACULTY','STUDENT'):
            user=User.objects.create_user('workspace-'+role)
            m.Profile.objects.create(user=user,role=role)
            self.client.force_login(user)
            response=self.client.get(self.browse)
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'aria-current="page">Browse Published</a>')
            self.assertNotContains(response,f'href="{self.manage}"')
            self.assertEqual(len(response.context['entries']),0)
            self.assertEqual(self.client.get(self.manage).status_code,302)

    def test_shared_grid_in_detail_browse_and_room_with_search_state(self):
        pages = [(reverse('schedule_detail', args=[self.schedule.pk]), {'view':'timetable'}),
                 (self.browse, {'view':'timetable','q':self.subject.code,'term':self.term.pk}),
                 (reverse('room_schedule'), {'schedule':self.schedule.pk,'room':self.room.pk})]
        for url, params in pages:
            response = self.client.get(url, params)
            self.assertEqual(response.status_code,200)
            self.assertTemplateUsed(response,'schedules/_time_grid.html')
            self.assertNotContains(response,'Class continues')
            self.assertContains(response, 'continuous-meeting')
            self.assertContains(response,'shared-time-grid')
            self.assertContains(response, 'class="meeting-preview"')
            self.assertContains(response, 'popovertarget="meeting-details-')
            self.assertContains(response, 'popovertargetaction="hide"')
            self.assertContains(response, 'class="meeting-details"')
        response=self.client.get(self.browse,pages[1][1])
        self.assertIn('q='+self.subject.code,response.context['view_links']['table'])
        self.assertEqual(len(response.context['entries']),2)
        self.assertContains(self.client.get(self.browse,{'view':'timetable','q':'unmatched-search'}),'No meetings found')
        self.assertEqual(self.client.get(self.browse,{'view':'invalid'}).context['schedule_view'],'table')

    def test_browse_combined_filters_and_unified_search(self):
        params = {'term':self.term.pk, 'faculty':self.faculty.pk, 'room':self.room.pk,
                  'day':'0', 'component':self.meetings[0].component, 'q':self.subject.code}
        expected = [e.pk for e in self.schedule.entries.all()
                    if e.effective_component == self.meetings[0].component]
        for view in ('table', 'timetable'):
            response = self.client.get(self.browse, dict(params, view=view, sort='faculty', page='2'))
            self.assertEqual([e.pk for e in response.context['entries']], expected)
            self.assertContains(response, 'name="q"', count=1)
            self.assertNotContains(response, 'data-table-filter')
            self.assertContains(response, '?view='+view+'">Clear')
            for value in ('faculty=', 'room=', 'day=0', 'component=', 'q=', 'sort=faculty', 'page=2'):
                self.assertIn(value, response.context['view_links']['table'])
        for params in ({'day':'1'}, {'component':'invalid'}, {'faculty':'999999'}, {'q':'no-match'}):
            self.assertEqual(len(self.client.get(self.browse, params).context['entries']), 0)
        self.assertEqual(len(self.client.get(self.browse, {'view':'table'}).context['entries']), 2)

    def test_browse_individual_filters_and_restricted_options(self):
        for key, value in (('faculty',self.faculty.pk), ('room',self.room.pk), ('day','0')):
            self.assertEqual(len(self.client.get(self.browse, {key:value}).context['entries']), 2)
        form = self.client.get(self.browse).context['form']
        self.assertEqual(list(form.fields['faculty'].queryset.values_list('pk',flat=True)), [self.faculty.pk])
        self.assertEqual(list(form.fields['room'].queryset.values_list('pk',flat=True)), [self.room.pk])
