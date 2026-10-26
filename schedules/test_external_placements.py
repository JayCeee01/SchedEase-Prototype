from datetime import date, time

from . import models as m
from . import test_known_defects as fixtures
from . import test_smart_repair as repair_fixtures
from .services.ga import GeneticScheduler
from .services import smart_repair


def external(test, status='PUBLISHED', starts=date(2026,8,1), ends=date(2026,12,1), faculty=None, room=None, start=time(10), end=time(11)):
    term=m.AcademicTerm.objects.create(name='External',school_year='2026',starts_on=starts,ends_on=ends)
    parent=m.Assignment.objects.create(term=term,subject=test.subject,faculty=faculty or test.faculty,section=test.section)
    meeting=m.TeachingAssignment.objects.create(assignment=parent,component='LECTURE',meeting_index=1,duration_minutes=60)
    schedule=m.Schedule.objects.create(term=term,name='External')
    schedule.entries.create(assignment=meeting,room=room or test.room,day=0,start_time=start,end_time=end)
    schedule.status=status
    schedule.save()
    return schedule


class ExternalPlacementTests(fixtures.SchedulingDefectFixture):
    def options(self):
        ga=GeneticScheduler(self.term,m.GASettings(),seed=7)
        return {(g.room_id,g.day,g.start_time,g.end_time) for g in ga.placement_options(self.meetings[0])}

    def test_faculty_conflict_blocks_all_rooms_but_preserves_boundaries(self):
        alternate=m.Room.objects.create(name='Alternative',room_type='LECTURE',capacity=30)
        external(self)
        options=self.options()
        for room in (self.room,alternate):
            self.assertNotIn((room.pk,0,time(10),time(11)),options)
            self.assertNotIn((room.pk,0,time(9,30),time(10,30)),options)
            self.assertIn((room.pk,0,time(9),time(10)),options)
            self.assertIn((room.pk,0,time(11),time(12)),options)
            self.assertIn((room.pk,1,time(10),time(11)),options)

    def test_room_conflict_is_independent_of_faculty(self):
        other=m.Faculty.objects.create(department=self.department,employee_id='OTHER',full_name='Other')
        alternate=m.Room.objects.create(name='Alternative',room_type='LECTURE',capacity=30)
        external(self,faculty=other)
        options=self.options()
        self.assertNotIn((self.room.pk,0,time(10),time(11)),options)
        self.assertIn((alternate.pk,0,time(10),time(11)),options)

    def test_draft_does_not_reserve(self):
        external(self,status='DRAFT')
        self.assertIn((self.room.pk,0,time(10),time(11)),self.options())

    def test_off_grid_adjacency_and_correction_suggestions(self):
        from django.contrib.auth.models import User
        from .services.corrections import placement_suggestions
        external(self,start=time(10,10),end=time(11,10))
        self.assertIn((self.room.pk,0,time(11,10),time(12,10)),self.options())
        draft=m.Schedule.objects.create(term=self.term,name='Corrections')
        entry=draft.entries.create(assignment=self.meetings[0],room=self.room,day=0,start_time=time(10),end_time=time(11))
        actor=User.objects.create_superuser(username='suggestions-admin',password='test')
        suggestions=placement_suggestions(entry,actor,limit=200)
        self.assertTrue(suggestions)
        self.assertTrue(any(row['entry'].day==0 and row['entry'].start_time==time(11,10) for row in suggestions))
        for row in suggestions:
            item=row['entry']
            self.assertFalse(item.day==0 and item.start_time<time(11,10) and item.end_time>time(10,10))

    def test_archived_does_not_reserve(self):
        external(self,status='ARCHIVED')
        self.assertIn((self.room.pk,0,time(10),time(11)),self.options())

    def test_nonoverlapping_dates_do_not_reserve(self):
        external(self,starts=date(2027,1,1),ends=date(2027,3,1))
        self.assertIn((self.room.pk,0,time(10),time(11)),self.options())

    def test_overlapping_dates_without_shared_weekday_do_not_reserve(self):
        external(self,starts=date(2026,12,1),ends=date(2026,12,2))
        self.assertIn((self.room.pk,0,time(10),time(11)),self.options())


class ExternalRepairTests(fixtures.SchedulingDefectFixture):
    def setUp(self):
        repair_fixtures.SmartRepairTests.setUp(self)

    def test_repair_skips_published_external_slot(self):
        external(self)
        draft=repair_fixtures.SmartRepairTests.draft(self)
        result=smart_repair.propose(draft.pk,self.admin)
        self.assertTrue(result['success'],result)
        smart_repair.apply(draft.pk,self.admin,result['token'],confirmed=True)
        moved=draft.entries.get(assignment=self.meetings[0])
        self.assertEqual(moved.start_time,time(11))
        repair_fixtures.SmartRepairTests.assert_safe(self,draft)
