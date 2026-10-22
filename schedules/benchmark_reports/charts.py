"""Standalone vector figures using the existing ReportLab dependency."""
from collections import defaultdict

from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors


def bar_figure(title, labels, values, y_label, x_label, *, percent=False):
    width = max(620, 95 * len(labels))
    drawing = Drawing(width, 360)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 80, 90, width - 120, 210
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 9
    chart.valueAxis.valueMin = min(0, min(values))
    chart.valueAxis.valueMax = 100 if percent else max(1, max(values) * 1.1)
    chart.bars[0].fillColor = colors.HexColor('#245A81')
    drawing.add(chart)
    drawing.add(String(width / 2, 337, title, textAnchor='middle', fontSize=13))
    drawing.add(String(12, 318, y_label, fontSize=10))
    drawing.add(String(width / 2, 52, x_label, textAnchor='middle', fontSize=10))
    drawing.add(String(width / 2, 25, 'Descriptive observations only; no significance or scalability inference.', textAnchor='middle', fontSize=8))
    return drawing


def write_charts(report, directory):
    charts, notes = [], []
    families = defaultdict(list)
    for group in report['groups']:
        families[group['family_id']].append(group)
        points = [s for s in group['per_seed'] if s['soft_score_feasible']['n']]
        if len(points) >= 2 and 'unverified_identity' not in group:
            charts.append((group['group_id'] + '-soft-score',
                f"{group['scenario']} / {group['group_id']}: feasible soft scores",
                bar_figure(f"{group['scenario']}: feasible soft score by seed",
                    [str(p['seed']) for p in points], [p['soft_score_feasible']['mean'] for p in points],
                    f"Mean soft score ({group['scoring_version']}; higher is better)", 'Random seed (repetitions averaged)')))
    for family, groups in sorted(families.items()):
        eligible = sorted([g for g in groups if g['completed_trials'] >= 2
                           and len({r['seed'] for r in g['trials'] if r['outcome'] != 'incomplete'}) >= 2
                           and 'unverified_identity' not in g], key=lambda g: (g['scenario'], g['group_id']))
        # Each bar names an input group; different fingerprints are not pooled.
        labels = [f"{g['scenario']} {i+1} (n={g['completed_trials']})" for i, g in enumerate(eligible)]
        mapping = '; '.join(f"{i+1}={g['group_id']}" for i, g in enumerate(eligible))
        if eligible:
            charts.append((family + '-feasibility', f'Feasibility; {mapping}', bar_figure(
                'Observed feasibility by input group', labels, [g['feasibility_percent'] for g in eligible],
                'Feasible / completed trials (%)', 'Scenario / group (completed trials)', percent=True)))
        timed = [(g, label) for g, label in zip(eligible, labels) if len({r['seed'] for r in g['trials']
                 if r['outcome'] != 'incomplete' and r['elapsed_seconds'] is not None}) >= 2]
        if timed:
            charts.append((family + '-runtime', f'Completed-trial runtime; {mapping}', bar_figure(
                'Mean trial runtime by input group', [label for g, label in timed],
                [g['runtime_seconds']['mean'] for g, label in timed], 'Mean runtime (seconds)',
                'Scenario / group (includes completed failures)')))
        sized = [g for g in eligible if g['scenario'] in ('small', 'medium', 'large')
                 and g['input_counts'] and len({r['seed'] for r in g['trials']
                 if r['outcome'] == 'feasible' and r['elapsed_seconds'] is not None}) >= 2]
        if len({g['input_counts']['meetings'] for g in sized}) >= 2:
            sized.sort(key=lambda g: (g['input_counts']['meetings'], g['group_id']))
            charts.append((family + '-workload', 'Observed runtime versus workload; ' + '; '.join(
                f"{g['scenario']}={g['group_id']}" for g in sized), bar_figure(
                'Observed feasible runtime at measured workload sizes',
                [f"{g['scenario']} ({g['input_counts']['meetings']})" for g in sized],
                [g['runtime_feasible_seconds']['mean'] for g in sized], 'Mean feasible-trial runtime (seconds)',
                'Scenario (number of meetings); no fitted or extrapolated curve')))
        else:
            notes.append(f'{family}: runtime-versus-workload chart omitted; fewer than two measured workload sizes with sufficient feasible trials.')
    if not charts:
        notes.append('Charts omitted: require at least two completed trials from two distinct seeds in a verified comparable group.')
    manifest = []
    for name, caption, drawing in charts:
        renderSVG.drawToFile(drawing, str(directory / (name + '.svg')))
        renderPDF.drawToFile(drawing, str(directory / (name + '.pdf')), canvasKwds={'invariant': 1})
        manifest.append(dict(svg=name + '.svg', pdf=name + '.pdf', caption=caption))
    return manifest, notes
