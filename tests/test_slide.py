import importlib
from pathlib import Path
import sys
import types
import unittest

from test_geometry import line_points

package = types.ModuleType('_curve_forge_slide_math')
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[package.__name__] = package
slide = importlib.import_module(package.__name__ + '.slide_geometry')


class SlideTests(unittest.TestCase):
    def assertVectorClose(self, actual, expected):
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=6)

    def test_slide_follows_both_neighbors_and_preserves_handles_and_attributes(self):
        points = line_points([(-2, 0, 0), (0, 0, 0), (0, 2, 0)], {1})
        originals = [point.copy() for point in points]
        for bezier in (False, True):
            paths = slide.prepare_slide(points, False, bezier)
            for factor, expected in ((0.5, (0, 1, 0)), (-0.5, (-1, 0, 0))):
                result = slide.slide_points(points, paths, factor)
                self.assertVectorClose(result[1]['co'], expected)
                self.assertVectorClose(tuple(result[1]['left'][i] - result[1]['co'][i] for i in range(3)),
                                       tuple(points[1]['left'][i] - points[1]['co'][i] for i in range(3)))
                self.assertEqual(result[0], points[0])
                self.assertEqual(result[2], points[2])
                self.assertEqual(result[1]['radius'], points[1]['radius'])
                self.assertEqual(result[1]['tilt'], points[1]['tilt'])
        self.assertEqual(points, originals)

    def test_curved_bezier_path_is_used_instead_of_straight_chord(self):
        points = line_points([(-2, 0, 0), (0, 0, 0), (2, 0, 0)], {1})
        points[1]['right'], points[2]['left'] = (0, 2, 0), (2, 2, 0)
        result = slide.slide_points(points, slide.prepare_slide(points, False, True), 0.5)
        self.assertVectorClose(result[1]['co'], (1, 1.5, 0))

    def test_clamp_and_tangent_extension(self):
        points = line_points([(-2, 0, 0), (0, 0, 0), (0, 2, 0)], {1})
        paths = slide.prepare_slide(points, False, False)
        for factor, clamped, extended in ((2, (0, 2, 0), (0, 4, 0)), (-2, (-2, 0, 0), (-4, 0, 0))):
            self.assertVectorClose(slide.slide_points(points, paths, factor)[1]['co'], clamped)
            self.assertVectorClose(slide.slide_points(points, paths, factor, False)[1]['co'], extended)

    def test_endpoints_slide_inward_and_extend_outward_only_when_unclamped(self):
        points = line_points([(0, 0, 0), (2, 0, 0)], {0, 1})
        paths = slide.prepare_slide(points, False, False)
        self.assertVectorClose(slide.slide_points(points, paths, 0.5)[0]['co'], (1, 0, 0))
        self.assertVectorClose(slide.slide_points(points, paths, 0.5)[1]['co'], (2, 0, 0))
        self.assertVectorClose(slide.slide_points(points, paths, -0.5, False)[0]['co'], (-1, 0, 0))
        self.assertVectorClose(slide.slide_points(points, paths, 0.5, False)[1]['co'], (3, 0, 0))

    def test_cyclic_wrap_and_multiple_selected_points(self):
        points = line_points([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], {0, 1}, True)
        paths = slide.prepare_slide(points, True, False)
        result = slide.slide_points(points, paths, -0.5)
        self.assertVectorClose(result[0]['co'], (0, 1, 0))
        self.assertVectorClose(result[1]['co'], (1, 0, 0))
        self.assertEqual(result, slide.slide_points(points, paths, -0.5))

    def test_hidden_zero_length_and_handle_only_points(self):
        points = line_points([(0, 0, 0), (0, 0, 0), (2, 0, 0)], {1})
        points[2]['hide'] = True
        self.assertFalse(slide.prepare_slide(points, False, False))
        points[1]['selected'] = False
        points[1]['select_left'] = True
        result = slide.move_points(points, (0, 1, 0))
        self.assertEqual(result[1]['co'], points[1]['co'])
        self.assertVectorClose(result[1]['left'], (0, 1, 0))
        self.assertEqual(result[1]['right'], points[1]['right'])
        self.assertEqual(result[2], points[2])
        self.assertFalse(slide.prepare_slide(points, False, True))

    def test_mouse_projection_selects_direction_clamps_and_extends(self):
        paths = [[(0, (0, 0)), (1, (100, 0)), (2, (200, 0))],
                 [(0, (0, 0)), (-1, (-100, 0)), (-2, (-200, 0))]]
        self.assertAlmostEqual(slide.nearest_factor(paths, (25, 5)), 0.25)
        self.assertAlmostEqual(slide.nearest_factor(paths, (-75, 5)), -0.75)
        self.assertEqual(slide.nearest_factor(paths, (150, 0)), 1)
        self.assertAlmostEqual(slide.nearest_factor(paths, (150, 0), False), 1.5)
        self.assertAlmostEqual(slide.nearest_factor([paths[0]], (-50, 0), False), -0.5)
        self.assertEqual(slide.nearest_factor([[(0, (0, 0)), (1, (0, 0))]], (1, 0)), 0)


if __name__ == '__main__':
    unittest.main()
