from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from schedules.benchmarks.runner import DEFAULT_PARAMETERS, DEFAULT_SEEDS, export_results, run_isolated_trial, validate_request
from schedules.benchmarks.scenarios import SCENARIOS


class Command(BaseCommand):
    help = 'Run synthetic GA trials in separate, disposable in-memory databases.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--scenario', choices=[*SCENARIOS, 'all'], default='small')
        parser.add_argument('--seeds', nargs='+', type=int, default=list(DEFAULT_SEEDS))
        parser.add_argument('--output', required=True, help='New .json or .csv file (never overwritten).')
        for name, default in DEFAULT_PARAMETERS.items():
            parser.add_argument('--' + name.replace('_', '-'), type=type(default), default=default)
        parser.add_argument('--repair-budget', type=int, default=64)

    def handle(self, *args, **options):
        output = Path(options['output'])
        if output.exists() or output.suffix.lower() not in ('.json', '.csv') or not output.parent.is_dir():
            raise CommandError('Choose a new .json or .csv file in an existing directory.')
        scenarios = list(SCENARIOS) if options['scenario'] == 'all' else [options['scenario']]
        parameters = {key: options[key] for key in DEFAULT_PARAMETERS}
        rows = []
        try:
            for scenario in scenarios:
                for seed in options['seeds']:
                    validate_request(dict(scenario=scenario, seed=seed, parameters=parameters,
                                          repair_budget=options['repair_budget']))
            for scenario in scenarios:
                for seed in options['seeds']:
                    self.stdout.write(f'Running {scenario}, seed {seed} in an isolated worker...')
                    rows.append(run_isolated_trial(scenario, seed, parameters, options['repair_budget']))
            export_results(rows, output)
        except (ValueError, RuntimeError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Exported {len(rows)} trials to {output}'))
        if any(row['status'] == 'ERROR' for row in rows):
            raise CommandError('Unexpected execution errors occurred; inspect the exported trial records.')
