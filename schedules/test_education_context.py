from datetime import date, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase, RequestFactory
from django.urls import reverse

from . import models as m
from .services.education_context import resolve_context
from .services.publication import publish


class EducationContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_superuser('context-test-admin')
        self.client.force_login(self.admin)
        self.ter = m.AcademicTerm.objects.create(name='Context tertiary', school_year='2026-2027',
            starts_on=date(2026,8,3), ends_on=date(2026,8,16))
        self.shs = m.AcademicTerm.objects.create(name='Context SHS', school_year='2026-2027',
            starts_on=date(2026,8,3), ends_on=date(2026,8,16), education_level='SHS')
        self.terms = m.AcademicTerm.objects.filter(pk__in=[self.ter.pk,self.shs.pk])

    def test_context_validation_and_single_level_compatibility(self):
        for level, term in [('TERTIARY',self.ter),('SHS',self.shs),('COMBINED',self.shs)]:
            context=resolve_context(self.factory.get('/',{'education_level':level,'term':term.pk}),self.terms)
            self.assertEqual(context.level,level)
            self.assertEqual(context.term_id,term.pk)
        for params in ({'education_level':'invalid'},{'education_level':'SHS','term':self.ter.pk},
                       {'term':'-1'},{'term':999999}):
            with self.assertRaises(Http404): resolve_context(self.factory.get('/',params),self.terms)
        self.assertEqual(resolve_context(self.factory.get('/'),self.terms.filter(pk=self.ter.pk)).level,'TERTIARY')
        request=self.factory.post('/',{'term':self.ter.pk})
        self.assertEqual(resolve_context(request,self.terms.filter(pk=self.ter.pk),write=True).level,'TERTIARY')
        with self.assertRaises(PermissionDenied): resolve_context(request,self.terms,write=True)

    def test_generation_rejects_forged_or_combined_context_before_lease(self):
        with patch('schedules.views.acquire') as acquire:
            for params, status in [({'education_level':'SHS','term':self.ter.pk},404),
                                   ({'education_level':'COMBINED','term':self.ter.pk},403),
                                   ({'term':self.ter.pk},403)]:
                self.assertEqual(self.client.post(reverse('generate_schedule'),params).status_code,status)
            acquire.assert_not_called()
        response=self.client.get(reverse('generate_schedule'),{'education_level':'SHS'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(set(response.context['form'].fields['term'].queryset.values_list('education_level',flat=True)),{'SHS'})
        self.assertContains(response,'name="education_level" value="SHS"')

    def test_management_scope_and_navigation(self):
        a=m.Schedule.objects.create(term=self.ter,name='Context tertiary draft')
        b=m.Schedule.objects.create(term=self.shs,name='Context SHS draft')
        url=reverse('resource_list',args=['schedules'])
        response=self.client.get(url,{'education_level':'SHS','term':self.shs.pk,'tab':'drafts'})
        self.assertEqual([o.pk for o in response.context['objects']],[b.pk])
        self.assertContains(response,'education_level=SHS&amp;term='+str(self.shs.pk))
        self.assertNotContains(response,a.name)
        terms=next(c for c in response.context['filters'] if c['name']=='term')
        self.assertNotIn(str(self.ter.pk),{str(pk) for pk,label in terms['options']})

    def published(self):
        department=m.Department.objects.create(code='CTX',name='Context tests')
        program=m.Program.objects.create(code='CTX',name='Context tests',department=department)
        year,_=m.YearLevel.objects.get_or_create(level=2,defaults={'label':'Year 2'})
        section=m.Section.objects.create(program=program,year_level=year,name='A',size=10)
        faculty=m.Faculty.objects.create(employee_id='CTX',full_name='Context faculty',department=department)
        room=m.Room.objects.create(name='CTX',room_type='LECTURE',capacity=20)
        subject=m.Subject.objects.create(code='CTX',title='Context subject',department=department,lecture_hours=1)
        assignment=m.Assignment.objects.create(term=self.ter,subject=subject,section=section,faculty=faculty)
        meeting=m.TeachingAssignment.objects.create(assignment=assignment,component='LECTURE',duration_minutes=60)
        schedule=m.Schedule.objects.create(term=self.ter,name='Context published')
        schedule.entries.create(assignment=meeting,room=room,day=0,start_time=time(9),end_time=time(10))
        publish(schedule,self.admin)
        return schedule,section,faculty

    def test_browse_isolation_switches_and_personal_export_authorization(self):
        schedule,section,faculty=self.published()
        user=User.objects.create_user('context-student')
        m.Profile.objects.create(user=user,role='STUDENT')
        m.Student.objects.create(user=user,section=section,student_number='20269991',full_name='Context student')
        self.client.force_login(user)
        for view in ('table','timetable'):
            response=self.client.get(reverse('browse_schedules'),{'education_level':'TERTIARY','term':self.ter.pk,'view':view})
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.context['entries']),1)
            self.assertIn('education_level=TERTIARY',response.context['view_links']['table'])
            self.assertEqual(response.context['export_schedule'].pk,schedule.pk)
        self.assertEqual(self.client.get(reverse('browse_schedules'),{'education_level':'COMBINED','term':self.shs.pk}).status_code,404)
        response=self.client.get(reverse('personal_schedule_export',args=['xlsx']),
            {'education_level':'SHS','schedule':schedule.pk,'term':self.ter.pk})
        self.assertEqual(response.status_code,404)
        response=self.client.get(reverse('personal_schedule_export',args=['xlsx']),
            {'education_level':'TERTIARY','schedule':schedule.pk,'term':self.ter.pk})
        self.assertEqual(response.status_code,200)
        faculty_user=User.objects.create_user('context-faculty')
        m.Profile.objects.create(user=faculty_user,role='FACULTY')
        faculty.user=faculty_user
        faculty.save()
        self.client.force_login(faculty_user)
        for source in ('browse','detail'):
            self.assertEqual(self.client.get(reverse('personal_schedule_export',args=['pdf']),
                {'education_level':'TERTIARY','schedule':schedule.pk,'source':source}).status_code,200)
            self.assertEqual(self.client.get(reverse('personal_schedule_export',args=['xlsx']),
                {'education_level':'SHS','schedule':schedule.pk,'source':source}).status_code,404)
        outsider=User.objects.create_user('context-outsider')
        m.Profile.objects.create(user=outsider,role='STUDENT')
        self.client.force_login(outsider)
        response=self.client.get(reverse('browse_schedules'),{'education_level':'COMBINED'})
        self.assertEqual(len(response.context['entries']),0)
        self.assertEqual(self.client.get(reverse('generate_schedule')).status_code,302)

    def test_conflicting_and_duplicate_context_is_rejected(self):
        with self.assertRaises(Http404):
            resolve_context(self.factory.get('/?education_level=SHS&education_level=TERTIARY'),self.terms)
        with self.assertRaises(Http404):
            resolve_context(self.factory.post('/?education_level=SHS',{'education_level':'TERTIARY','term':self.ter.pk}),self.terms,write=True)

    def test_generation_blocks_cross_level_assignment_before_lease(self):
        department=m.Department.objects.create(code='CTXBAD',name='Context bad assignment')
        program=m.Program.objects.create(code='CTXBAD',name='SHS',education_level='SHS',department=department)
        year,_=m.YearLevel.objects.get_or_create(level=11,defaults={'label':'Grade 11'})
        section=m.Section.objects.create(program=program,year_level=year,name='BAD',size=10)
        faculty=m.Faculty.objects.create(employee_id='CTXBAD',full_name='Context faculty',department=department)
        subject=m.Subject.objects.create(code='CTXBAD',title='Context subject',department=department)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            m.Assignment.objects.create(term=self.ter,subject=subject,section=section,faculty=faculty)
        settings=m.GASettings.objects.create()
        # Ordinary creation now rejects this fixture. Keep the independent
        # generation fail-closed boundary covered without bypassing DB guards.
        with patch('schedules.views.acquire') as acquire, patch('schedules.views.generation_scope_valid', return_value=False):
            response=self.client.post(reverse('generate_schedule'),{'education_level':'TERTIARY',
                'term':self.ter.pk,'name':'Must not generate','settings':settings.pk})
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'another education level')
            acquire.assert_not_called()
