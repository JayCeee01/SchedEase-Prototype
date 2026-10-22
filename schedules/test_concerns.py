"""T7 authorization, audit, traceability and schedule non-mutation contracts."""
from datetime import time
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import Client
from django.urls import reverse
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.publication import publish
from .services.concerns import submit_concern, review_concern


class ConcernTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin=User.objects.create_superuser('concern-admin')
        self.student=User.objects.create_user('concern-student',password='fixture-only')
        m.Profile.objects.create(user=self.student,role=m.Role.STUDENT)
        m.Student.objects.create(user=self.student,section=self.section,student_number='CONCERN',full_name='Reporter')
        self.teacher=User.objects.create_user('concern-teacher',password='fixture-only')
        m.Profile.objects.create(user=self.teacher,role=m.Role.FACULTY)
        self.faculty.user=self.teacher
        self.faculty.save()
        self.outsider=User.objects.create_user('outsider')
        m.Profile.objects.create(user=self.outsider,role=m.Role.STUDENT)
        other=m.Section.objects.create(program=self.section.program,year_level=self.section.year_level,name='B',size=20)
        m.Student.objects.create(user=self.outsider,section=other,student_number='OTHER',full_name='Other')
        self.schedule=m.Schedule.objects.create(term=self.term,name='Concern timetable')
        self.entries=[self.schedule.entries.create(assignment=a,room=self.room,day=0,
            start_time=time(8+i),end_time=time(9+i)) for i,a in enumerate(self.meetings)]
        publish(self.schedule,self.admin)
        self.schedule.refresh_from_db()

    def payload(self):
        return {'schedule':self.schedule.pk,'entry':self.entries[0].pk,'category':'TIME',
                'description':'The displayed class time needs review.'}

    def submit(self, user=None, **changes):
        data={**self.payload(),**changes}
        return submit_concern(actor=user or self.student,schedule_id=data['schedule'],
            entry_id=data['entry'],category=data['category'],description=data['description'])

    def test_student_and_faculty_submission_default_pending_and_ignored_privileged_fields(self):
        for user in (self.student,self.teacher):
            self.client.force_login(user)
            response=self.client.post(reverse('concern_create'),{**self.payload(),
                'reporter':self.outsider.pk,'reporter_role':'ADMIN','status':'RESOLVED','response':'Forged'})
            self.assertEqual(response.status_code,302)
            concern=m.ScheduleConcern.objects.get(reporter=user)
            self.assertEqual(concern.status,'PENDING')
            self.assertEqual(concern.response,'')
            self.assertEqual(concern.reporter_role,user.profile.role)
            self.assertEqual(concern.reference['assignment_id'],self.entries[0].assignment_id)
            self.assertIn(self.subject.code,concern.reference['course'])

    def test_unauthorized_reference_and_draft_rejected(self):
        self.client.force_login(self.outsider)
        self.assertContains(self.client.get(reverse('concern_create')),'No published schedule available')
        response=self.client.post(reverse('concern_create'),self.payload())
        self.assertEqual(response.status_code,200)
        self.assertFalse(m.ScheduleConcern.objects.exists())
        with self.assertRaises(ValidationError):
            self.submit(self.outsider)
        draft=m.Schedule.objects.create(term=self.term,name='Private draft')
        with self.assertRaises(ValidationError):
            self.submit(schedule=draft.pk)
        with self.assertRaises(ValidationError):
            self.submit(entry=999999)

    def test_mismatched_schedule_entry_rejected_and_missing_subject_allowed(self):
        draft=m.Schedule.objects.create(term=self.term,name='Draft')
        private=draft.entries.create(assignment=self.meetings[0],room=self.room,day=1,start_time=time(8),end_time=time(9))
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse('concern_create'),{**self.payload(),'entry':private.pk}).status_code,200)
        self.assertFalse(m.ScheduleConcern.objects.exists())
        concern=self.submit(entry=None,category='SUBJECT')
        self.assertIsNone(concern.entry_id)
        self.assertNotIn('course',concern.reference)

    def test_reporter_visibility_and_read_only_review(self):
        concern=self.submit()
        for other in (self.outsider, self.teacher):
            self.client.force_login(other)
            self.assertEqual(self.client.get(reverse('concern_detail',args=[concern.pk])).status_code,404)
            self.assertEqual(self.client.post(reverse('concern_detail',args=[concern.pk]),{}).status_code,404)
            self.assertNotContains(self.client.get(reverse('concern_list')),f'Concern #{concern.pk}:')
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('concern_detail',args=[concern.pk])),concern.description)
        self.assertEqual(self.client.post(reverse('concern_detail',args=[concern.pk]),{'status':'RESOLVED'}).status_code,403)
        concern.refresh_from_db()
        self.assertEqual(concern.status,'PENDING')

    def test_admin_review_filters_history_and_stale_rejection(self):
        concern=self.submit()
        self.submit(self.teacher,category='ROOM')
        self.client.force_login(self.admin)
        response=self.client.get(reverse('concern_list'),{'reporter_role':'STUDENT','category':'TIME','status':'PENDING'})
        self.assertEqual(list(response.context['page_obj']),[concern])
        self.assertEqual(self.client.post(reverse('concern_detail',args=[concern.pk]),
            {'revision':0,'status':'UNDER_REVIEW','response':'We are reviewing this time.'}).status_code,302)
        concern.refresh_from_db()
        self.assertEqual(concern.status,'UNDER_REVIEW')
        self.assertEqual(concern.reviewed_by,self.admin)
        self.assertIsNotNone(concern.reviewed_at)
        self.assertEqual(concern.reviews.count(),1)
        self.assertContains(self.client.post(reverse('concern_detail',args=[concern.pk]),
            {'revision':0,'status':'REJECTED','response':'Stale'}),'This concern changed')
        review_concern(actor=self.admin,pk=concern.pk,revision=1,status='RESOLVED',response='Reviewed with the department.')
        self.assertEqual(concern.reviews.count(),2)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('concern_detail',args=[concern.pk])),'Reviewed with the department.')

    def test_lengths_categories_status_and_response_validation(self):
        self.client.force_login(self.student)
        for changes in ({'description':'short'},{'description':'x'*3001},{'description':' '*20},{'category':'BAD'}):
            self.assertEqual(self.client.post(reverse('concern_create'),{**self.payload(),**changes}).status_code,200)
        self.assertFalse(m.ScheduleConcern.objects.exists())
        concern=self.submit()
        for status,response in [('INVALID','text'),('RESOLVED','x'*3001)]:
            with self.assertRaises(ValidationError):
                review_concern(actor=self.admin,pk=concern.pk,revision=0,status=status,response=response)
        self.assertFalse(concern.reviews.exists())

    def test_schedule_and_snapshots_unchanged_and_review_failure_atomic(self):
        before=(list(m.Schedule.objects.values()),list(m.ScheduleEntry.objects.values()),
                list(m.ScheduleSnapshot.objects.values()),list(m.ScheduleEntryAudit.objects.values()),
                list(m.TeachingAssignment.objects.values()))
        concern=self.submit()
        with patch('schedules.services.concerns.ConcernReview.objects.create',side_effect=RuntimeError('test rollback')):
            with self.assertRaises(RuntimeError):
                review_concern(actor=self.admin,pk=concern.pk,revision=0,status='RESOLVED',response='Review')
        concern.refresh_from_db()
        self.assertEqual(concern.revision,0)
        self.assertEqual(concern.status,'PENDING')
        review_concern(actor=self.admin,pk=concern.pk,revision=0,status='REJECTED',response='No schedule change required.')
        self.assertEqual(before,(list(m.Schedule.objects.values()),list(m.ScheduleEntry.objects.values()),
                list(m.ScheduleSnapshot.objects.values()),list(m.ScheduleEntryAudit.objects.values()),
                list(m.TeachingAssignment.objects.values())))

    def test_safe_text_and_traceability_after_schedule_replacement(self):
        concern=self.submit(description='<script>alert(1)</script> Please check.')
        review_concern(actor=self.admin,pk=concern.pk,revision=0,status='RESOLVED',response='<img src=x onerror=alert(1)>')
        replacement=m.Schedule.objects.create(term=self.term,name='Replacement')
        for i,a in enumerate(self.meetings):
            replacement.entries.create(assignment=a,room=self.room,day=1,start_time=time(8+i),end_time=time(9+i))
        publish(replacement,self.admin,replace_confirmed=True)
        self.client.force_login(self.student)
        response=self.client.get(reverse('concern_detail',args=[concern.pk]))
        self.assertContains(response,'Concern timetable')
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertNotContains(response,'<img src=x')
        self.assertNotContains(response,'>View schedule</a>')
        self.assertEqual(self.client.get(reverse('schedule_detail',args=[self.schedule.pk])).status_code,404)
        with self.assertRaises(ValidationError):
            self.submit()  # A form opened before replacement must no longer submit.

    def test_csrf_authentication_roles_and_http_methods(self):
        concern=self.submit()
        csrf=Client(enforce_csrf_checks=True)
        csrf.force_login(self.student)
        self.assertEqual(csrf.post(reverse('concern_create'),self.payload()).status_code,403)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(reverse('concern_detail',args=[concern.pk]),{'status':'RESOLVED'}).status_code,403)
        self.assertEqual(self.client.get(reverse('concern_list')).status_code,302)
        self.client.force_login(self.student)
        self.assertEqual(self.client.delete(reverse('concern_detail',args=[concern.pk])).status_code,405)
        with self.assertRaises(PermissionDenied):
            review_concern(actor=self.teacher,pk=concern.pk,revision=0,status='RESOLVED',response='Forged')
        with self.assertRaises(PermissionDenied):
            self.submit(self.admin)

    def test_faculty_cannot_select_other_teachers_published_class(self):
        from datetime import date
        other=m.Faculty.objects.create(department=self.department,employee_id='PRIVATE',full_name='Private Instructor')
        term=m.AcademicTerm.objects.create(name='Private term',school_year='2027',starts_on=date(2027,1,1),ends_on=date(2027,6,1))
        parent=m.Assignment.objects.create(term=term,subject=self.subject,section=self.section,faculty=other)
        schedule=m.Schedule.objects.create(term=term,name='Private teaching schedule')
        entries=[]
        for i in (1,2):
            meeting=m.TeachingAssignment.objects.create(assignment=parent,component='LECTURE',meeting_index=i,duration_minutes=60)
            entries.append(schedule.entries.create(assignment=meeting,room=self.room,day=0,start_time=time(7+i),end_time=time(8+i)))
        publish(schedule,self.admin)
        self.client.force_login(self.teacher)
        self.assertNotContains(self.client.get(reverse('concern_create')),'Private teaching schedule')
        with self.assertRaises(ValidationError):
            self.submit(self.teacher,schedule=schedule.pk,entry=entries[0].pk)
        # Student owns both schedules, but a class from one cannot refer to the other.
        self.client.force_login(self.student)
        response=self.client.post(reverse('concern_create'),{**self.payload(),'schedule':schedule.pk})
        self.assertContains(response,'Choose a class from the selected schedule.')
        self.assertFalse(m.ScheduleConcern.objects.exists())
