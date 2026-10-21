"""T4 section availability uses the same policy and backend gates as faculty."""
from datetime import time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from . import models as m
from .services.ga import Gene, GeneticScheduler
from .services.conflicts import schedule_validation_issues
from .services.manual_edits import FIELDS, revision_token, save_manual_entry
from .services.publication import publish
from .services.reproducibility import input_summary
from .test_known_defects import SchedulingDefectFixture


class SectionAvailabilityTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('section-admin')
        self.schedule = m.Schedule.objects.create(term=self.term, name='Section test')
        self.entries = [self.schedule.entries.create(assignment=a, room=self.room,
            day=0, start_time=time(8+i), end_time=time(9+i)) for i, a in enumerate(self.meetings)]

    def period(self, kind='UNAVAILABLE', start=time(8), end=time(9)):
        return m.Availability.objects.create(section=self.section, day=0,
            start_time=start, end_time=end, kind=kind)

    def test_default_policy_preserves_existing_schedule(self):
        self.assertEqual(schedule_validation_issues(self.schedule), [])
        self.assertEqual(self.scheduler().fitness([Gene(e.assignment_id, e.room_id, e.day,
            e.start_time, e.end_time) for e in self.entries]).hard_violations, 0)

    def test_unavailable_partial_overlap_and_adjacency(self):
        self.period()
        ga = self.scheduler()
        for start, end, blocked in [(time(7,30), time(8,30), True),
                (time(8), time(9), True), (time(9), time(10), False)]:
            with self.subTest(start=start):
                gene = Gene(self.meetings[0].pk, self.room.pk, 0, start, end)
                self.assertEqual(ga.fitness([gene]).hard_violations, int(blocked))
        self.entries[1].full_clean()
        with self.assertRaisesMessage(ValidationError, 'Section is unavailable'):
            self.entries[0].full_clean()

    def test_available_window_closes_other_days_and_off_grid_generation(self):
        self.period('AVAILABLE', time(8,10), time(10,10))
        ga = GeneticScheduler(self.term, m.GASettings(population_size=4, generations=2, elitism=1), seed=13)
        for a in self.meetings:
            options = ga.placement_options(a)
            self.assertTrue(options)
            self.assertIn(Gene(a.pk, self.room.pk, 0, time(8,10), time(9,10)), options)
            self.assertTrue(all(g.day == 0 and g.start_time >= time(8,10) and g.end_time <= time(10,10)
                                for g in options))
        generated = ga.generate()
        self.assertEqual(schedule_validation_issues(generated), [])

    def test_manual_and_publication_reject_section_unavailability_atomically(self):
        self.period()
        entry = self.entries[0]
        baseline = self.schedule.updated_at
        with self.assertRaisesMessage(ValidationError, 'Section is unavailable'):
            save_manual_entry(schedule_id=self.schedule.pk, entry_id=entry.pk, actor=self.admin,
                revision=revision_token(self.schedule, self.admin, entry),
                proposed={f: getattr(entry, f) for f in FIELDS})
        with self.assertRaisesMessage(ValidationError, 'Resolve conflicts'):
            publish(self.schedule, self.admin)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.updated_at, baseline)
        self.assertEqual(self.schedule.status, 'DRAFT')
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())

    def test_valid_available_schedule_publishes(self):
        self.period('AVAILABLE', time(8), time(10))
        published, _ = publish(self.schedule, self.admin)
        self.assertEqual(published.status, 'PUBLISHED')

    def test_effective_section_override_uses_its_own_windows(self):
        other = m.Section.objects.create(program=self.section.program,
            year_level=self.section.year_level, name='B', size=20)
        self.period()
        entry = self.entries[0]
        entry.section_override = other
        entry.full_clean()
        m.Availability.objects.create(section=other, day=0, start_time=time(8), end_time=time(9), kind='UNAVAILABLE')
        with self.assertRaisesMessage(ValidationError, 'Section is unavailable'):
            entry.full_clean()

    def test_administrative_crud_and_faculty_cannot_set_section_owner(self):
        self.client.force_login(self.admin)
        payload = {'section': self.section.pk, 'day': 0, 'start_time': '08:00', 'end_time': '09:00', 'kind': 'UNAVAILABLE'}
        response = self.client.post(reverse('resource_create', args=['availability']), payload)
        self.assertEqual(response.status_code, 302)
        row = m.Availability.objects.get(section=self.section)
        self.assertContains(self.client.get(reverse('resource_list', args=['availability'])), str(self.section))
        self.assertEqual(self.client.post(reverse('resource_update', args=['availability', row.pk]),
            {**payload, 'start_time': '09:00', 'end_time': '10:00'}).status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.start_time, time(9))
        user = User.objects.create_user('teacher')
        m.Profile.objects.update_or_create(user=user, defaults={'role': m.Role.FACULTY})
        self.faculty.user = user
        self.faculty.save()
        self.client.force_login(user)
        self.assertNotEqual(self.client.post(reverse('resource_create', args=['availability']), payload).status_code, 200)
        response = self.client.post(reverse('my_availability_create'), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(m.Availability.objects.filter(section=self.section).count(), 1)
        self.assertTrue(m.Availability.objects.filter(faculty=self.faculty, section__isnull=True).exists())

    def test_owner_constraint_and_no_section_preferences(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            m.Availability.objects.create(section=self.section, faculty=self.faculty,
                day=0, start_time=time(8), end_time=time(9))
        record = m.Availability(section=self.section, day=0, start_time=time(8), end_time=time(9), kind='PREFERRED')
        with self.assertRaisesMessage(ValidationError, 'Available or Unavailable'):
            record.full_clean()

    def test_section_availability_changes_input_fingerprint(self):
        before = input_summary(self.scheduler())
        self.period()
        after = input_summary(self.scheduler())
        self.assertEqual(after['schema'], 'schedease-inputs-v2')
        self.assertNotEqual(before['sha256'], after['sha256'])

    def test_faculty_unavailability_manual_and_publication_then_valid_window(self):
        row = m.Availability.objects.create(faculty=self.faculty, day=0,
            start_time=time(8), end_time=time(9), kind='UNAVAILABLE')
        entry = self.entries[0]
        with self.assertRaisesMessage(ValidationError, 'Faculty is unavailable'):
            save_manual_entry(schedule_id=self.schedule.pk, entry_id=entry.pk, actor=self.admin,
                revision=revision_token(self.schedule, self.admin, entry),
                proposed={f: getattr(entry, f) for f in FIELDS})
        with self.assertRaisesMessage(ValidationError, 'Resolve conflicts'):
            publish(self.schedule, self.admin)
        row.kind, row.end_time = 'AVAILABLE', time(10)
        row.save()
        self.assertEqual(schedule_validation_issues(self.schedule), [])
        self.assertEqual(publish(self.schedule, self.admin)[0].status, 'PUBLISHED')

    def test_ga_rechecks_section_availability_changed_after_initialization(self):
        from unittest.mock import patch
        ga = GeneticScheduler(self.term, m.GASettings(population_size=2, generations=0), seed=13, repair_budget=0)
        genes = [Gene(e.assignment_id, e.room_id, e.day, e.start_time, e.end_time) for e in self.entries]
        self.period()
        before = m.Schedule.objects.count()
        with patch.object(ga, '_random_chromosome', return_value=genes):
            with self.assertRaisesMessage(ValueError, 'Section is unavailable'):
                ga.generate()
        self.assertEqual(m.Schedule.objects.count(), before)

    def test_unavailable_overrides_available_and_rejects_empty_domain(self):
        self.period('AVAILABLE', time(8), time(9))
        self.period('UNAVAILABLE', time(8), time(9))
        with self.assertRaisesMessage(ValueError, 'No common faculty, section and room'):
            self.scheduler().placement_options(self.meetings[0])
