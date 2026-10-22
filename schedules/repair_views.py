"""Administrator-only, explicitly confirmed schedule repair."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from . import models as m
from .services import smart_repair as service


class RepairForm(forms.Form):
    kind = forms.ChoiceField(label='What changed?', choices=[('room','Room unavailable'),
        ('faculty','Instructor unavailable'),('sections','Additional sections')])
    faculty = forms.ModelChoiceField(queryset=m.Faculty.objects.none(), required=False, label='Affected instructor')
    room = forms.ModelChoiceField(queryset=m.Room.objects.none(), required=False, label='Affected room')
    days = forms.TypedMultipleChoiceField(coerce=int, choices=m.Weekday.choices, required=False,
        widget=forms.CheckboxSelectMultiple, label='Unavailable days',
        help_text='Select all days that apply. The same start and end time applies to every selected day.')
    start = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type':'time'}), label='Unavailable from')
    end = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type':'time'}), label='Unavailable until')
    sections = forms.ModelMultipleChoiceField(queryset=m.Section.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple, label='New sections with recorded teaching assignments')
    replacement_meetings = forms.ModelMultipleChoiceField(queryset=m.TeachingAssignment.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple, label='Meetings authorized for a replacement instructor')
    replacements = forms.ModelMultipleChoiceField(queryset=m.Faculty.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple, label='Approved alternatives (up to three)')
    comparable = forms.BooleanField(required=False, label='I confirm these instructors have comparable responsibilities and compatible workload policies.')
    rearrange = forms.BooleanField(required=False,
        label='Allow changes to up to two other classes if needed (optional)',
        help_text='SchedEase will first try to adjust only the affected classes. Check this to let it suggest moving up to two other classes if needed. You will review all changes before saving them.')
    recurring = forms.BooleanField(
        label='I confirm this change applies every week for this term (required)',
        help_text='For example, the room is unavailable every Tuesday at the selected time. Do not use this for a change that happens on just one date.',
        error_messages={'required':'Confirm that this change applies every week for the term. One-day changes are not supported here.'})

    def __init__(self, source, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source=source
        entries=list(source.entries.select_related('assignment','faculty_override'))
        self.fields['faculty'].queryset=m.Faculty.objects.filter(pk__in={e.effective_faculty.pk for e in entries})
        self.fields['room'].queryset=m.Room.objects.filter(pk__in={e.room_id for e in entries})
        self.fields['replacement_meetings'].queryset=m.TeachingAssignment.objects.filter(pk__in={e.assignment_id for e in entries})
        self.fields['sections'].queryset=m.Section.objects.filter(pk__in=m.TeachingAssignment.objects.filter(
            term=source.term).exclude(pk__in={e.assignment_id for e in entries}).values('section_id'))
        for name, field in self.fields.items():
            descriptions = [f'id_{name}_errors']
            if field.help_text:
                descriptions.append(f'id_{name}_helptext')
            field.widget.attrs['aria-describedby'] = ' '.join(descriptions)

    def clean(self):
        data=super().clean()
        if self.errors:return data
        kind=data['kind']
        scenario=dict(kind=kind,rearrange=data['rearrange'],comparable=data['comparable'],
            replacements=[f.pk for f in data['replacements']],replacement_meetings=[a.pk for a in data['replacement_meetings']])
        if kind in ('faculty','room'):
            if not data[kind] or not data['days'] or not data['start'] or not data['end']:
                raise ValidationError('Select the affected resource, at least one day, start and end time.')
            scenario.update(resource=data[kind].pk,days=data['days'],start=data['start'].isoformat(),end=data['end'].isoformat())
        else:
            scenario['sections']=[s.pk for s in data['sections']]
        self.scenario=service.validate_scenario(self.source,scenario)
        return data


def require_admin(user):
    try:service.authorized_administrator(user)
    except ValidationError as exc:raise PermissionDenied from exc


@login_required
@require_http_methods(['GET','POST'])
def repair_start(request, pk):
    require_admin(request.user)
    source=get_object_or_404(m.Schedule,pk=pk,status='PUBLISHED')
    form=RepairForm(source,request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            draft=service.create_draft(source.pk,request.user,form.scenario)
            messages.success(request,'Repair draft created. Review a proposal before applying changes.')
            return redirect('repair_review',pk=draft.pk)
        except ValidationError as exc:form.add_error(None,exc)
        except DatabaseError:form.add_error(None,'The draft could not be created. Reload and try again.')
    return render(request,'schedules/repair_start.html',{'source':source,'form':form})


@login_required
@require_http_methods(['GET','POST'])
def repair_review(request,pk):
    require_admin(request.user)
    draft=get_object_or_404(m.Schedule,pk=pk,status='DRAFT')
    context={'schedule':draft}
    try:
        context['setup']=service.setup(draft)
        from .services.repair_rules import scenario_days
        context['unavailable_days']=', '.join(str(m.Weekday(day).label) for day in scenario_days(context['setup']['scenario']) if day is not None)
        if request.method=='POST':
            if request.POST.get('action')=='preview':
                context['result']=service.propose(draft.pk,request.user)
            elif request.POST.get('action')=='apply':
                service.apply(draft.pk,request.user,request.POST.get('token',''),request.POST.get('confirm')=='yes')
                messages.success(request,'Repair applied to the draft. Review it, then use Publish when ready.')
                return redirect('schedule_detail',pk=draft.pk)
            else:raise ValidationError('Choose Preview or Apply.')
    except ValidationError as exc:context['errors']=exc.messages
    except DatabaseError:context['errors']=['The operation could not be completed. Reload and generate a new preview.']
    return render(request,'schedules/repair_review.html',context)
