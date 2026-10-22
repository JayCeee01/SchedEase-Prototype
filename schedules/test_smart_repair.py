"""T10: recurring repair is previewed, authorized and applied only to drafts."""
from datetime import time
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services import smart_repair as service
from .services.conflicts import schedule_validation_messages


def measurement(scenario, result):
    import json
    print('T10 measurement '+json.dumps(dict(scenario=scenario,success=result['success'],
        counts=result.get('counts'),unresolved=result['unresolved'],hard_violations=result.get('hard_violations'),
        seconds=round(result['seconds'],4)),sort_keys=True))


class SmartRepairTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='repair-admin', password='test')
        self.client.force_login(self.admin)
        self.hours = m.Availability.objects.create(room=self.room, day=0, start_time=time(8),
            end_time=time(12), kind='AVAILABLE')
        self.source = m.Schedule.objects.create(term=self.term, name='Original')
        for i, meeting in enumerate(self.meetings):
            self.source.entries.create(assignment=meeting, room=self.room, day=0,
                start_time=time(8+i), end_time=time(9+i))
        self.source.status = 'PUBLISHED'
        self.source.save(update_fields=['status'])
        self.original = list(self.source.entries.values())

    def draft(self, kind='room', **extra):
        scenario = dict(kind=kind, resource=self.room.pk if kind=='room' else self.faculty.pk,
            day=0, start='08:00', end='09:00', rearrange=False)
        scenario.update(extra)
        return service.create_draft(self.source.pk, self.admin, scenario)

    def assert_safe(self, draft):
        self.assertEqual(list(self.source.entries.values()), self.original)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.faculty_id, self.faculty.pk)
        self.assertEqual(schedule_validation_messages(draft), [])

    def test_room_alternative_preserves_time_and_unaffected_meeting(self):
        alternate = m.Room.objects.create(name='Alternative', room_type='LECTURE', capacity=30)
        draft = self.draft()
        result = service.propose(draft.pk, self.admin)
        measurement('same-time alternate room',result)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['counts']['time_changes'], 0)
        self.assertEqual(result['counts']['room_changes'], 1)
        self.assertEqual(result['counts']['preserved'], 1)
        self.assertEqual(result['counts']['preserved_percent'], 50)
        self.assertEqual(draft.entries.first().room_id, self.room.pk)
        service.apply(draft.pk, self.admin, result['token'], confirmed=True)
        self.assertEqual(draft.entries.get(assignment=self.meetings[0]).room_id, alternate.pk)
        self.assert_safe(draft)

    def test_same_instructor_and_room_time_repair_is_deterministic(self):
        for kind in ('faculty', 'room'):
            draft = self.draft(kind)
            result = service.propose(draft.pk, self.admin)
            self.assertTrue(result['success'], result)
            self.assertEqual(result['rows'], service.propose(draft.pk, self.admin)['rows'])
            self.assertEqual(result['counts']['time_changes'], 1)
            self.assertEqual(result['counts']['instructor_changes'], 0)
            service.apply(draft.pk, self.admin, result['token'], confirmed=True)
            self.assert_safe(draft)
            measurement(kind+' time change',result)

    def replacement(self, **kwargs):
        self.hours.end_time=time(10); self.hours.save()
        other=m.Faculty.objects.create(department=self.department,employee_id='ALT',full_name='Alternative',**kwargs)
        draft=self.draft('faculty', replacements=[other.pk], replacement_meetings=[self.meetings[0].pk], comparable=True)
        return draft, other

    def test_explicit_replacement_only_changes_draft_entry(self):
        draft, other=self.replacement()
        result=service.propose(draft.pk,self.admin)
        measurement('approved replacement',result)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['counts']['instructor_changes'],1)
        self.assertEqual(result['counts']['time_changes'],0)
        service.apply(draft.pk,self.admin,result['token'],confirmed=True)
        self.assertEqual(draft.entries.get(assignment=self.meetings[0]).effective_faculty.pk,other.pk)
        self.assert_safe(draft)
        audit=draft.edit_audits.get(new_values__action='smart_repair_apply')
        override=audit.new_values['instructor_overrides'][0]
        self.assertEqual(override['original_faculty_id'],self.faculty.pk)
        self.assertEqual(override['replacement_faculty_id'],other.pk)
        self.assertEqual(override['meeting_id'],self.meetings[0].pk)
        self.assertTrue(override['reason'])
        self.assertEqual(audit.user_id,self.admin.pk)
        self.assertIsNotNone(audit.created_at)
        from .services.publication import publish
        draft.refresh_from_db()
        publish(draft,self.admin,replace_confirmed=True)
        self.assertEqual(draft.entries.get(assignment=self.meetings[0]).effective_faculty.pk,other.pk)
        self.assertEqual(list(self.source.entries.values()),self.original)

    def test_unresolved_does_not_modify_entries(self):
        self.hours.end_time=time(10);self.hours.save()
        draft=self.draft()
        before=list(draft.entries.values())
        result=service.propose(draft.pk,self.admin)
        measurement('no feasible room/time',result)
        self.assertFalse(result['success'])
        self.assertEqual(result['unresolved'],1)
        self.assertIsNone(result['token'])
        self.assertEqual(before,list(draft.entries.values()))

    def test_confirmation_and_stale_preview(self):
        draft=self.draft()
        result=service.propose(draft.pk,self.admin)
        with self.assertRaises(ValidationError):service.apply(draft.pk,self.admin,result['token'])
        self.hours.end_time=time(11);self.hours.save()
        before=list(draft.entries.values())
        with self.assertRaisesMessage(ValidationError,'stale'):
            service.apply(draft.pk,self.admin,result['token'],confirmed=True)
        self.assertEqual(before,list(draft.entries.values()))

    def test_failed_final_validation_rolls_back_entries_revision_and_audit(self):
        draft=self.draft()
        result=service.propose(draft.pk,self.admin)
        before=list(draft.entries.values()); audits=draft.edit_audits.count(); version=draft.updated_at
        with patch.object(service,'schedule_validation_messages',return_value=['Rejected']):
            with self.assertRaises(ValidationError):service.apply(draft.pk,self.admin,result['token'],confirmed=True)
        draft.refresh_from_db()
        self.assertEqual(before,list(draft.entries.values()))
        self.assertEqual(draft.updated_at,version)
        self.assertEqual(draft.edit_audits.count(),audits)

    def test_rules_reject_manual_edit_and_publication_and_survive_copy(self):
        from .services.manual_edits import copy_to_draft
        draft=self.draft()
        self.assertTrue(any('Recurring repair' in x for x in schedule_validation_messages(draft)))
        with self.assertRaises(ValidationError):draft.entries.first().full_clean()
        service.apply(draft.pk,self.admin,service.propose(draft.pk,self.admin)['token'],confirmed=True)
        from .services.publication import publish
        draft.refresh_from_db()
        publish(draft,self.admin,replace_confirmed=True)
        copied=copy_to_draft(source_id=draft.pk,actor=self.admin)
        entry=copied.entries.get(assignment=self.meetings[0]);entry.start_time=time(8);entry.end_time=time(9)
        with self.assertRaisesMessage(ValidationError,'Recurring repair'):entry.full_clean()

    def test_services_reject_non_administrator(self):
        user=User.objects.create_user(username='student')
        draft=self.draft()
        with self.assertRaises(ValidationError):service.propose(draft.pk,user)
        with self.assertRaises(ValidationError):service.create_draft(self.source.pk,user,{})

    def test_multiple_days_enforced_without_blocking_other_days_or_adjacent_times(self):
        from .services.repair_rules import entry_errors
        for kind in ('room','faculty'):
            draft=self.draft(kind,days=[2,0,2])
            self.assertEqual(service.setup(draft)['scenario']['days'],[0,2])
            entry=draft.entries.first()
            for day,blocked in [(0,True),(2,True),(1,False)]:
                entry.day=day
                self.assertEqual(bool(entry_errors(entry)),blocked)
            entry.day=2;entry.start_time=time(9);entry.end_time=time(10)
            self.assertEqual(entry_errors(entry),[])
            result=service.propose(draft.pk,self.admin)
            self.assertTrue(result['success'],result)
            service.apply(draft.pk,self.admin,result['token'],confirmed=True)
            self.assert_safe(draft)

    def test_missing_or_invalid_days_rejected_and_legacy_rules_remain_readable(self):
        from .services.repair_rules import entry_errors
        for days in ([],[6],['Monday'],[True]):
            with self.assertRaises(ValidationError):self.draft(days=days)
        draft=self.draft()
        audit=draft.edit_audits.get(new_values__action='smart_repair_setup')
        scenario=audit.new_values['scenario'];scenario.pop('days');scenario['day']=0
        audit.save(update_fields=['new_values'])
        self.assertTrue(entry_errors(draft.entries.first()))
        self.assertTrue(service.propose(draft.pk,self.admin)['success'])

    def test_form_requires_a_day_for_outages(self):
        from .repair_views import RepairForm
        form=RepairForm(self.source,dict(kind='room',room=self.room.pk,start='08:00',end='09:00',recurring='on'))
        self.assertFalse(form.is_valid())
        self.assertIn('at least one day',str(form.errors))

    def test_replacement_workload_capacity_blocks_entire_batch(self):
        draft, other=self.replacement(max_weekly_hours=1)
        # An existing authorized override already consumes the replacement's limit.
        draft.entries.filter(assignment=self.meetings[1]).update(faculty_override=other)
        m.Availability.objects.create(faculty=self.faculty,day=0,start_time=time(8),end_time=time(9),kind='AVAILABLE')
        result=service.propose(draft.pk,self.admin)
        self.assertFalse(result['success'],result)
        self.assertTrue(any('weekly workload' in reason for reason in result['reasons']))
        measurement('replacement lacks capacity',result)
        self.assertEqual(draft.entries.get(assignment=self.meetings[0]).effective_faculty.pk,self.faculty.pk)

    def test_unqualified_replacement_is_not_used(self):
        from datetime import date
        draft, other=self.replacement()
        credential=m.Credential.objects.create(name='Required certification')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject,required_credential=credential)
        m.FacultyCredential.objects.create(faculty=self.faculty,credential=credential,issued_on=date(2020,1,1))
        result=service.propose(draft.pk,self.admin)
        self.assertFalse(result['success'],result)
        self.assertTrue(any('qualification' in reason for reason in result['reasons']))

    def add_section(self):
        section=m.Section.objects.create(program=self.section.program,year_level=self.section.year_level,name='B',size=20)
        parent=m.Assignment.objects.create(term=self.term,subject=self.subject,section=section,faculty=self.faculty)
        m.TeachingAssignment.objects.create(assignment=parent,component='LECTURE',meeting_index=1,duration_minutes=120)
        return section

    def test_new_section_uses_recorded_requirements_and_preserves_original(self):
        section=self.add_section()
        draft=self.draft('sections',sections=[section.pk])
        result=service.propose(draft.pk,self.admin)
        self.assertTrue(result['success'],result)
        self.assertEqual(result['counts']['preserved'],2)
        self.assertEqual(result['counts']['added'],1)
        self.assertEqual(result['counts']['time_changes'],0)
        service.apply(draft.pk,self.admin,result['token'],confirmed=True)
        self.assert_safe(draft)
        measurement('additional section',result)

    def test_limited_rearrangement_requires_authorization(self):
        self.hours.end_time=time(11);self.hours.save()
        # First meeting needs the 9-10 slot; second can move to 10-11 only when authorized.
        m.Availability.objects.create(faculty=self.faculty,day=0,start_time=time(8),end_time=time(10),kind='AVAILABLE')
        other=m.Faculty.objects.create(department=self.department,employee_id='ALT',full_name='Alternative')
        draft=self.draft('faculty')
        draft.entries.filter(assignment=self.meetings[1]).update(faculty_override=other)
        self.assertFalse(service.propose(draft.pk,self.admin)['success'])
        draft2=self.draft('faculty',rearrange=True)
        draft2.entries.filter(assignment=self.meetings[1]).update(faculty_override=other)
        result=service.propose(draft2.pk,self.admin)
        self.assertTrue(result['success'],result)
        self.assertEqual(result['counts']['unaffected_changes'],1)
        service.apply(draft2.pk,self.admin,result['token'],confirmed=True)
        self.assert_safe(draft2)

    def test_invalid_room_alternatives_and_replacement_authorization(self):
        m.Room.objects.create(name='Too small',room_type='LECTURE',capacity=5)
        m.Room.objects.create(name='Wrong type',room_type='COMPUTER_LAB',capacity=50)
        m.Room.objects.create(name='Inactive',room_type='LECTURE',capacity=50,is_active=False)
        self.hours.end_time=time(10);self.hours.save()
        self.assertFalse(service.propose(self.draft().pk,self.admin)['success'])
        with self.assertRaises(ValidationError):self.draft('faculty',replacements=[self.faculty.pk])

    def test_http_authorization_csrf_confirmation_and_method(self):
        from django.test import Client
        url=f'/schedules/{self.source.pk}/repair/'
        response=self.client.get(url)
        self.assertContains(response,'Create a repair draft')
        payload=dict(kind='room',room=self.room.pk,days=[0,2],start='08:00',end='09:00',recurring='on')
        self.assertEqual(self.client.post(url,payload).status_code,302)
        draft=m.Schedule.objects.get(status='DRAFT')
        review=f'/schedules/{draft.pk}/repair/review/'
        response=self.client.post(review,{'action':'preview'})
        self.assertContains(response,'Apply to draft')
        self.assertTrue(response.context['result']['success'])
        self.assertContains(self.client.post(review,{'action':'apply','token':response.context['result']['token']}),'Confirm the repaired batch')
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.admin)
        self.assertEqual(csrf.post(review,{'action':'preview'}).status_code,403)
        self.assertEqual(self.client.delete(review).status_code,405)
        for role in ('STUDENT','FACULTY'):
            user=User.objects.create_user(username=role)
            m.Profile.objects.create(user=user,role=role)
            self.client.force_login(user)
            self.assertEqual(self.client.get(review).status_code,403)
            self.assertEqual(self.client.post(url,payload).status_code,403)

    def test_publication_rejects_unrepaired_draft_and_replay_is_stale(self):
        from .services.publication import publish
        draft=self.draft()
        with self.assertRaisesMessage(ValidationError,'Resolve conflicts'):publish(draft,self.admin,replace_confirmed=True)
        result=service.propose(draft.pk,self.admin)
        service.apply(draft.pk,self.admin,result['token'],confirmed=True)
        with self.assertRaisesMessage(ValidationError,'stale'):service.apply(draft.pk,self.admin,result['token'],confirmed=True)

    def test_other_published_term_consumes_rooms_and_instructors(self):
        term=m.AcademicTerm.objects.create(name='Overlapping',school_year='2026-2027',starts_on=self.term.starts_on,ends_on=self.term.ends_on)
        parent=m.Assignment.objects.create(term=term,subject=self.subject,section=self.section,faculty=self.faculty)
        meeting=m.TeachingAssignment.objects.create(assignment=parent,component='LECTURE',meeting_index=1,duration_minutes=120)
        external=m.Schedule.objects.create(term=term,name='Other term')
        external.entries.create(assignment=meeting,room=self.room,day=0,start_time=time(10),end_time=time(12))
        external.status='PUBLISHED';external.save(update_fields=['status'])
        result=service.propose(self.draft().pk,self.admin)
        self.assertFalse(result['success'],result)

    def test_source_archival_invalidates_proposal(self):
        from .services.manual_edits import copy_to_draft
        from .services.publication import publish
        draft=self.draft()
        token=service.propose(draft.pk,self.admin)['token']
        other=copy_to_draft(source_id=self.source.pk,actor=self.admin)
        publish(other,self.admin,replace_confirmed=True)
        with self.assertRaisesMessage(ValidationError,'source changed'):service.propose(draft.pk,self.admin)
        with self.assertRaisesMessage(ValidationError,'stale'):service.apply(draft.pk,self.admin,token,confirmed=True)

    def test_preview_budget_failure_is_not_claimed_infeasible(self):
        draft=self.draft()
        with patch.object(service,'BUDGET',0):result=service.propose(draft.pk,self.admin)
        self.assertFalse(result['success'])
        self.assertIn('Search limit reached; infeasibility is not proven.',result['reasons'])


from django.test import TransactionTestCase


class ConcurrentRepairTests(TransactionTestCase):
    def _fixture_teardown(self):
        # Match the existing cross-term concurrency fixture: protections stay
        # enabled throughout assertions; suspend only for disposable DB flush.
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
            triggers=cursor.fetchall()
            for name,_ in triggers:cursor.execute('DROP TRIGGER '+connection.ops.quote_name(name))
        try:super()._fixture_teardown()
        finally:
            with connection.cursor() as cursor:
                for _,sql in triggers:cursor.execute(sql)

    def test_two_apply_requests_cannot_commit_the_same_preview(self):
        from threading import Barrier, Thread
        from django.db import connections, OperationalError
        SchedulingDefectFixture.setUpTestData.__func__(type(self))
        SmartRepairTests.setUp(self)
        draft=SmartRepairTests.draft(self)
        token=service.propose(draft.pk,self.admin)['token']
        gate=Barrier(2);outcomes=[]
        def writer():
            try:
                gate.wait(timeout=10)
                service.apply(draft.pk,self.admin,token,confirmed=True)
                outcomes.append('saved')
            except ValidationError:outcomes.append('stale')
            except OperationalError as exc:outcomes.append('locked' if 'locked' in str(exc).lower() else repr(exc))
            except Exception as exc:outcomes.append(repr(exc))
            finally:connections.close_all()
        workers=[Thread(target=writer) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(15)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(outcomes.count('saved'),1,outcomes)
        self.assertEqual(len(outcomes),2)
        self.assertTrue(all(x in ('saved','stale','locked') for x in outcomes),outcomes)
        self.assertEqual(draft.edit_audits.filter(new_values__action='smart_repair_apply').count(),1)
        self.assertEqual(schedule_validation_messages(draft),[])
        self.assertEqual(list(self.source.entries.values()),self.original)
