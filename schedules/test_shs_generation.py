from datetime import date, time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from . import models as m
from . import test_contact_workload as workload_tests
from .services.shs_scheduling import generate_shs
from .services.publication import publish
from .services.scheduling_requirements import resolve_shs


class ControlledSHSGenerationTests(TestCase):
    def setUp(self):
        workload_tests.ContactPolicyTests.setUp(self)
        self.actor = User.objects.create_superuser('synthetic_admin', password='test-only')
        self.settings = m.GASettings(population_size=2, generations=1, elitism=1)

    def generate(self):
        return generate_shs(self.term, self.settings, actor=self.actor, seed=17)

    def test_missing_policy_leaves_no_prepared_meetings(self):
        with self.assertRaises(ValidationError):
            self.generate()
        self.assertFalse(m.TeachingAssignment.objects.exists())
        self.assertFalse(m.Schedule.objects.exists())

    def test_generation_manual_validation_and_publication(self):
        workload_tests.ContactPolicyTests.policy(self)
        resolve_shs(self.plan.pk, assignment_id=self.assignment.pk).require_schedulable()
        schedule = self.generate()
        entry = schedule.entries.get()
        self.assertEqual(entry.day, 0)
        self.assertEqual(entry.room_id, self.room.pk)
        self.assertEqual(entry.assignment.required_duration_minutes, 60)
        self.assertEqual(entry.assignment.shs_binding.data['dates'], ['2026-08-03', '2026-08-10'])
        entry.day = 1
        with self.assertRaises(ValidationError):
            entry.full_clean()
        entry.refresh_from_db()
        published, _ = publish(schedule, self.actor)
        self.assertEqual(published.status, 'PUBLISHED')
        self.assertTrue(m.ScheduleSnapshot.objects.filter(schedule=published).exists())

    def test_policy_revocation_before_publication_blocks(self):
        policy = workload_tests.ContactPolicyTests.policy(self)
        schedule = self.generate()
        policy.is_active = False
        policy.save()
        with self.assertRaises(ValidationError):
            publish(schedule, self.actor)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'DRAFT')

    def test_unauthorized_adapter(self):
        workload_tests.ContactPolicyTests.policy(self)
        self.actor.is_superuser = False
        self.actor.save()
        with self.assertRaises(ValidationError):
            self.generate()
        self.assertFalse(m.TeachingAssignment.objects.exists())

    def test_dated_meetings_can_share_weekday_and_time_on_different_dates(self):
        pattern = self.config.patterns.get()
        self.config.is_confirmed = False
        self.config.save()
        pattern.recurrence = 'DATED'
        pattern.meeting_date = date(2026,8,3)
        pattern.window_end = time(9)
        pattern.save()
        m.SHSMeetingPattern.objects.create(configuration=self.config, component=self.component,
            sequence=2, recurrence='DATED', weekday=0, meeting_date=date(2026,8,10),
            window_start=time(8), window_end=time(9), required_room_type='LECTURE',
            room=self.room, room_approval_reference='Synthetic test')
        self.config.is_confirmed = True
        self.config.save()
        workload_tests.ContactPolicyTests.policy(self)
        schedule = self.generate()
        self.assertEqual(schedule.entries.count(),2)
        self.assertEqual(set(schedule.entries.values_list('start_time',flat=True)),{time(8)})
        publish(schedule,self.actor)

    def test_non_grid_operating_window_is_schedulable(self):
        pattern=self.config.patterns.get()
        pattern.window_start,pattern.window_end=time(8,10),time(9,10)
        pattern.save()
        workload_tests.ContactPolicyTests.policy(self)
        self.assertEqual(self.generate().entries.get().start_time,time(8,10))

    def test_snapshot_sql_protection(self):
        from django.db import IntegrityError, transaction
        workload_tests.ContactPolicyTests.policy(self)
        schedule = self.generate()
        item = schedule.entries.get().assignment.shs_binding
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.SHSMeetingBinding.objects.filter(pk=item.pk).update(data={})
        publish(schedule,self.actor)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.SHSMeetingBinding.objects.filter(pk=item.pk).delete()

    def test_smart_repair_stays_in_approved_pattern(self):
        from .services import smart_repair
        workload_tests.ContactPolicyTests.policy(self)
        schedule = self.generate()
        entry = schedule.entries.get()
        entry.start_time, entry.end_time = time(8),time(9)
        entry.save()
        published,_ = publish(schedule,self.actor)
        draft = smart_repair.create_draft(published.pk,self.actor,dict(kind='room',resource=self.room.pk,
            day=0,start='08:00',end='09:00',rearrange=False))
        result = smart_repair.propose(draft.pk,self.actor)
        self.assertTrue(result['success'],result)
        smart_repair.apply(draft.pk,self.actor,result['token'],confirmed=True)
        self.assertEqual(draft.entries.get().start_time,time(9))
        self.assertEqual(draft.entries.get().room_id,self.room.pk)

    def test_secondary_section_availability_is_enforced(self):
        self.config.combined_class_reference='Synthetic test'
        self.config.save()
        extra=m.Section.objects.create(program=self.program,year_level=self.year,name='B',size=20,cohort=self.section.cohort)
        m.SHSSectionParticipation.objects.create(configuration=self.config,section=extra)
        m.Availability.objects.create(section=extra,day=0,start_time=time(8),end_time=time(9),kind='UNAVAILABLE')
        workload_tests.ContactPolicyTests.policy(self)
        schedule=self.generate()
        self.assertGreaterEqual(schedule.entries.get().start_time,time(9))

    def tertiary(self, starts=date(2026,8,1), ends=date(2026,8,16)):
        program=m.Program.objects.create(department=self.department,code='TER',name='Tertiary')
        year=m.YearLevel.objects.create(level=1,label='Year 1')
        section=m.Section.objects.create(program=program,year_level=year,name='A',size=20)
        subject=m.Subject.objects.create(department=self.department,code='TER',title='Tertiary',lecture_hours=1)
        term=m.AcademicTerm.objects.create(name='Tertiary',school_year='2026-2027',starts_on=starts,ends_on=ends)
        parent=m.Assignment.objects.create(term=term,subject=subject,faculty=self.faculty,section=section)
        meeting=m.TeachingAssignment.objects.create(assignment=parent,component='LECTURE',duration_minutes=60,meeting_index=1)
        schedule=m.Schedule.objects.create(term=term,name='Tertiary')
        entry=schedule.entries.create(assignment=meeting,room=self.room,day=0,start_time=time(8),end_time=time(9))
        return schedule,entry

    def test_published_tertiary_consumes_room_and_weekly_minutes(self):
        policy=workload_tests.ContactPolicyTests.policy(self,maximum_contact_minutes=60)
        other,_=self.tertiary()
        publish(other,self.actor)
        with self.assertRaises(ValidationError): self.generate()
        policy.maximum_contact_minutes=120
        policy.save()
        schedule=self.generate()
        self.assertGreaterEqual(schedule.entries.get().start_time,time(9))
        publish(schedule,self.actor)

    def test_tertiary_publication_cannot_overload_published_shs(self):
        workload_tests.ContactPolicyTests.policy(self,maximum_contact_minutes=60)
        published,_=publish(self.generate(),self.actor)
        other,entry=self.tertiary()
        entry.start_time,entry.end_time=time(11),time(12)
        entry.save()
        with self.assertRaises(ValidationError): publish(other,self.actor)
        published.refresh_from_db()
        self.assertEqual(published.status,'PUBLISHED')

    def test_repeated_tertiary_validation_refreshes_published_shs_workload(self):
        from .services.conflicts import schedule_validation_messages
        workload_tests.ContactPolicyTests.policy(self,maximum_contact_minutes=60)
        shs=self.generate()
        other,entry=self.tertiary()
        entry.start_time,entry.end_time=time(11),time(12)
        entry.save()
        self.assertEqual(schedule_validation_messages(other),[])
        publish(shs,self.actor)
        errors=schedule_validation_messages(other)
        self.assertTrue(any('exceeds the approved limit' in message for message in errors),errors)
        with self.assertRaises(ValidationError): entry.full_clean()

    def test_nonoverlapping_published_term_does_not_consume_policy_or_room(self):
        workload_tests.ContactPolicyTests.policy(self,maximum_contact_minutes=60)
        other,_=self.tertiary(date(2026,9,1),date(2026,9,30))
        publish(other,self.actor)
        publish(self.generate(),self.actor)


class SnapshotMigrationTests(workload_tests.ContactPolicyMigrationTests):
    def rehearse(self,populated):
        import os, subprocess, sys
        from .test_shs_migrations import REHEARSAL
        script=REHEARSAL.replace('0020_normalized_identity_uniqueness','0024_shs_operational_inputs').replace('0021_shs_academic_identity','0026_shs_meeting_snapshots')
        env=os.environ.copy()
        env['SHS_MIGRATION_POPULATED']=str(int(populated))
        result=subprocess.run([sys.executable,'-B','-c',script],env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


from django.test import TransactionTestCase


class ConcurrentSHSPublicationTests(TransactionTestCase):
    def _fixture_teardown(self):
        # Same disposable-database teardown convention as publication tests.
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
            triggers=cursor.fetchall()
            for name,_ in triggers:
                cursor.execute('DROP TRIGGER '+connection.ops.quote_name(name))
        try:
            super()._fixture_teardown()
        finally:
            with connection.cursor() as cursor:
                for _,sql in triggers: cursor.execute(sql)
    generate = ControlledSHSGenerationTests.generate
    tertiary = ControlledSHSGenerationTests.tertiary

    def test_competing_shs_and_tertiary_publications_recheck_weekly_limit(self):
        from threading import Barrier, Thread
        from django.db import OperationalError, connections
        ControlledSHSGenerationTests.setUp(self)
        workload_tests.ContactPolicyTests.policy(self,maximum_contact_minutes=60)
        shs=self.generate()
        tertiary,entry=self.tertiary()
        entry.start_time,entry.end_time=time(11),time(12)
        entry.save()
        gate=Barrier(2)
        outcomes=[]
        def worker(schedule):
            try:
                gate.wait(timeout=10)
                publish(schedule,self.actor)
                outcomes.append('saved')
            except ValidationError:
                outcomes.append('rejected')
            except OperationalError as exc:
                outcomes.append('locked' if 'locked' in str(exc).lower() else str(exc))
            except Exception as exc:
                outcomes.append(repr(exc))
            finally:
                connections.close_all()
        workers=[Thread(target=worker,args=(schedule,)) for schedule in (shs,tertiary)]
        for worker_thread in workers: worker_thread.start()
        for worker_thread in workers: worker_thread.join(20)
        self.assertTrue(all(not worker_thread.is_alive() for worker_thread in workers))
        self.assertEqual(outcomes.count('saved'),1,outcomes)
        self.assertTrue(all(value in ('saved','rejected','locked') for value in outcomes),outcomes)
        loser=m.Schedule.objects.get(status='DRAFT')
        with self.assertRaises(ValidationError): publish(loser,self.actor)
        self.assertEqual(m.Schedule.objects.filter(status='PUBLISHED').count(),1)
