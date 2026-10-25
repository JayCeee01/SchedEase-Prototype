"""T10 bounded incumbent repair. Proposals never write schedule placements."""
import hashlib
import json
from copy import copy
from datetime import time
from itertools import combinations
from time import perf_counter
from types import SimpleNamespace
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction, connection
from schedules import models as m
from .manual_edits import authorized_administrator, copy_to_draft, revision_token, manual_edit_transaction, values
from .repair_rules import windows, entry_errors, scenario_days
from .conflicts import validate_entry, individual_entry_errors, schedule_validation_messages
from .meetings import scheduled_requirement_errors
from .placements import PlacementOccupancy
from .ga import Gene, GeneticScheduler
from .availability import AvailabilityPolicy
from .credentials import teaching_eligibility
from .time import ALLOWED_DAYS, slot_starts, add_minutes, SCHOOL_END
from .workload_balancing import fingerprint

SALT = 'smart-repair-v1'
BUDGET = 6000


def setup(schedule):
    record = schedule.edit_audits.filter(new_values__action='smart_repair_setup').order_by('-pk').first()
    if record is None:
        raise ValidationError('Create a repair draft from a published schedule first.')
    return record.new_values


def stamp(schedule):
    return hashlib.sha256((fingerprint() + json.dumps(windows(schedule),sort_keys=True) + json.dumps(setup(schedule),sort_keys=True)).encode()).hexdigest()


def validate_scenario(source, scenario):
    kind = scenario.get('kind')
    if kind not in ('faculty','room','sections'):
        raise ValidationError('Choose an instructor, room or additional-section scenario.')
    scenario = dict(scenario)
    entries = list(source.entries.select_related('assignment__faculty','faculty_override'))
    if kind in ('faculty','room'):
        try:
            start, end = time.fromisoformat(scenario['start']),time.fromisoformat(scenario['end'])
        except (ValueError,KeyError,TypeError) as exc:
            raise ValidationError('Enter a valid recurring time window.') from exc
        days = scenario_days(scenario)
        if not isinstance(days, (list, tuple)) or not days or any(type(day) is not int or day not in ALLOWED_DAYS for day in days):
            raise ValidationError('Select at least one day from Monday to Saturday.')
        scenario['days'] = sorted(set(days))
        scenario.pop('day', None)
        if start >= end or start.second or end.second or start.microsecond or end.microsecond:
            raise ValidationError('Use a weekday and whole-minute start time before the end time.')
        owners = {e.effective_faculty.pk if kind=='faculty' else e.room_id for e in entries}
        if scenario['resource'] not in owners:
            raise ValidationError('Select a resource used by this published schedule.')
    else:
        ids = scenario.get('sections',[])
        available = set(m.TeachingAssignment.objects.filter(term=source.term,section_id__in=ids).exclude(
            pk__in=source.entries.values_list('assignment_id',flat=True)).values_list('section_id',flat=True))
        if not ids or set(ids) != available:
            raise ValidationError('Select new sections with recorded, unscheduled teaching assignments in this term.')
    eligible = set(scenario.get('replacement_meetings',[]))
    replacements = scenario.get('replacements',[])
    if replacements or eligible:
        if kind != 'faculty' or not replacements or not eligible or not scenario.get('comparable'):
            raise ValidationError('Explicitly select eligible meetings and comparable replacement instructors.')
        allowed = {e.assignment_id for e in entries if e.effective_faculty.pk == scenario['resource']}
        original = m.Faculty.objects.get(pk=scenario['resource'])
        teachers = list(m.Faculty.objects.filter(pk__in=replacements))
        if (not eligible.issubset(allowed) or len(teachers)!=len(set(replacements)) or len(teachers)>3
                or any(f.pk==original.pk or f.department_id!=original.department_id or f.max_weekly_hours<=0 for f in teachers)):
            raise ValidationError('Use up to three distinct replacements from the original instructor’s department and authorized meetings only.')
    return scenario


@transaction.atomic
def create_draft(source_id, actor, scenario):
    authorized_administrator(actor)
    source = m.Schedule.objects.get(pk=source_id)
    if source.status != m.ScheduleStatus.PUBLISHED:
        raise ValidationError('Start repair from a currently published schedule.')
    # Existing copy service reserves the SQLite writer before reading/copying entries.
    draft = copy_to_draft(source_id=source_id,actor=actor)
    source.refresh_from_db()
    if source.status != m.ScheduleStatus.PUBLISHED:
        raise ValidationError("The source is no longer published. Start again.")
    scenario = validate_scenario(source,scenario)
    m.ScheduleEntryAudit.objects.create(schedule=draft,user=actor,previous_values={},new_values={
        'action':'smart_repair_setup','source':source.pk,'source_version':source.updated_at.isoformat(),'scenario':scenario})
    return draft


def gene(entry):
    return Gene(entry.assignment_id,entry.room_id,entry.day,entry.start_time,entry.end_time)


def mapping(entries):
    return {e.assignment_id:SimpleNamespace(faculty_id=e.effective_faculty.pk,section_id=e.effective_section.pk) for e in entries}


def describe(entry):
    return dict(meeting=entry.assignment_id,subject=entry.effective_subject.code,section=str(entry.effective_section),
        faculty=entry.effective_faculty.full_name,faculty_id=entry.effective_faculty.pk,room=entry.room.name,
        room_id=entry.room_id,day=entry.day,start=entry.start_time.isoformat(),end=entry.end_time.isoformat())


def differences(original, proposed, affected):
    originals = {e.assignment_id:e for e in original}
    rows, counts = [], dict(preserved=0,modified=0,added=0,time_changes=0,room_changes=0,instructor_changes=0,unaffected_changes=0)
    for entry in proposed:
        old = originals.get(entry.assignment_id)
        before, after = describe(old) if old else None,describe(entry)
        state = 'Added' if old is None else 'Preserved' if before==after else 'Modified'
        counts[state.lower()] += 1
        if old:
            counts['time_changes'] += (old.day,old.start_time,old.end_time)!=(entry.day,entry.start_time,entry.end_time)
            counts['room_changes'] += old.room_id!=entry.room_id
            counts['instructor_changes'] += old.effective_faculty.pk!=entry.effective_faculty.pk
            counts['unaffected_changes'] += state=='Modified' and entry.assignment_id not in affected
        rows.append(dict(before=before,after=after,state=state,reason={
            'Added':'Recorded teaching requirement inserted into a feasible placement.',
            'Preserved':'Existing placement and instructor retained.',
            'Modified':'Moved to satisfy the recurring restriction and shared scheduling constraints.'}[state]))
    counts['preserved_percent'] = 100*counts['preserved']/len(original) if original else 100
    return rows, counts


def propose(draft_id, actor):
    authorized_administrator(actor)
    draft = m.Schedule.objects.select_related('term').get(pk=draft_id)
    if draft.status != 'DRAFT':
        raise ValidationError('Only repair drafts can be changed.')
    data=setup(draft); scenario=data['scenario']
    source=m.Schedule.objects.get(pk=data['source'])
    if source.status!='PUBLISHED' or source.updated_at.isoformat()!=data['source_version']:
        raise ValidationError('The published source changed. Start a new repair draft.')
    initial_stamp=stamp(draft); started=perf_counter()
    original=list(draft.entries.select_related('assignment__subject','assignment__faculty','assignment__section',
        'faculty_override','section_override','subject_override','room','schedule__term').order_by('assignment_id'))
    all_entries=list(original)
    if scenario['kind']=='sections':
        for a in m.TeachingAssignment.objects.filter(term=draft.term,section_id__in=scenario['sections']).exclude(
                pk__in=[e.assignment_id for e in original]).select_related('subject','faculty','section'):
            all_entries.append(m.ScheduleEntry(schedule=draft,assignment=a,day=0,start_time=time(7),end_time=add_minutes(time(7),a.required_duration_minutes)))
    if len(all_entries)>40:
        raise ValidationError('Repair currently supports up to 40 meetings per draft.')
    rule_windows=windows(draft)
    draft._repair_windows=rule_windows
    requirement_errors=scheduled_requirement_errors(draft, all_entries)
    missing=m.TeachingAssignment.objects.filter(term=draft.term).exclude(pk__in=[e.assignment_id for e in all_entries])
    if missing.exists():
        requirement_errors.append('Other recorded classes are missing from this draft. Include their sections before requesting a complete repair.')
    external=m.Schedule.objects.filter(status="PUBLISHED").exclude(term=draft.term).exists()
    policies={}; preferred={}
    for e in all_entries:
        e.schedule=draft
    affected={e.assignment_id for e in all_entries if not e.pk or entry_errors(e)}
    domains={}; blockers=list(requirement_errors); candidate_checks=0
    rooms=list(m.Room.objects.filter(is_active=True).order_by('pk'))
    from .room_compatibility import meeting_room_errors
    for entry in all_entries:
        room_errors = meeting_room_errors(entry.assignment)
        if room_errors:
            blockers.extend(room_errors)
            domains[entry.assignment_id] = []
            continue
        options=[]
        faculty=[entry.effective_faculty]
        if entry.assignment_id in scenario.get('replacement_meetings',[]) and entry.assignment_id in affected:
            faculty+=list(m.Faculty.objects.filter(pk__in=scenario.get('replacements',[])).order_by('pk'))
        for f in faculty:
            if not teaching_eligibility(f,entry.effective_subject,draft.term,entry.assignment)['eligible']:
                blockers.append(f'{entry.effective_subject.code}: {f.full_name} does not meet term-wide qualification requirements.');continue
            faculty_policy=AvailabilityPolicy.for_resource(f)
            policies[f.pk]=faculty_policy
            preferred[f.pk]=list(f.availability_set.filter(kind="PREFERRED"))
            section_policy=AvailabilityPolicy.for_resource(entry.effective_section)
            duration=entry.assignment.required_duration_minutes
            starts=set(slot_starts(duration))|{entry.start_time}
            suitable=[r for r in rooms if r.capacity>=entry.effective_section.size and r.room_type==entry.assignment.effective_room_type]
            if not suitable:
                blockers.append(f'{entry.effective_subject.code}: no active room meets capacity and type requirements.')
            for room in suitable:
                policy=AvailabilityPolicy.for_resource(room)
                for day in ALLOWED_DAYS:
                    boundaries=set(starts)
                    for p in (faculty_policy,section_policy,policy):
                        for left,right in p.effective_intervals(day):
                            boundaries.update((left,add_minutes(right,-duration)))
                    for window in rule_windows:
                        if day in scenario_days(window):
                            boundaries.update((time.fromisoformat(window['end']),add_minutes(time.fromisoformat(window['start']),-duration)))
                    for start in sorted(boundaries):
                        candidate_checks += 1
                        if candidate_checks > 100000:
                            raise ValidationError('Candidate limit reached. Review availability or narrow the repair scope; no placements were changed.')
                        end=add_minutes(start,duration)
                        if end<=start or end>SCHOOL_END or any(p.rejection_reason(day,start,end) for p in (faculty_policy,section_policy,policy)):
                            continue
                        candidate=copy(entry);candidate._state=copy(entry._state);candidate._state.fields_cache=entry._state.fields_cache.copy()
                        candidate.room=room;candidate.day=day;candidate.start_time=start;candidate.end_time=end
                        candidate.faculty_override=f if f.pk!=entry.assignment.faculty_id else None
                        # Validate the candidate without stale incumbent overlap/workload rows.
                        candidate.schedule=m.Schedule(pk=-1,term=draft.term,name='Repair validation')
                        candidate.schedule._repair_windows=rule_windows
                        try:
                            if external:
                                validate_entry(candidate)
                            elif individual_entry_errors(candidate, eligible=True, faculty_policy=faculty_policy,
                                    room_policy=policy, section_policy=section_policy):
                                continue
                        except ValidationError:
                            continue
                        candidate.schedule=draft
                        options.append(candidate)
        domains[entry.assignment_id]=sorted(options,key=lambda e:(
            (e.day,e.start_time,e.end_time)!=(entry.day,entry.start_time,entry.end_time),e.room_id!=entry.room_id,
            e.effective_faculty.pk!=entry.effective_faculty.pk,e.day,e.start_time,e.room_id,e.effective_faculty.pk))
        if not options:
            blockers.append(f'{entry.effective_subject.code} / {entry.effective_section}: no candidate time and room satisfies current availability, qualifications and published-term constraints.')
    affected.update(e.assignment_id for e in original if not any(describe(e)==describe(o) for o in domains[e.assignment_id]))
    scorer=GeneticScheduler(draft.term,m.GASettings(),seed=0)
    visits=0;best=None;best_cost=None;stage_used='No solution';capped=False
    baseline={e.assignment_id:e for e in all_entries}
    # Existing unaffected placements are hard-frozen in the first two stages.
    stages=[('Direct same-instructor repair',affected,False)]
    if scenario.get('replacements'):
        stages.append(('Explicitly authorized replacement',affected,True))
    if scenario.get('rearrange'):
        resources={(e.effective_faculty.pk,e.effective_section.pk,e.room_id) for e in all_entries if e.assignment_id in affected}
        related=[e.assignment_id for e in original if e.assignment_id not in affected and any(
            e.effective_faculty.pk==f or e.effective_section.pk==s or e.room_id==r for f,s,r in resources)][:6]
        for size in (1,2):
            stages.extend(('Limited rearrangement',affected|set(extra),bool(scenario.get('replacements'))) for extra in combinations(related,size))
    load_failures=set()
    def compatible(candidate,chosen):
        entries=chosen+[candidate]
        if PlacementOccupancy(mapping(entries),[gene(e) for e in chosen]).conflicts(gene(candidate)):
            return False
        total=sum(e.assignment.required_duration_minutes for e in entries if e.effective_faculty.pk==candidate.effective_faculty.pk)
        if total>candidate.effective_faculty.max_weekly_hours*60:
            load_failures.add(f'{candidate.effective_faculty.full_name}: combined weekly workload would exceed the {candidate.effective_faculty.max_weekly_hours}-hour limit.')
            return False
        return True
    def search(todo,chosen,replace):
        nonlocal visits,best,best_cost,capped
        if visits>=BUDGET:
            capped=True;return
        if not todo:
            if requirement_errors:
                return
            rows,counts=differences(original,chosen,affected)
            scorer.assignment_map={}
            for e in chosen:
                a=copy(e.assignment);a._state=copy(e.assignment._state);a._state.fields_cache=e.assignment._state.fields_cache.copy()
                a.faculty=e.effective_faculty;a.section=e.effective_section
                scorer.assignment_map[a.pk]=a
                scorer.qualification_cache[a.pk]=True
                scorer.faculty_policies[a.faculty_id]=policies[a.faculty_id]
                # Existing GA section policies already cover recorded term assignments.
                scorer.faculty_preferred[a.faculty_id]=preferred[a.faculty_id]
            scorer._fitness_cache.clear()
            soft=scorer.fitness([gene(e) for e in chosen]).soft_score
            cost=tuple(counts[k] for k in ('unaffected_changes','time_changes','room_changes','instructor_changes'))+(-soft,)
            if best_cost is None or cost<best_cost:
                best,best_cost=list(chosen),cost
            return
        pk=todo[0]
        for candidate in domains[pk]:
            if not replace and candidate.effective_faculty.pk!=baseline[pk].effective_faculty.pk:
                continue
            visits+=1
            if compatible(candidate,chosen):
                search(todo[1:],chosen+[candidate],replace)
            if visits>=BUDGET:
                capped=True;break
    best_scope=None
    for stage,movable,replace in stages:
        scope=(stage,len(movable))
        if best is not None and scope != best_scope:
            break
        if requirement_errors:
            break
        frozen=[e for e in original if e.assignment_id not in movable]
        checked=[]
        for e in frozen:
            if not compatible(e,checked):break
            checked.append(e)
        if len(checked)!=len(frozen) or any(entry_errors(e) for e in frozen):
            continue
        search(sorted(movable,key=lambda pk:(len(domains[pk]),pk)),frozen,replace)
        if best is not None:
            stage_used=stage
            best_scope=scope
        if capped:break
    if initial_stamp!=stamp(draft):
        raise ValidationError('Scheduling inputs changed during repair. Generate a new preview.')
    elapsed=perf_counter()-started
    if best is None:
        reasons=list(dict.fromkeys(blockers+sorted(load_failures)))
        reasons.append('Search limit reached; infeasibility is not proven.' if capped else 'No feasible repair was found within the authorized direct/replacement/limited scope. Administrator review is required.')
        if not scenario.get('replacements'):
            reasons.append('No instructor replacements were authorized. Parent assignments remain locked and unchanged.')
        return dict(success=False,affected=len(affected),unresolved=len(affected),reasons=reasons,seconds=elapsed,attempts=visits,token=None,
            affected_classes=[f'{e.effective_subject.code} / {e.effective_section}' for e in all_entries if e.assignment_id in affected])
    best.sort(key=lambda e:e.assignment_id)
    rows,counts=differences(original,best,affected)
    payload=dict(user=actor.pk,draft=draft.pk,stamp=initial_stamp,revision=revision_token(draft,actor),
        entries=[dict(assignment=e.assignment_id,entry=e.pk,faculty=e.faculty_override_id,room=e.room_id,day=e.day,start=e.start_time.isoformat(),end=e.end_time.isoformat()) for e in best])
    return dict(success=True,affected=len(affected),unresolved=0,rows=rows,counts=counts,hard_violations=0,
        seconds=elapsed,attempts=visits,stage=stage_used,capped=capped,
        token=signing.dumps(payload,salt=SALT,compress=True))


@transaction.atomic
def apply(draft_id,actor,token,confirmed=False):
    authorized_administrator(actor)
    if not confirmed:raise ValidationError('Confirm the repaired batch before applying it.')
    if connection.vendor!='sqlite':raise ValidationError('Repair application currently requires the verified SQLite backend.')
    try:payload=signing.loads(token,salt=SALT,max_age=1800)
    except signing.BadSignature as exc:raise ValidationError('This repair preview expired or is invalid.') from exc
    if payload['user']!=actor.pk or payload['draft']!=draft_id:raise ValidationError('This preview belongs to another user or draft.')
    # Writer reservation before fingerprint reads; audit rolls back with all edits.
    audit=m.ScheduleEntryAudit.objects.create(schedule_id=draft_id,user=actor,previous_values={},new_values={'action':'smart_repair_apply_pending'})
    draft=m.Schedule.objects.get(pk=draft_id)
    if stamp(draft)!=payload['stamp']:raise ValidationError('This repair preview is stale. Generate it again.')
    with manual_edit_transaction(schedule_id=draft_id,entry_id=None,actor=actor,revision=payload['revision'],draft_only=True) as (draft,_,__,user):
        before=[];after=[];instructor_overrides=[]
        for row in payload['entries']:
            e=draft.entries.get(pk=row['entry']) if row['entry'] else m.ScheduleEntry(schedule=draft,assignment_id=row['assignment'])
            previous=values(e) if e.pk else {}
            original_faculty=e.effective_faculty
            e.faculty_override_id=row['faculty'];e.room_id=row['room'];e.day=row['day']
            e.start_time=time.fromisoformat(row['start']);e.end_time=time.fromisoformat(row['end'])
            if e.effective_faculty.pk != original_faculty.pk:
                instructor_overrides.append({
                    'meeting_id':e.assignment_id,'entry_id':e.pk,
                    'original_faculty_id':original_faculty.pk,'original_faculty':original_faculty.full_name,
                    'replacement_faculty_id':e.effective_faculty.pk,'replacement_faculty':e.effective_faculty.full_name,
                    'reason':'Original instructor unavailable in the recurring window; no direct same-instructor repair found within the search scope.',
                    'scenario':setup(draft)['scenario'],
                })
            if previous!=values(e):
                e.save()
                m.ScheduleEntryAudit.objects.create(schedule=draft,entry=e,user=user,previous_values=previous,new_values=values(e))
            before.append(previous);after.append(values(e))
        errors=schedule_validation_messages(draft)
        if errors:raise ValidationError(errors)
        audit.previous_values={'entries':before}
        audit.new_values={'action':'smart_repair_apply','entries':after,'instructor_overrides':instructor_overrides}
        audit.save(update_fields=['previous_values','new_values'])
    return draft
