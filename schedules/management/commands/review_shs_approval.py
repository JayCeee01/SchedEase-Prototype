"""Authenticated, two-step current review; no legacy history reconstruction."""
import getpass
import json
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from schedules.models import AcademicTerm
from schedules.services.shs_approval import preview, reapprove


class Command(BaseCommand):
    help = 'Preview and explicitly reapprove current SHS inputs. Does not prove or rewrite original legacy approval.'

    def add_arguments(self, parser):
        parser.add_argument('--term', type=int, required=True)
        parser.add_argument('--administrator', required=True)
        parser.add_argument('--confirm-token')
        parser.add_argument('--reason')

    def handle(self, *args, **options):
        password=getpass.getpass('Administrator password (hidden): ')
        actor=authenticate(username=options['administrator'],password=password)
        del password
        if actor is None: raise CommandError('Administrator authentication failed.')
        try:
            term=AcademicTerm.objects.get(pk=options['term'],education_level='SHS')
            if options['confirm_token']:
                evidence=reapprove(actor=actor,term=term,scope_token=options['confirm_token'],reason=options['reason'])
                self.stdout.write(f'Current review recorded as evidence {evidence.pk}. Original historical approval remains unproven for legacy records.')
            else:
                data, token=preview(actor=actor,term=term)
                self.stdout.write('Review every definition below. Confirmation establishes current validity only; historical restrictions remain.')
                self.stdout.write(json.dumps(data,indent=2))
                self.stdout.write('Confirmation token (expires in one hour): '+token)
        except (ValidationError, AcademicTerm.DoesNotExist) as exc:
            raise CommandError('; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Choose an existing SHS term.')
