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
    day = forms.TypedChoiceField(coerce=int, choices=enumerate(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']), required=False)
    start = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type':'time'}), label='Unavailable from')
    end = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type':'time'}), label='Unavailable until')
    sections = forms.ModelMultipleChoiceField(queryset=m.Section.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple, label='New sections with recorded teaching assignments')
    replacement_meetings = forms.ModelMultipleChoiceField(queryset=m.TeachingAssignment.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple, label='Meetings authorized for a replacement instructor')
    replacements = forms.ModelMultipleChoiceField(queryset=m.Faculty.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple, label='Approved alternatives (up to three)')
    comparable = forms.BooleanField(required=False, label='I confirm these instructors have comparable responsibilities and compatible workload policies.')
    rearrange = forms.BooleanField(required=False, label='Allow moving up to two related meetings if direct repair is unsuccessful.')
    recurring = forms.BooleanField(label='This change repeats weekly for the term, rather than a one-day absence.')

    def __init__(self, source, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source=source
        entries=list(source.entries.select_related('assignment','faculty_override'))
        self.fields['faculty'].queryset=m.Faculty.objects.filter(pk__in={e.effective_faculty.pk for e in entries})
        self.fields['room'].queryset=m.Room.objects.filter(pk__in={e.room_id for e in entries})
        self.fields['replacement_meetings'].queryset=m.TeachingAssignment.objects.filter(pk__in={e.assignment_id for e in entries})
        self.fields['sections'].queryset=m.Section.objects.filter(pk__in=m.TeachingAssignment.objects.filter(
            term=source.term).exclude(pk__in={e.assignment_id for e in entries}).values('section_id'))

    def clean(self):
        data=super().clean()
        if self.errors:return data
        kind=data['kind']
        scenario=dict(kind=kind,rearrange=data['rearrange'],comparable=data['comparable'],
            replacements=[f.pk for f in data['replacements']],replacement_meetings=[a.pk for a in data['replacement_meetings']])
        if kind in ('faculty','room'):
            if not data[kind] or data['day']=='' or not data['start'] or not data['end']:
                raise ValidationError('Select the affected resource, weekday, start and end time.')
            scenario.update(resource=data[kind].pk,day=data['day'],start=data['start'].isoformat(),end=data['end'].isoformat())
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
