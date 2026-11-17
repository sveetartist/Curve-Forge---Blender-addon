import importlib
import sys
import types
import unittest
from pathlib import Path

from test_geometry import line_points

package = types.ModuleType('_bevel_curve_math')
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[package.__name__] = package
merge = importlib.import_module(package.__name__ + '.merge')


class MergeTests(unittest.TestCase):
    def test_center_collapses_selection_and_averages_attributes(self):
        points = line_points([(0, 0, 0), (2, 4, 0), (6, 2, 0), (8, 0, 0)], {1, 2})
        points[1]['radius'], points[2]['radius'] = 2, 4
        originals = [p.copy() for p in points]
        result = merge.merge_points(points)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1]['co'], (4, 3, 0))
        self.assertEqual(result[1]['radius'], 3)
        self.assertTrue(result[1]['selected'])
        self.assertEqual(result[0], points[0])
        self.assertEqual(result[2], points[3])
        self.assertEqual(points, originals)

    def test_active_retains_position_handles_and_attributes(self):
        points = line_points([(0, 0, 0), (2, 4, 0), (6, 2, 0), (8, 0, 0)], {1, 2})
        points[2]['radius'], points[2]['tilt'] = 4, 0.7
        result = merge.merge_points(points, 'ACTIVE', 2)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1], points[2])

    def test_hidden_and_unselected_points_survive_noncontiguous_merge(self):
        points = line_points([(i, 0, 0) for i in range(5)], {0, 2, 4})
        points[2]['hide'] = True
        result = merge.merge_points(points)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]['co'], (2, 0, 0))
        self.assertEqual(result[1:], points[1:4])

    def test_all_selected_cyclic_points_can_collapse(self):
        points = line_points([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], {0, 1, 2, 3}, True)
        result = merge.merge_points(points)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['co'], (1, 1, 0))

    def test_invalid_selection_and_active_target_are_rejected(self):
        points = line_points([(0, 0, 0), (2, 0, 0), (4, 0, 0)], {1})
        with self.assertRaises(ValueError):
            merge.merge_points(points)
        points[0]['selected'] = True
        for active in (None, 2, 10):
            with self.assertRaises(ValueError):
                merge.merge_points(points, 'ACTIVE', active)

    def test_join_endpoints_in_all_directions(self):
        for first_index in (0, 2):
            for second_index in (0, 2):
                first = line_points([(0, 0, 0), (1, 1, 0), (2, 0, 0)], {first_index})
                second = line_points([(4, 0, 0), (5, 1, 0), (6, 0, 0)], {second_index})
                result = merge.join_endpoints(first, first_index, second, second_index)
                self.assertEqual(len(result), 5)
                self.assertEqual(result[0]['co'], first[2 - first_index]['co'])
                self.assertEqual(result[-1]['co'], second[2 - second_index]['co'])
                self.assertEqual(result[2]['co'],
                                 ((first[first_index]['co'][0] + second[second_index]['co'][0]) / 2, 0, 0))
                self.assertEqual(sum(p['selected'] for p in result), 1)

    def test_join_at_active_uses_destination_attributes_and_both_tangents(self):
        first = line_points([(0, 0, 0), (2, 0, 0)], {1})
        second = line_points([(4, 0, 0), (6, 2, 0)], {0})
        second[0]['radius'], second[0]['tilt'] = 3, 0.4
        result = merge.join_endpoints(first, 1, second, 0, 'ACTIVE', 1)
        self.assertEqual(result[1]['co'], (4, 0, 0))
        self.assertEqual(result[1]['radius'], 3)
        self.assertEqual(result[1]['tilt'], 0.4)
        self.assertAlmostEqual(result[1]['left'][0], 4 - 2 / 3)
        self.assertEqual(result[1]['right'], second[0]['right'])
        with self.assertRaises(ValueError):
            merge.join_endpoints(first, 1, second, 0, 'ACTIVE')

    def test_join_rejects_middle_points(self):
        points = line_points([(0, 0, 0), (2, 0, 0), (4, 0, 0)], {1})
        with self.assertRaises(ValueError):
            merge.join_endpoints(points, 1, points, 0)


if __name__ == '__main__':
    unittest.main()
