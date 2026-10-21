"""T3 workflow and real separate-connection writer regression tests."""
from datetime import time
from threading import Barrier, Thread
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import OperationalError, connections
from django.test import TransactionTestCase
from . import models as m
from .services.conflicts import schedule_validation_issues
from .services.manual_edits import FIELDS, revision_token, save_manual_entry
from .test_known_defects import SchedulingDefectFixture


class DoubleBookingWorkflowTests(SchedulingDefectFixture):
    def test_manual_creation_rejects_overlap_but_accepts_adjacent_and_other_day(self):
        actor = User.objects.create_superuser('t3-create')
        schedule = m.Schedule.objects.create(term=self.term, name='Create')
        schedule.entries.create(assignment=self.meetings[0], room=self.room,
            day=0, start_time=time(8), end_time=time(9))
        entry = m.ScheduleEntry(assignment=self.meetings[1], room=self.room,
            day=0, start_time=time(8, 30), end_time=time(9, 30))
        proposed = {f: getattr(entry, f) for f in FIELDS}
        token = revision_token(schedule, actor)
        with self.assertRaisesMessage(ValidationError, 'conflict'):
            save_manual_entry(schedule_id=schedule.pk, entry_id=None, actor=actor,
                revision=token, proposed=proposed)
        self.assertEqual(schedule.entries.count(), 1)
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())
        for day, start, end in [(0, time(9), time(10)), (1, time(8), time(9))]:
            with self.subTest(day=day):
                schedule.refresh_from_db()
                saved = save_manual_entry(schedule_id=schedule.pk, entry_id=None, actor=actor,
                    revision=revision_token(schedule, actor),
                    proposed={**proposed, 'day': day, 'start_time': start, 'end_time': end})
                self.assertEqual(schedule_validation_issues(schedule), [])
                saved.delete()


class ConcurrentDoubleBookingTests(TransactionTestCase):
    def setUp(self):
        SchedulingDefectFixture.setUpTestData.__func__(type(self))

    def compete(self, resource):
        actor = User.objects.create_superuser('t3-race')
        schedule = m.Schedule.objects.create(term=self.term, name='Race')
        other_faculty = m.Faculty.objects.create(department=self.department,
            employee_id='other', full_name='Other')
        other_section = m.Section.objects.create(program=self.section.program,
            year_level=self.section.year_level, name='B', size=20)
        other_room = m.Room.objects.create(name='Other', room_type='LECTURE', capacity=30)
        entries = [schedule.entries.create(assignment=a, room=self.room, day=0,
            start_time=time(8+i), end_time=time(9+i)) for i, a in enumerate(self.meetings)]
        proposals = [{f: getattr(e, f) for f in FIELDS} for e in entries]
        for p in proposals:
            p.update(day=1, start_time=time(8), end_time=time(9))
        proposals[1]['section_override_id'] = other_section.pk
        if resource == 'faculty':
            proposals[1]['room_id'] = other_room.pk
        else:
            proposals[1]['faculty_override_id'] = other_faculty.pk
        tokens = [revision_token(schedule, actor, e) for e in entries]
        gate = Barrier(2)
        outcomes = []
        def writer(i):
            try:
                gate.wait(timeout=10)
                save_manual_entry(schedule_id=schedule.pk, entry_id=entries[i].pk,
                    actor=actor, revision=tokens[i], proposed=proposals[i])
                outcomes.append('saved')
            except ValidationError:
                outcomes.append('stale')
            except OperationalError as exc:
                outcomes.append('locked' if 'locked' in str(exc).lower() else repr(exc))
            except Exception as exc:
                outcomes.append(repr(exc))
            finally:
                connections.close_all()
        workers = [Thread(target=writer, args=(i,)) for i in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(15)
        self.assertTrue(all(not w.is_alive() for w in workers))
        self.assertEqual(outcomes.count('saved'), 1, outcomes)
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(all(o in ('saved', 'stale', 'locked') for o in outcomes), outcomes)
        self.assertEqual(m.ScheduleEntryAudit.objects.count(), 1)
        self.assertEqual(schedule_validation_issues(schedule), [])
        loser = next(i for i, e in enumerate(entries)
                     if m.ScheduleEntry.objects.get(pk=e.pk).day == 0)
        schedule.refresh_from_db()
        entries[loser].refresh_from_db()
        with self.assertRaisesMessage(ValidationError, resource.capitalize() + ' conflict'):
            save_manual_entry(schedule_id=schedule.pk, entry_id=entries[loser].pk,
                actor=actor, revision=revision_token(schedule, actor, entries[loser]),
                proposed=proposals[loser])
        self.assertEqual(m.ScheduleEntryAudit.objects.count(), 1)

    def test_concurrent_different_entries_same_instructor(self):
        self.compete('faculty')

    def test_concurrent_different_entries_same_room(self):
        self.compete('room')


class CrossTermFixture:
    def prepare(self):
        from datetime import date
        SchedulingDefectFixture.setUpTestData.__func__(type(self))
        self.actor = User.objects.create_superuser('cross-term')
        second_term = m.AcademicTerm.objects.create(name='Concurrent term', school_year='2026',
            starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 1))
        parent = m.Assignment.objects.create(term=second_term, subject=self.subject,
            section=self.section, faculty=self.faculty)
        meetings = [m.TeachingAssignment.objects.create(assignment=parent, component='LECTURE',
            meeting_index=i, duration_minutes=60) for i in (1, 2)]
        self.schedules = []
        for term, items in [(self.term, self.meetings), (second_term, meetings)]:
            schedule = m.Schedule.objects.create(term=term, name=term.name)
            for i, meeting in enumerate(items):
                schedule.entries.create(assignment=meeting, room=self.room, day=0,
                    start_time=time(8+i), end_time=time(9+i))
            self.schedules.append(schedule)


class CrossTermTests(CrossTermFixture, TransactionTestCase):
    def _fixture_teardown(self):
        # Only the disposable test DB: finalized-record triggers must remain
        # active during assertions, but prohibit Django's unordered flush.
        from django.db import connection
        if connection.vendor != 'sqlite':
            return super()._fixture_teardown()
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
            triggers = cursor.fetchall()
            for name, _ in triggers:
                cursor.execute('DROP TRIGGER ' + connection.ops.quote_name(name))
        try:
            super()._fixture_teardown()
        finally:
            with connection.cursor() as cursor:
                for _, sql in triggers:
                    cursor.execute(sql)

    def setUp(self):
        self.prepare()

    def test_published_term_blocks_manual_save_and_publication_atomically(self):
        from .services.publication import publish
        publish(self.schedules[0], self.actor)
        draft = self.schedules[1]
        issues = schedule_validation_issues(draft)
        self.assertEqual({i['issue'].category for i in issues}, {'FACULTY_CONFLICT', 'ROOM_CONFLICT'})
        entry = draft.entries.first()
        with self.assertRaisesMessage(ValidationError, 'Faculty conflict'):
            save_manual_entry(schedule_id=draft.pk, entry_id=entry.pk, actor=self.actor,
                revision=revision_token(draft, self.actor, entry),
                proposed={f: getattr(entry, f) for f in FIELDS})
        with self.assertRaisesMessage(ValidationError, 'Resolve conflicts'):
            publish(draft, self.actor)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'DRAFT')
        self.assertFalse(m.ScheduleEntryAudit.objects.filter(schedule=draft).exists())
        self.assertFalse(m.ScheduleSnapshot.objects.filter(schedule=draft).exists())

    def test_date_weekday_adjacency_and_alternative_draft_boundaries(self):
        from datetime import date
        from .services.publication import publish
        self.assertEqual(schedule_validation_issues(self.schedules[1]), [])
        publish(self.schedules[0], self.actor)
        draft = self.schedules[1]
        for starts, ends, blocked in [(date(2026, 12, 2), date(2026, 12, 8), False),
                (date(2026, 12, 1), date(2026, 12, 8), False),
                (date(2026, 11, 30), date(2026, 12, 8), True)]:
            with self.subTest(starts=starts):
                m.AcademicTerm.objects.filter(pk=draft.term_id).update(starts_on=starts, ends_on=ends)
                draft = m.Schedule.objects.get(pk=draft.pk)
                self.assertEqual(bool(schedule_validation_issues(draft)), blocked)
        draft.entries.update(day=1)
        self.assertEqual(schedule_validation_issues(draft), [])
        for i, entry in enumerate(draft.entries.order_by('pk')):
            entry.day, entry.start_time, entry.end_time = 0, time(10+i), time(11+i)
            entry.save()
        self.assertEqual(schedule_validation_issues(draft), [])

    def test_concurrent_cross_term_publications_cannot_both_commit(self):
        from .services.publication import publish
        gate = Barrier(2)
        results = []
        def writer(schedule):
            try:
                gate.wait(timeout=10)
                publish(schedule, self.actor)
                results.append('saved')
            except ValidationError:
                results.append('rejected')
            except OperationalError as exc:
                results.append('locked' if 'locked' in str(exc).lower() else repr(exc))
            except Exception as exc:
                results.append(repr(exc))
            finally:
                connections.close_all()
        workers = [Thread(target=writer, args=(s,)) for s in self.schedules]
        for w in workers:
            w.start()
        for w in workers:
            w.join(15)
        self.assertTrue(all(not w.is_alive() for w in workers))
        self.assertEqual(results.count('saved'), 1, results)
        self.assertTrue(all(r in ('saved', 'rejected', 'locked') for r in results), results)
        self.assertEqual(m.Schedule.objects.filter(status='PUBLISHED').count(), 1)
        loser = m.Schedule.objects.get(status='DRAFT')
        with self.assertRaisesMessage(ValidationError, 'Resolve conflicts'):
            publish(loser, self.actor)
        self.assertEqual(m.ScheduleSnapshot.objects.count(), 1)

    def test_ga_cross_term_conflicts_roll_back_generated_schedule(self):
        from unittest.mock import patch
        from .services.ga import Gene, GeneticScheduler
        from .services.publication import publish
        publish(self.schedules[0], self.actor)
        draft = self.schedules[1]
        genes = [Gene(e.assignment_id, e.room_id, e.day, e.start_time, e.end_time)
                 for e in draft.entries.order_by('pk')]
        ga = GeneticScheduler(draft.term, m.GASettings(population_size=2, generations=0), seed=17,
                              repair_budget=0)
        before = m.Schedule.objects.count()
        with patch.object(ga, '_random_chromosome', return_value=genes):
            with self.assertRaisesMessage(ValueError, 'conflict'):
                ga.generate()
        self.assertEqual(m.Schedule.objects.count(), before)

    def test_external_effective_instructor_and_room_are_independent(self):
        from .services.publication import publish
        publish(self.schedules[0], self.actor)
        draft = self.schedules[1]
        faculty = m.Faculty.objects.create(department=self.department, employee_id='isolated', full_name='Other')
        room = m.Room.objects.create(name='Isolated', room_type='LECTURE', capacity=30)
        draft.entries.update(faculty_override=faculty)
        self.assertEqual({i['issue'].category for i in schedule_validation_issues(draft)}, {'ROOM_CONFLICT'})
        draft.entries.update(faculty_override=None, room=room)
        self.assertEqual({i['issue'].category for i in schedule_validation_issues(draft)}, {'FACULTY_CONFLICT'})
        draft.entries.update(faculty_override=faculty)
        self.assertEqual(schedule_validation_issues(draft), [])
