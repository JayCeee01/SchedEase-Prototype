"""Academic relationship checks; shared subjects/resources have no inferred owner."""
from django.core.exceptions import ValidationError
from django.http import Http404

SCOPES = {
    'program': 'education_level', 'academicterm': 'education_level',
    'section': 'program__education_level', 'student': 'section__program__education_level',
    'assignment': 'term__education_level', 'teachingassignment': 'term__education_level',
    'curriculumversion': 'education_level', 'academicpathway': 'curriculum_version__education_level',
    'cohort': 'curriculum_version__education_level',
    'curriculumsubjectrequirement': 'curriculum_version__education_level',
    'subjectoffering': 'academic_term__education_level', 'schedule': 'term__education_level',
}


def request_level(request):
    from schedules.models import AcademicTerm
    levels = []
    for data in (request.GET, request.POST):
        if len(data.getlist('education_level')) > 1:
            raise Http404('Choose one education level.')
        level = data.get('education_level')
        if level:
            if level not in ('TERTIARY', 'SHS'):
                raise Http404('Choose one education level for academic changes.')
            levels.append(level)
        if len(data.getlist('term')) > 1:
            raise Http404('Choose one academic term.')
        term = data.get('term')
        if term:
            if not term.isascii() or not term.isdecimal() or len(term) > 18:
                raise Http404('Invalid academic term.')
            term_level = AcademicTerm.objects.filter(pk=int(term)).values_list('education_level',flat=True).first()
            if term_level is None:
                raise Http404('Academic term is unavailable.')
            levels.append(term_level)
    if request.GET.get('term') and request.POST.get('term') and request.GET['term'] != request.POST['term']:
        raise Http404('The submitted term differs from the selected context.')
    if len(set(levels)) > 1:
        raise Http404('The submitted education level changed.')
    return levels[0] if levels else None


def scope_form(request, form):
    level = request_level(request)
    instance = getattr(form, 'instance', None)
    instance_path = SCOPES.get(instance._meta.model_name) if instance is not None else None
    if not level and instance_path and instance.pk:
        value = instance
        for part in instance_path.split('__'):
            value = getattr(value, part)
        level = value
    request.academic_write_level = level
    if not level:
        return
    for field in form.fields.values():
        qs = getattr(field, 'queryset', None)
        path = SCOPES.get(qs.model._meta.model_name) if qs is not None else None
        if path:
            field.queryset = qs.filter(**{path: level})
    if 'education_level' in form.fields:
        form.fields['education_level'].choices = [(level, level)]
        form.initial['education_level'] = level
    elif instance is not None and instance_path == 'education_level' and not instance.pk:
        # Legacy application forms omit the level field. The explicit, validated
        # creation context supplies it rather than silently using TERTIARY.
        instance.education_level = level


def check_object_context(request, obj):
    level = request_level(request)
    request.academic_write_level = level
    path = SCOPES.get(obj._meta.model_name)
    if level and path:
        value = obj
        for part in path.split('__'):
            value = getattr(value, part)
        if value != level:
            raise Http404('This record belongs to another education level.')


def validate_relationships(obj, using=None):
    from schedules import models as m
    name = obj._meta.model_name
    alias = using or obj._state.db or 'default'
    assignments = m.Assignment.objects.using(alias)
    meetings = m.TeachingAssignment.objects.using(alias)
    terms = m.AcademicTerm.objects.using(alias)
    programs = m.Program.objects.using(alias)
    sections = m.Section.objects.using(alias)
    message = 'The academic term and section program must belong to the same education level.'
    if name in ('program', 'academicterm') and obj.education_level not in ('SHS', 'TERTIARY'):
        raise ValidationError('Choose a valid education level.')
    if name in ('assignment', 'teachingassignment') and obj.term_id and obj.section_id:
        level = terms.filter(pk=obj.term_id).values_list('education_level', flat=True).first()
        section_level = sections.filter(pk=obj.section_id).values_list('program__education_level', flat=True).first()
        if level and section_level and level != section_level:
            raise ValidationError(message)
    elif name == 'program' and obj.pk:
        if (assignments.filter(section__program_id=obj.pk).exclude(term__education_level=obj.education_level).exists()
                or meetings.filter(section__program_id=obj.pk).exclude(term__education_level=obj.education_level).exists()
                or (obj.education_level != 'SHS' and sections.filter(program_id=obj.pk,cohort__isnull=False).exists())):
            raise ValidationError('This program level conflicts with existing sections or teaching assignments.')
    elif name == 'academicterm' and obj.pk:
        if (assignments.filter(term_id=obj.pk).exclude(section__program__education_level=obj.education_level).exists()
                or meetings.filter(term_id=obj.pk).exclude(section__program__education_level=obj.education_level).exists()
                or (obj.education_level != 'SHS' and m.SubjectOffering.objects.using(alias).filter(academic_term_id=obj.pk).exists())):
            raise ValidationError('This term level conflicts with existing assignments or SHS offerings.')
    elif name == 'section' and obj.program_id:
        level = programs.filter(pk=obj.program_id).values_list('education_level',flat=True).first()
        if obj.pk and (assignments.filter(section_id=obj.pk).exclude(term__education_level=level).exists()
                       or meetings.filter(section_id=obj.pk).exclude(term__education_level=level).exists()):
            raise ValidationError(message)
        if obj.cohort_id:
            grade = m.Cohort.objects.using(alias).filter(pk=obj.cohort_id).values_list('grade_level',flat=True).first()
            year = m.YearLevel.objects.using(alias).filter(pk=obj.year_level_id).values_list('level',flat=True).first()
            if level != 'SHS' or grade != year:
                raise ValidationError('The section program and grade must match its SHS cohort.')
