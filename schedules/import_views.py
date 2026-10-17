import csv
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction, IntegrityError, OperationalError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_GET

from .models import AcademicImport, AcademicTerm, Role
from .import_workflow import GROUPS, guide, issues_for, review_context
from .import_presentation import LABELS, message
from .importers.academic import COLUMNS, REQUIRED, read_spreadsheet, suggested_mapping, template_bytes, run_import


class UploadForm(forms.Form):
    spreadsheet = forms.FileField(label='Completed spreadsheet', widget=forms.FileInput(attrs={'accept': '.csv,.xlsx', 'data-import-file': ''}))
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.all(), label='Academic term', help_text='Choose the term for these classes. If it is missing, add it in Academic Terms first.')


def check_admin(user):
    if not (user.is_superuser or getattr(getattr(user, 'profile', None), 'role', None) == Role.ADMIN):
        raise PermissionDenied


def mapping_form(payload, data=None):
    form = forms.Form(data)
    for index, header in enumerate(payload['headers']):
        form.fields[f'column_{index}'] = forms.ChoiceField(label=LABELS.get(header, header), help_text='Column in your file: ' + header, required=False,
            choices=[('', 'Do not use this column')] + [(key, LABELS[key] + (' (required)' if key in REQUIRED else '')) for key in COLUMNS],
            initial=payload.get('mapping', [suggested_mapping(h) for h in payload['headers']])[index])
    form.fields['policy'] = forms.ChoiceField(label='Existing records', choices=[('skip', 'Keep existing records unchanged'), ('update', 'Update existing records with information from this file')])
    form.fields['policy'].initial = payload.get('policy', 'skip')
    form.fields['faculty_confirm'] = forms.BooleanField(label='I confirm that the assigned teacher IDs identify who will teach these classes. Old teacher names belong under Original teacher (for reference).')
    return form


def mapping_summary(form):
    fields = [field for field in form if field.name.startswith('column_')]
    choices = [field.value() for field in fields if field.value() in COLUMNS]
    missing = sorted(REQUIRED - set(choices))
    duplicates = sorted({choice for choice in choices if choices.count(choice) > 1})
    return {'mapping_fields': fields, 'matched_columns': len(choices), 'column_count': len(fields),
            'unmatched_columns': len(fields) - len(choices),
            'missing_columns': [LABELS[key] for key in missing],
            'duplicate_columns': [LABELS[key] for key in duplicates],
            'mapping_needs_review': bool(missing or duplicates or form.errors)}


@login_required
@require_http_methods(['GET', 'POST'])
def academic_import(request):
    check_admin(request.user)
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            payload = read_spreadsheet(form.cleaned_data['spreadsheet'])
            payload['term_id'] = form.cleaned_data['term'].pk
            payload['filename'] = form.cleaned_data['spreadsheet'].name
            payload['file_size'] = form.cleaned_data['spreadsheet'].size
            batch = AcademicImport.objects.create(user=request.user, payload=payload)
            return redirect('academic_import_review', pk=batch.pk)
        except ValueError as exc:
            form.add_error('spreadsheet', message(str(exc)))
    stage = 'upload' if request.method == 'POST' or request.GET.get('step') == 'upload' else 'template'
    return import_page(request, {'form': form, 'stage': stage})


def import_page(request, context):
    steps = [('template', 'Download Template'), ('upload', 'Upload File'), ('review', 'Review Data'), ('confirm', 'Confirm Import')]
    current = {'template': 1, 'upload': 2, 'mapping': 3, 'review': 3, 'confirm': 4, 'complete': 4}[context['stage']]
    from django.urls import reverse
    batch = context.get('batch')
    links = {1: reverse('academic_import'), 2: reverse('academic_import') + '?step=upload'}
    if batch and not batch.completed_at:
        links[3] = reverse('academic_import_review', args=[batch.pk]) + '?step=review'
    context.update(guide=guide(), groups=GROUPS, steps=[{'number': i, 'label': name, 'current': i == current,
                   'done': i < current, 'url': links.get(i) if i < current else None}
                   for i, (_, name) in enumerate(steps, 1)])
    return render(request, 'schedules/academic_import.html', context)



@login_required
@require_GET
def academic_import_template(request, kind):
    check_admin(request.user)
    if kind not in ('csv', 'xlsx'):
        raise PermissionDenied
    response = HttpResponse(template_bytes(kind == 'xlsx'), content_type='text/csv' if kind == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="academic-import-template.{kind}"'
    return response


@login_required
@require_http_methods(['GET', 'POST'])
def academic_import_review(request, pk):
    check_admin(request.user)
    batch = get_object_or_404(AcademicImport, pk=pk, user=request.user)
    if batch.completed_at:
        if request.method == 'POST':
            return redirect('academic_import_review', pk=batch.pk)
        result = batch.payload.get('preview')
        if not result:
            messages.info(request, 'This spreadsheet was already imported.')
            return redirect('generate_schedule')
        return import_page(request, {'stage': 'complete', 'batch': batch, **review_context(batch, result)})
    if batch.created_at < timezone.now() - timedelta(hours=2):
        messages.error(request, 'This upload expired. Upload the file again.')
        return redirect('academic_import')
    term = get_object_or_404(AcademicTerm, pk=batch.payload['term_id'])
    result = batch.payload.get('preview')
    if result and not result['errors'] and not batch.preview_signature:
        result = None  # An earlier valid preview was revoked; require a fresh review.
    error_message = ''
    is_preview = request.method == 'POST' and request.POST.get('action') == 'preview'
    form = mapping_form(batch.payload, request.POST if is_preview else None)
    approval_missing = False
    if request.method == 'POST':
        try:
            with transaction.atomic():
                batch = AcademicImport.objects.select_for_update().get(pk=batch.pk, user=request.user)
                if batch.completed_at:
                    return redirect('academic_import_review', pk=batch.pk)
                if request.POST.get('action') == 'confirm':
                    if not batch.preview_signature or request.POST.get('signature') != batch.preview_signature:
                        raise ValueError('Click Review Information before importing.')
                    if batch.payload['policy'] == 'update' and request.POST.get('approve_updates') != 'yes':
                        approval_missing = True
                        raise ValueError('Tick the approval box to allow changes to existing records.')
                    result = run_import(batch.payload, batch.payload['mapping'], term, batch.payload['policy'],
                                        commit=True, expected_signature=batch.preview_signature)
                    if result['errors']:
                        raise ValueError('Some information needs fixing. Review the file again before importing.')
                    batch.payload['preview'] = result
                    batch.completed_at = timezone.now()
                    batch.save(update_fields=['payload', 'completed_at'])
                    return redirect('academic_import_review', pk=batch.pk)
                if is_preview:
                    batch.preview_signature = ''
                    batch.payload.pop('preview', None)
                    result = None
                    if form.is_valid():
                        mapping = [form.cleaned_data[f'column_{i}'] for i in range(len(batch.payload['headers']))]
                        result = run_import(batch.payload, mapping, term, form.cleaned_data['policy'])
                        batch.payload.update(mapping=mapping, policy=form.cleaned_data['policy'], preview=result)
                        batch.preview_signature = result['signature'] if not result['errors'] else ''
                    batch.save(update_fields=['payload', 'preview_signature'])
        except (ValueError, IntegrityError, OperationalError) as exc:
            error_message = message(str(exc)) if isinstance(exc, ValueError) else 'We could not save the records right now. Nothing was imported. Click Review Information and try again.'
            result = batch.payload.get('preview') if approval_missing else None
            # Invalidate the old confirmation even when the attempted new preview failed.
            if not approval_missing:
                AcademicImport.objects.filter(pk=batch.pk, completed_at__isnull=True).update(preview_signature='')
    stage = 'review' if result else 'mapping'
    if request.GET.get('step') == 'mapping':
        stage = 'mapping'
    if result and not result['errors'] and batch.preview_signature and (request.GET.get('step') == 'confirm' or approval_missing):
        stage = 'confirm'
    try:
        page = int(request.GET.get('page', 1))
    except ValueError:
        page = 1
    context = {'form': form, 'stage': stage, 'batch': batch, 'term': term, 'error_message': error_message,
               'update': batch.payload.get('policy') == 'update', **mapping_summary(form)}
    if result:
        context.update(review_context(batch, result, page, request.GET.get('filter') == 'errors'))
    return import_page(request, context)


@login_required
@require_GET
def academic_import_errors(request, pk):
    check_admin(request.user)
    batch = get_object_or_404(AcademicImport, pk=pk, user=request.user,
                             created_at__gte=timezone.now() - timedelta(hours=2))
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="import-errors.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Spreadsheet row', 'Column', 'Problem', 'How to fix'])
    def safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value
    for issue in issues_for(batch.payload.get('preview', {})):
        writer.writerow([safe(value) for value in [issue['row'] or 'Related records', issue['column_labels'], issue['problem'], issue['fix']]])
    return response
