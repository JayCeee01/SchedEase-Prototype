from django import forms
from django.core import signing
import hashlib
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from . import models as m
from .services import workload_balancing as service


class ScopedCheckboxes(forms.CheckboxSelectMultiple):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        item = getattr(value, 'instance', None)
        if isinstance(item, m.Assignment):
            locked = item.pk in getattr(self, 'locked_ids', set())
            option['attrs']['data-locked'] = 'true' if locked else 'false'
            option['label'] = f'{label} - ' + ('Locked by schedule' if locked else 'Candidate; analysis required')
            option['attrs']['data-term'] = str(item.term_id)
            option['attrs']['data-department'] = str(item.subject.department_id)
        elif isinstance(item, m.Faculty):
            option['attrs']['data-department'] = str(item.department_id)
        return option


class ScopeForm(forms.Form):
    term = forms.ModelChoiceField(label='Academic term', queryset=m.AcademicTerm.objects.all())
    department = forms.ModelChoiceField(queryset=m.Department.objects.all())
    assignments = forms.ModelMultipleChoiceField(required=False, widget=ScopedCheckboxes,
        queryset=m.Assignment.objects.select_related('subject', 'section', 'faculty'), label='Limit to assignments',
        help_text='Leave empty to analyze all assignments in the chosen term and department.')
    faculty = forms.ModelMultipleChoiceField(required=False, widget=ScopedCheckboxes,
        queryset=m.Faculty.objects.all(), label='Limit to instructors',
        help_text='Leave empty to analyze instructors in the department. Include current instructors.')
    exclude_assignments = forms.ModelMultipleChoiceField(required=False, widget=ScopedCheckboxes,
        queryset=m.Assignment.objects.select_related('subject', 'section', 'faculty'), label='Exclude assignments')
    exclude_faculty = forms.ModelMultipleChoiceField(required=False, widget=ScopedCheckboxes,
        queryset=m.Faculty.objects.all(), label='Exclude instructors')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        locked = set(m.ScheduleEntry.objects.values_list('assignment__assignment_id', flat=True))
        for key in ('assignments', 'exclude_assignments'):
            self.fields[key].widget.locked_ids = locked

    def clean(self):
        data = super().clean()
        term, department = data.get('term'), data.get('department')
        if term and department:
            for key in ('assignments', 'exclude_assignments'):
                if any(a.term_id != term.pk or a.subject.department_id != department.pk for a in data.get(key, [])):
                    self.add_error(key, 'Remove assignments outside the selected term and department.')
            for key in ('faculty', 'exclude_faculty'):
                if any(f.department_id != department.pk for f in data.get(key, [])):
                    self.add_error(key, 'Remove instructors outside the selected department.')
            for left, right in (('assignments', 'exclude_assignments'), ('faculty', 'exclude_faculty')):
                if {a.pk for a in data.get(left, [])} & {a.pk for a in data.get(right, [])}:
                    self.add_error(right, 'An item cannot be both included and excluded. Remove one selection.')
        return data


def form_state(post):
    return {key: (post.get(key) if key in ('term', 'department') else post.getlist(key)) for key in ScopeForm.base_fields}


@login_required
@require_http_methods(['GET', 'POST'])
def workload_proposals(request):
    service.require_admin(request.user)
    from .services import workload_discovery as discovery
    context = {'form': ScopeForm(), 'history': m.WorkloadApproval.objects.order_by('-pk')[:10]}
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if request.POST.get('scope_state'):
                state = signing.loads(request.POST['scope_state'], salt='workload-form', max_age=1800)
                context.update(form=ScopeForm(state), scope_state=request.POST['scope_state'])
            if action == 'analyze':
                request.session.pop('workload_proposal', None)
                request.session.pop('workload_analysis', None)
                form = ScopeForm(request.POST)
                context['form'] = form
                if form.is_valid():
                    data = form.cleaned_data
                    analysis, analysis_token = discovery.discover(request.user, data['term'], data['department'],
                        **{key: [item.pk for item in data[key]] for key in ('assignments', 'faculty', 'exclude_assignments', 'exclude_faculty')})
                    context.update(analysis=analysis, analysis_token=analysis_token,
                        scope_state=signing.dumps(form_state(request.POST), salt='workload-form'))
                    request.session['workload_analysis'] = hashlib.sha256(analysis_token.encode()).hexdigest()
            elif action == 'generate':
                analysis_token = request.POST.get('analysis_token', '')
                if request.session.get('workload_analysis') != hashlib.sha256(analysis_token.encode()).hexdigest():
                    raise ValidationError('Analyze the current scope before generating proposals.')
                if request.POST.get('authorize_scope') != 'yes' or request.POST.get('comparable') != 'yes':
                    raise ValidationError('Authorize the listed candidate assignments and confirm instructor comparability first. Analyze again to review the list.')
                token, attention = discovery.authorize(request.user, analysis_token)
                request.session['workload_proposal'] = hashlib.sha256(token.encode()).hexdigest()
                payload = signing.loads(token, salt=service.SALT)
                selected = list(payload['changes'])
                _, result = service.preview(request.user, token, selected)
                context.update(token=token, result=result, attention=attention, selected=selected,
                    choices=[{'id': str(row['id']), 'label': f"{row['subject']} / {row['section']}: {row['current']} -> {row['proposed']}"} for row in result['proposals']])
            elif action in ('preview', 'approve'):
                token = request.POST.get('token', '')
                if request.session.get('workload_proposal') != hashlib.sha256(token.encode()).hexdigest():
                    raise ValidationError('This proposal was replaced by a new analysis. Analyze the current scope again.')
                selected = request.POST.getlist('selected')
                payload, result = service.preview(request.user, token, selected)
                if action == 'approve':
                    try:
                        reviewed = signing.loads(request.POST.get('reviewed', ''), salt='workload-reviewed', max_age=1800)
                    except signing.BadSignature as exc:
                        raise ValidationError('Preview this selection before approving.') from exc
                    if reviewed != {'token': hashlib.sha256(token.encode()).hexdigest(), 'selected': sorted(set(selected))}:
                        raise ValidationError('Your selection changed. Preview it before approving.')
                    if request.POST.get('confirm') != 'yes':
                        raise ValidationError('Confirm the selected batch before approving.')
                    audit = service.approve(request.user, token, selected)
                    messages.success(request, f'Approved {len(result["changes"])} reassignments. Audit #{audit.pk}. No schedule was published.')
                    return redirect('workload_proposals')
                choices = []
                for pk, target in payload['changes'].items():
                    parent = m.Assignment.objects.select_related('subject', 'section', 'faculty').get(pk=pk)
                    teacher = m.Faculty.objects.get(pk=target)
                    choices.append({'id': pk, 'label': f'{parent.subject.code} / {parent.section}: {parent.faculty} → {teacher}'})
                context.update(token=token, selected=selected, result=result, choices=choices)
            else:
                raise ValidationError('Choose a valid batch action.')
        except signing.BadSignature:
            context['errors'] = ['The saved selections expired. Analyze workload again.']
        except ValidationError as exc:
            context['errors'] = exc.messages
        except DatabaseError:
            context['errors'] = ['The batch could not be saved. No changes were applied. Refresh and generate proposals again.']
    if context.get('token'):
        context['reviewed'] = signing.dumps({'token': hashlib.sha256(context['token'].encode()).hexdigest(), 'selected': sorted(set(context['selected']))}, salt='workload-reviewed')
    context['advanced_fields'] = [context['form'][key] for key in ('assignments', 'faculty', 'exclude_assignments', 'exclude_faculty')]
    return render(request, 'schedules/workload_proposals.html', context)
