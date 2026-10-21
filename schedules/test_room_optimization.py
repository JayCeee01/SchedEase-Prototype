"""T9 room allocation evidence and effective-section reporting regressions."""
from datetime import time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.ga import Gene, GeneticScheduler
from .services.room_utilization import utilization_rows, utilization_summary
from .services.conflicts import schedule_validation_messages


class RoomOptimizationTests(SchedulingDefectFixture):
    def test_report_uses_effective_section_size_and_department(self):
        department = m.Department.objects.create(code='OTHER', name='Other department')
        program = m.Program.objects.create(department=department,code='OTHER',name='Other')
        year = m.YearLevel.objects.create(level=2,label='Year 2')
        section = m.Section.objects.create(program=program,year_level=year,name='B',size=10)
        schedule = m.Schedule.objects.create(term=self.term,name='Authorized section correction')
        entry = m.ScheduleEntry(schedule=schedule,assignment=self.meetings[0],section_override=section,
                                room=self.room,day=0,start_time=time(8),end_time=time(9))
        entry.full_clean()
        entry.save()
        row = utilization_rows(schedule)[0]
        self.assertEqual(row.capacity_utilization,33.3)
        self.assertEqual(utilization_rows(schedule,department)[0].scheduled_hours,1)
        self.assertEqual(utilization_rows(schedule,self.department)[0].scheduled_hours,0)
        import csv, io
        admin = User.objects.create_superuser('t9-report',password='test')
        self.client.force_login(admin)
        response = self.client.get('/schedules/room-utilization/export/csv/', {'schedule':schedule.pk,'department':department.pk})
        self.assertEqual(response.status_code,200)
        exported = list(csv.DictReader(io.StringIO(response.content.decode())))[0]
        self.assertEqual(float(exported['Seat Utilization %']),33.3)
        self.assertEqual(float(exported['Scheduled Hours']),1)

    def prepare_rooms(self):
        large = m.Room.objects.create(name='Large',room_type='LECTURE',capacity=100)
        for room in (self.room,large):
            m.Availability.objects.create(room=room,day=0,start_time=time(8),end_time=time(10),kind='AVAILABLE')
        return large

    def genes(self, room):
        return [Gene(a.pk,room.pk,0,time(8+i),time(9+i)) for i,a in enumerate(self.meetings)]

    def test_capacity_fit_is_soft_and_cannot_override_feasibility(self):
        large = self.prepare_rooms()
        ga = self.scheduler()
        fit, oversized = self.genes(self.room), self.genes(large)
        self.assertEqual(ga.fitness(fit).hard_violations,0)
        self.assertEqual(ga.fitness(oversized).hard_violations,0)
        self.assertGreater(ga.fitness(fit),ga.fitness(oversized))
        invalid = [fit[0], Gene(self.meetings[1].pk,self.room.pk,0,time(8),time(9))]
        self.assertGreater(ga.fitness(oversized),ga.fitness(invalid))

    def test_seeded_generation_and_measured_room_fit(self):
        large = self.prepare_rooms()
        baseline = m.Schedule.objects.create(term=self.term,name='Feasible oversized baseline')
        for a,gene in zip(self.meetings,self.genes(large)):
            baseline.entries.create(assignment=a,room=large,day=gene.day,start_time=gene.start_time,end_time=gene.end_time)
        self.assertEqual(schedule_validation_messages(baseline),[])
        settings = m.GASettings(population_size=20,generations=10,elitism=2,crossover_rate=0.8,mutation_rate=0.1)
        first = GeneticScheduler(self.term,settings,seed=19).generate('T9 seed 19')
        second = GeneticScheduler(self.term,settings,seed=19).generate('T9 repeated')
        fields = ('assignment_id','room_id','day','start_time','end_time')
        self.assertEqual(list(first.entries.order_by('assignment_id').values_list(*fields)),list(second.entries.order_by('assignment_id').values_list(*fields)))
        self.assertEqual(set(first.entries.values_list('room_id',flat=True)),{self.room.pk})
        self.assertEqual(set(baseline.entries.values_list('room_id',flat=True)),{large.pk})
        self.assertEqual(schedule_validation_messages(first),[])
        before = utilization_rows(baseline)
        after = utilization_rows(first)
        before_used = next(r for r in before if r.scheduled_hours)
        after_used = next(r for r in after if r.scheduled_hours)
        self.assertEqual((before_used.capacity_utilization,after_used.capacity_utilization),(20,66.7))
        self.assertEqual((utilization_summary(before)['average_utilization'],utilization_summary(after)['average_utilization']),(50,50))
        self.assertEqual(sum(r.exact_scheduled_hours for r in after),2)
        self.assertEqual(sum(r.exact_available_hours for r in after),4)
        self.assertEqual(sum(r.assigned_classes for r in after),2)
        self.assertEqual(utilization_summary(after)['unused_rooms'],1)
        def unused_seat_hours(schedule):
            return sum((e.room.capacity-e.effective_section.size) * (e.end_time.hour-e.start_time.hour) for e in schedule.entries.all())
        self.assertEqual((unused_seat_hours(baseline),unused_seat_hours(first)),(160,20))
        print('T9 measured seed19: seat occupancy 20% -> 66.7%; unused seat-hours 160 -> 20; room-time utilization 50% -> 50%; hard violations 0 -> 0. Existing optimizer, not a GA change.')

    def test_larger_room_remains_valid_when_fitting_room_unavailable(self):
        large = self.prepare_rooms()
        m.Availability.objects.create(room=self.room,day=0,start_time=time(8),end_time=time(10),kind='UNAVAILABLE')
        ga = self.scheduler()
        self.assertEqual({g.room_id for a in ga.assignments for g in ga.placement_options(a)},{large.pk})

    def test_shared_room_across_departments_and_year_levels(self):
        department = m.Department.objects.create(code='SHARED',name='Shared')
        program = m.Program.objects.create(department=department,code='SHARED',name='Shared')
        year = m.YearLevel.objects.create(level=2,label='Year 2')
        section = m.Section.objects.create(program=program,year_level=year,name='B',size=25)
        subject = m.Subject.objects.create(department=department,code='SH101',title='Shared course',lecture_hours=1,lab_hours=0)
        teacher = m.Faculty.objects.create(department=department,employee_id='SHARED',full_name='Shared teacher')
        meeting = m.TeachingAssignment.objects.create(term=self.term,subject=subject,section=section,faculty=teacher,component='LECTURE',duration_minutes=60)
        ga = self.scheduler()
        self.assertIn(self.room.pk,{g.room_id for g in ga.placement_options(ga.assignment_map[meeting.pk])})
        schedule = m.Schedule.objects.create(term=self.term,name='Cross department')
        for a, hour in [(self.meetings[0],8),(self.meetings[1],9),(meeting,10)]:
            entry = m.ScheduleEntry(schedule=schedule,assignment=a,room=self.room,day=0,start_time=time(hour),end_time=time(hour+1))
            entry.full_clean();entry.save()
        from .services.publication import publish
        admin = User.objects.create_superuser('t9publisher',password='test')
        published,_ = publish(schedule,admin)
        self.assertEqual(published.status,'PUBLISHED')
        self.assertEqual(utilization_rows(published,self.department)[0].scheduled_hours,2)
        self.assertEqual(utilization_rows(published,department)[0].scheduled_hours,1)


    def test_manual_and_publication_reject_room_violations(self):
        from .services.manual_edits import FIELDS, revision_token, save_manual_entry
        from .services.publication import publish
        admin = User.objects.create_superuser('t9-constraints',password='test')
        cases = [('Small','LECTURE',10,True,'capacity'), ('Wrong type','SCIENCE_LAB',30,True,'Room type'),
                 ('Inactive','LECTURE',30,False,'inactive'), ('Unavailable','LECTURE',30,True,'unavailable')]
        for name,kind,capacity,active,reason in cases:
            with self.subTest(case=name):
                room = m.Room.objects.create(name=name,room_type=kind,capacity=capacity,is_active=active)
                if name == 'Unavailable':
                    m.Availability.objects.create(room=room,day=0,start_time=time(8),end_time=time(10),kind='UNAVAILABLE')
                schedule = m.Schedule.objects.create(term=self.term,name=name)
                proposed = m.ScheduleEntry(assignment=self.meetings[0],room=room,day=0,start_time=time(8),end_time=time(9))
                with self.assertRaises(ValidationError):
                    save_manual_entry(schedule_id=schedule.pk,entry_id=None,actor=admin,
                        revision=revision_token(schedule,admin),proposed={f:getattr(proposed,f) for f in FIELDS})
                self.assertFalse(schedule.entries.exists())
                # Simulate pre-existing bad draft data to test the publication boundary.
                for i,meeting in enumerate(self.meetings):
                    schedule.entries.create(assignment=meeting,room=room,day=0,start_time=time(8+i),end_time=time(9+i))
                self.assertIn(reason,' '.join(schedule_validation_messages(schedule)))
                schedule.refresh_from_db()
                with self.assertRaises(ValidationError):
                    publish(schedule,admin)
                schedule.refresh_from_db()
                self.assertEqual(schedule.status,'DRAFT')
                self.assertFalse(m.ScheduleSnapshot.objects.filter(schedule=schedule).exists())


    def test_existing_distribution_penalty_rewards_equal_capacity_room_use(self):
        second = m.Room.objects.create(name='Equally suitable',room_type='LECTURE',capacity=30)
        m.Room.objects.create(name='Unneeded laboratory',room_type='SCIENCE_LAB',capacity=30)
        ga = self.scheduler()
        concentrated = self.genes(self.room)
        distributed = [concentrated[0],Gene(self.meetings[1].pk,second.pk,0,time(9),time(10))]
        self.assertEqual(ga.fitness(distributed).hard_violations,0)
        self.assertEqual(ga._room_utilization_penalty(concentrated),11)
        self.assertEqual(ga._room_utilization_penalty(distributed),0)
        self.assertGreater(ga.fitness(distributed),ga.fitness(concentrated))
