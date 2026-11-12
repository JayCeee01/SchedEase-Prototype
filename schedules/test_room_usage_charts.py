from types import SimpleNamespace
from django.test import SimpleTestCase
from django.template.loader import render_to_string
from .services.room_utilization import utilization_charts, filtered_rows


class RoomUsageChartTests(SimpleTestCase):
    def row(self, name, scheduled, available):
        return SimpleNamespace(room=SimpleNamespace(name=name), scheduled_hours=scheduled,
            available_hours=available, utilization_percentage=round(scheduled / available * 100, 1) if available else 0,
            daily=[{'day': 0, 'scheduled': scheduled, 'available': available}])

    def test_weighted_aggregation_sorting_and_filter_scope(self):
        rows = [self.row('A', 1, 2), self.row('B', 8, 8), self.row('C', 0, 10)]
        charts = utilization_charts(rows)
        self.assertEqual([b['label'] for b in charts['weekly']], ['B', 'A', 'C'])
        self.assertEqual(charts['daily'][0]['percentage'], 45)
        self.assertEqual(charts['busiest']['label'], 'Monday')
        self.assertEqual(utilization_charts(filtered_rows(rows, query='B'))['daily'][0]['percentage'], 100)
        self.assertEqual([b['percentage'] for b in charts['weekly']], [100, 50, 0])

    def test_empty_zero_denominator_and_over_capacity(self):
        self.assertIsNone(utilization_charts([])['busiest'])
        charts = utilization_charts([self.row('Closed', 2, 0), self.row('Over', 3, 2)])
        self.assertFalse(charts['weekly'][1]['valid'])
        self.assertEqual(charts['weekly'][0]['width'], 100)
        self.assertEqual(charts['weekly'][0]['percentage'], 150)

    def test_exact_daily_hours_and_accessible_details(self):
        row = self.row('Room <A>', 1, 3)
        row.daily[0].update(exact_scheduled=1.004, exact_available=3.009)
        charts = utilization_charts([row])
        self.assertEqual(charts['daily'][0]['percentage'], round(1.004 / 3.009 * 100, 1))
        html = render_to_string('schedules/_room_usage_charts.html', {'rows': [row], 'analytics': charts})
        self.assertIn('<details', html)
        self.assertIn('Room &lt;A&gt;', html)
        self.assertIn('1 scheduled hours / 3 available hours', html)
        self.assertIn('33.3%', html)
