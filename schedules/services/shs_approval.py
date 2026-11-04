"""Immutable current-scope attestations, never inferred historical approvals."""
from contextvars import ContextVar
from contextlib import contextmanager
from importlib import import_module
import hashlib
import json

from django.core import signing
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connections, transaction
from django.db.models import F
from django.db.models.deletion import ProtectedError
from django.utils import timezone

policy = import_module('schedules.migrations.0033_shs_approval_scope')
SALT = 'schedease.shs-scope.v1'
_issuance = ContextVar('shs_scope_issuance', default=None)


def canonical(value):
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def evidence_allowed(term_id, actor_id, kind, reason, data):
    try:
        if isinstance(data, str): data = json.loads(data)
        return _issuance.get() is not None and _issuance.get() == (term_id, actor_id, kind, reason, data)
    except (ValueError, TypeError):
        return False


def register_connection(connection, **kwargs):
    if connection.vendor == 'sqlite':
        connection.connection.create_function('schedease_shs_scope_v1', 5,
            lambda *args: int(evidence_allowed(*args)))


def available(using='default'):
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='view' AND name=%s", [policy.VIEW])
        if cursor.fetchone(): return True
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='django_migrations'")
        if cursor.fetchone():
            cursor.execute("SELECT 1 FROM django_migrations WHERE app='schedules' AND name='0033_shs_approval_scope'")
            if cursor.fetchone(): raise ValidationError('SHS approval protection is unavailable. Review the database setup.')
    return False  # Earlier-schema disposable migration rehearsals.


def check_save(sender, instance, using='default', update_fields=None, **kwargs):
    _guard(instance, using=using, update_fields=update_fields)


def check_delete(sender, instance, using='default', **kwargs):
    try:
        _guard(instance, using=using, deleting=True)
    except ValidationError as exc:
        raise ProtectedError('; '.join(exc.messages), [instance])


def _guard(instance, *, using, deleting=False, update_fields=None):
    name = instance._meta.model_name
    if name not in policy.FIELDS or not available(using): return
    old = type(instance).objects.using(using).filter(pk=instance.pk).first() if instance.pk is not None else None
    event = 'delete' if deleting else 'update' if old else 'insert'
    fields = list(instance._meta.concrete_fields)
    values = {f.attname: getattr(instance,f.attname) for f in fields}
    if old and update_fields is not None:
        for f in fields:
            if f.name not in update_fields and f.attname not in update_fields:
                values[f.attname] = getattr(old,f.attname)
    if old and not deleting and all(getattr(old,col)==values[col] for col in policy.FIELDS[name].split()): return
    sql = policy.TRIGGERS[f'shs_scope_{name}_{event}'].split(' WHEN ',1)[1].split(' BEGIN ',1)[0]
    params, sources = [], []
    for alias, obj in (('OLD',old),('NEW',instance)):
        columns = []
        for f in fields:
            value = values[f.attname] if alias=='NEW' else getattr(obj,f.attname) if obj else None
            columns.append(f'%s AS "{f.column}"')
            params.append(f.get_db_prep_value(value, connections[using]))
        sources.append(f'(SELECT {",".join(columns)}) AS {alias}')
    with connections[using].cursor() as cursor:
        cursor.execute(f'SELECT 1 FROM {" CROSS JOIN ".join(sources)} WHERE {sql}',params)
        if cursor.fetchone(): raise ValidationError(policy.MESSAGE)


def scope(term):
    """Capture actual definitions; caller must validate and hold the write fence."""
    from schedules import models as m
    from .contact_workload import shs_contact_events, published_contact_events, validate_weekly_contact_limits
    from datetime import timedelta
    term = m.AcademicTerm.objects.get(pk=term.pk)
    records = {}
    def add(obj):
        if obj is None: return
        key=(obj._meta.model_name,obj.pk)
        if key in records: return
        definition={f.attname:getattr(obj,f.attname) for f in obj._meta.concrete_fields}
        records[key]={'model':key[0],'id':obj.pk,'definition':definition}
    def pathway(obj):
        visited=set()
        while obj:
            if obj.pk in visited: raise ValidationError('Resolve the pathway cycle before approving SHS inputs.')
            visited.add(obj.pk); add(obj); add(obj.curriculum_version); obj=obj.parent
    def cohort(obj):
        add(obj); add(obj.curriculum_version); pathway(obj.pathway)
    add(term)
    events=[]
    for config in m.SHSAssignmentConfiguration.objects.filter(assignment__term=term).order_by('pk'):
        add(config); add(config.assignment); add(config.assignment.faculty); add(config.assignment.subject)
        plan=config.delivery_plan; offering=plan.offering; requirement=offering.requirement
        for obj in (plan,offering,requirement,requirement.curriculum_version): add(obj)
        cohort(offering.cohort); pathway(requirement.pathway)
        for component in plan.components.order_by('pk'): add(component)
        for pattern in config.patterns.order_by('pk'): add(pattern); add(pattern.room)
        participants=[config.assignment.section]
        for row in config.additional_sections.select_related('section').order_by('pk'):
            add(row); participants.append(row.section)
        for section in participants:
            add(section); cohort(section.cohort); add(section.program); add(section.year_level); add(section.program.department)
        events.extend(shs_contact_events(config))
    if not events: raise ValidationError('No validated SHS teaching events are available for review.')
    first=min(e.teaching_date for e in events); last=max(e.teaching_date for e in events)
    first-=timedelta(days=first.weekday()); last+=timedelta(days=6-last.weekday())
    faculty={e.faculty_id for e in events}
    events.extend(e for e in published_contact_events(first,last,exclude_term_id=term.pk) if e.faculty_id in faculty)
    totals=validate_weekly_contact_limits(events)
    for faculty_id, week in totals:
        add(m.FacultyContactMinutePolicy.objects.get(faculty_id=faculty_id,is_active=True,is_verified=True,is_approved=True,
            starts_on__lte=week,ends_on__gte=week+timedelta(days=6)))
    bindings=list(m.SHSMeetingBinding.objects.filter(meeting__term=term).order_by('pk').values('id','meeting_id','pattern_id','data'))
    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT b.id,b.data FROM schedules_shsmeetingbinding b JOIN schedules_teachingassignment a ON a.id=b.meeting_id WHERE a.term_id=%s',[term.pk])
        stored=dict(cursor.fetchall())
    for item in bindings: item['stored_json']=stored[item['id']]
    schedules=list(m.Schedule.objects.filter(term=term,status__in=['PUBLISHED','ARCHIVED']).order_by('pk').values('id','status','updated_at'))
    snapshots=list(m.ScheduleSnapshot.objects.filter(schedule__term=term).order_by('pk').values('id','schedule_id','data'))
    result={'term_id':term.pk,'records':[records[key] for key in sorted(records)],'bindings':bindings,
            'finalized_state':{'schedules':schedules,'snapshot_digest':digest(snapshots)},
            'contact_events':[{'identity':e.identity,'faculty_id':e.faculty_id,'date':e.teaching_date,'minutes':e.minutes,'level':e.education_level} for e in events],
            'weekly_minutes':[{'faculty_id':faculty_id,'week':week,'minutes':minutes} for (faculty_id,week),minutes in sorted(totals.items())]}
    return json.loads(canonical(result))


def critical(data):
    from schedules.protection import FIELDS
    result=[]
    for row in data['records']:
        columns=policy.FIELDS.get(row['model'],FIELDS.get(row['model'],'' )).split()
        # Names are frozen display information, not new operational constraints.
        if row['model'] in ('section','faculty','room','subject'):
            columns=[c for c in columns if c not in ('name','full_name','title')]
        if row['model']=='academicpathway': columns=policy.FIELDS['academicpathway'].split()
        result.append((row['model'],row['id'],{k:row['definition'].get(k) for k in columns}))
    return {'records':result,'bindings':data['bindings'],'term_id':data['term_id']}


def validate_evidence(term):
    from schedules.models import SHSApprovalEvidence
    if not available(): return
    current=critical(scope(term))
    for evidence in SHSApprovalEvidence.objects.filter(term=term,schema_version=1).order_by('-pk'):
        try:
            if critical(evidence.data)==current: return
        except (TypeError,ValueError,KeyError): pass
    raise ValidationError('SHS approval scope is missing or changed. An authorized administrator must explicitly review and reapprove the current inputs. Historical approval remains unproven for legacy records.')


def preview(*, actor, term):
    from .manual_edits import authorized_administrator
    from .shs_scheduling import _prepared_inputs
    actor=authorized_administrator(actor)
    _prepared_inputs(term)
    data=scope(term)
    return data, signing.dumps({'actor':actor.pk,'term':term.pk,'digest':digest(data)},salt=SALT)


def _issue(actor,term,kind,reason,data):
    from schedules.models import SHSApprovalEvidence
    now=timezone.now()
    data={**data,'reviewed_at':now.isoformat(),'authority':{'user_id':actor.pk,'username':actor.username},
          'original_historical_scope_proven':kind=='PREPARATION',
          'meaning':'Current validated inputs only; not proof of original legacy approval.' if kind=='CURRENT_REVIEW' else 'Validated scope captured at new meeting preparation.'}
    token=_issuance.set((term.pk,actor.pk,kind,reason,data))
    try:
        return SHSApprovalEvidence.objects.create(term=term,actor=actor,kind=kind,reason=reason,data=data,created_at=now)
    finally: _issuance.reset(token)


@contextmanager
def new_preparation(*, actor, term):
    """Fence capture around creation, never attest pre-existing legacy bindings."""
    from .manual_edits import authorized_administrator
    from schedules.models import Schedule
    if not available():
        yield
        return
    if not connections['default'].in_atomic_block:
        raise ValidationError('SHS evidence requires the preparation transaction.')
    actor=authorized_administrator(actor)
    if term.teachingassignment_set.exists():
        raise ValidationError('Existing prepared meetings require explicit review, not automatic evidence capture.')
    if Schedule.objects.filter(term=term,status__in=['PUBLISHED','ARCHIVED']).exists():
        raise ValidationError('Existing historical SHS inputs require explicit current review, never automatic evidence backfill.')
    yield
    from .shs_scheduling import _prepared_inputs
    _prepared_inputs(term)
    _issue(actor,term,'PREPARATION','Authorized preparation of validated SHS inputs.',scope(term))


def reapprove(*, actor, term, scope_token, reason):
    from schedules.models import AcademicTerm, Schedule
    from .manual_edits import authorized_administrator
    from .shs_scheduling import _prepared_inputs
    from .conflicts import schedule_validation_messages
    if not reason or not reason.strip(): raise ValidationError('Record the reason and authority for this current review.')
    with transaction.atomic():
        if AcademicTerm.objects.filter(pk=term.pk).update(is_active=F('is_active'))!=1:
            raise ValidationError('Choose an existing academic term.')
        actor=authorized_administrator(actor)
        term=AcademicTerm.objects.get(pk=term.pk)
        _prepared_inputs(term); data=scope(term)
        try: expected=signing.loads(scope_token,salt=SALT,max_age=3600)
        except (signing.BadSignature,TypeError,ValueError): raise ValidationError('Review expired. Preview the current SHS inputs again.')
        if expected!={'actor':actor.pk,'term':term.pk,'digest':digest(data)}:
            raise ValidationError('The reviewed SHS inputs changed. Preview and confirm again.')
        evidence=_issue(actor,term,'CURRENT_REVIEW',reason.strip(),data)
        for schedule in Schedule.objects.filter(term=term,status__in=['PUBLISHED','ARCHIVED']):
            if schedule_validation_messages(schedule):
                raise ValidationError('Current schedule validation failed. No reapproval was saved; resolve the reported requirements through an authorized revision.')
        return evidence
