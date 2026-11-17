import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geometry import bevel_points, evaluate, lerp, trim, trim_edge, prepare_edges


def point(co, selected=False):
    return dict(co=co, left=co, right=co, left_type='FREE', right_type='FREE',
                selected=selected, select_left=False, select_right=False,
                hide=False, radius=1.0, tilt=0.0, weight_softbody=0.5, co_weight=1.0)


def line_points(coords, selected, cyclic=False):
    points = [point(tuple(co), i in selected) for i, co in enumerate(coords)]
    for i, p in enumerate(points):
        if i > 0 or cyclic:
            p['left'] = lerp(p['co'], points[(i - 1) % len(points)]['co'], 1 / 3)
        if i < len(points) - 1 or cyclic:
            p['right'] = lerp(p['co'], points[(i + 1) % len(points)]['co'], 1 / 3)
    return points


class GeometryTests(unittest.TestCase):
    def assertVectorClose(self, a, b, places=6):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=places)

    def test_quarter_circle_and_tangents(self):
        values, corners, clamped = bevel_points(
            line_points([(-1, 0, 0), (0, 0, 0), (0, 1, 0)], {1}), False, 0.2, 1)
        self.assertEqual((corners, clamped, len(values)), (1, 0, 4))
        a, b = values[1:3]
        self.assertVectorClose(a['co'], (-0.2, 0, 0))
        self.assertVectorClose(b['co'], (0, 0.2, 0))
        k = 4 / 3 * math.tan(math.pi / 8)
        self.assertVectorClose(a['right'], (-0.2 + 0.2 * k, 0, 0))
        self.assertVectorClose(b['left'], (0, 0.2 - 0.2 * k, 0))

    def test_adjacent_cyclic_corners_can_overlap(self):
        values, corners, clamped = bevel_points(
            line_points([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], {0, 1, 2, 3}, True),
            True, 0.75, 1)
        self.assertEqual((corners, clamped, len(values)), (4, 0, 8))
        self.assertAlmostEqual(values[2]['co'][0] - values[1]['co'][0], -0.5, places=6)

    def test_large_amounts_extend_beyond_segment_ends(self):
        points = line_points([(-1, 0, 0), (0, 0, 0), (0, 1, 0)], {1})
        for bezier in (True, False):
            for rounded in (True, False):
                for amount_type in ('RADIUS', 'OFFSET'):
                    for width in (0.75, 1.0, 2.0, 25.0):
                        with self.subTest(bezier=bezier, rounded=rounded,
                                          amount_type=amount_type, width=width):
                            values, corners, clamped = bevel_points(
                                points, False, width, 1, rounded, bezier, amount_type)
                            self.assertEqual((corners, clamped, len(values)), (1, 0, 4))
                            self.assertVectorClose(values[1]['co'], (-width, 0, 0))
                            self.assertVectorClose(values[2]['co'], (0, width, 0))

    def test_large_bevel_with_zero_length_handles_keeps_radius_and_attributes(self):
        points = [point((-1, 0, 0)), point((0, 0, 0), True), point((0, 1, 0))]
        for i, p in enumerate(points):
            p['radius'] = i + 1
            p['tilt'] = i * 0.1
        values, corners, clamped = bevel_points(points, False, 5, 1, amount_type='RADIUS')
        self.assertEqual((corners, clamped), (1, 0))
        self.assertVectorClose(values[1]['co'], (-5, 0, 0))
        self.assertVectorClose(values[2]['co'], (0, 5, 0))
        self.assertEqual(values[1]['radius'], 1)
        self.assertEqual(values[2]['radius'], 3)
        k = 4 / 3 * math.tan(math.pi / 8)
        self.assertVectorClose(values[1]['right'], (-5 + 5 * k, 0, 0))

    def test_oversized_cyclic_bevel_preserves_connection_boundaries(self):
        points = line_points([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
                             {0, 1, 2, 3}, True)
        values, corners, clamped = bevel_points(points, True, 10, 1)
        self.assertEqual((corners, clamped, len(values)), (4, 0, 16))
        self.assertVectorClose(values[1]['co'], (10, 0, 0))
        self.assertVectorClose(values[2]['co'], (1, 0, 0))
        self.assertVectorClose(values[3]['co'], (0, 0, 0))
        self.assertVectorClose(values[4]['co'], (-9, 0, 0))

    def test_endpoint_smooth_hidden_and_cusp_skipped(self):
        coords = [(-1, 0, 0), (0, 0, 0), (1, 0, 0)]
        self.assertIsNone(bevel_points(line_points(coords, {0, 1, 2}), False, 0.1)[0])
        coords[2] = (-1, 0, 0)
        self.assertIsNone(bevel_points(line_points(coords, {1}), False, 0.1)[0])
        points = line_points([(-1, 0, 0), (0, 0, 0), (0, 1, 0)], {1})
        points[1]['hide'] = True
        self.assertIsNone(bevel_points(points, False, 0.1)[0])

    def test_curved_segment_preserved_exactly_after_trim(self):
        points = line_points([(-2, -1, 0), (0, 0, 0), (0, 2, 1)], {1})
        points[0]['right'] = (-1.8, -0.2, 0)
        points[1]['left'] = (-0.5, 0, 0)
        source = (points[0]['co'], points[0]['right'], points[1]['left'], points[1]['co'])
        values, corners, _ = bevel_points(points, False, 0.2, 3)
        self.assertEqual(corners, 1)
        kept = (values[0]['co'], values[0]['right'], values[1]['left'], values[1]['co'])
        # Locate the cut parameter, then compare every evaluated point to the
        # original cubic. This verifies preservation, not just point counts.
        low, high = 0.0, 1.0
        for _ in range(60):
            middle = (low + high) / 2
            if evaluate(source, middle)[0] < kept[3][0]:
                low = middle
            else:
                high = middle
        end = (low + high) / 2
        for step in range(21):
            t = step / 20
            self.assertVectorClose(evaluate(kept, t), evaluate(source, t * end))

    def test_poly_round_and_chamfer(self):
        points = line_points([(-1, 0, 0), (0, 0, 0), (0, 1, 0)], {1})
        rounded = bevel_points(points, False, 0.2, 4, True, False)[0]
        chamfer = bevel_points(points, False, 0.2, 4, False, False)[0]
        self.assertEqual(len(rounded), 7)
        self.assertVectorClose(chamfer[3]['co'], (-0.1, 0.1, 0))
        self.assertGreater(rounded[3]['co'][0], chamfer[3]['co'][0])
        self.assertLess(rounded[3]['co'][1], chamfer[3]['co'][1])

    def test_radius_and_tilt_interpolated(self):
        points = line_points([(-1, 0, 0), (0, 0, 0), (0, 1, 0)], {1})
        points[0]['radius'], points[1]['radius'], points[2]['radius'] = 1, 2, 3
        points[0]['tilt'], points[1]['tilt'], points[2]['tilt'] = 0, 1, 2
        values = bevel_points(points, False, 0.2, 1)[0]
        self.assertAlmostEqual(values[1]['radius'], 1.8, places=6)
        self.assertAlmostEqual(values[2]['radius'], 2.2, places=6)
        self.assertAlmostEqual(values[1]['tilt'], 0.8, places=6)
        self.assertEqual(values[0]['radius'], 1)

    def test_subdivision_matches_source(self):
        source = ((0, 0, 0), (1, 2, 0), (2, -1, 1), (3, 0, 2))
        part = trim(source, 0.2, 0.7)
        for i in range(11):
            t = i / 10
            self.assertVectorClose(evaluate(part, t), evaluate(source, 0.2 + t * 0.5))

    def test_reversed_and_collapsed_subdivision(self):
        source = ((0, 0, 0), (1, 2, 0), (2, -1, 1), (3, 0, 2))
        for start, end in ((0.7, 0.2), (1.0, 0.0), (0.0, 0.0), (1.0, 1.0)):
            part = trim(source, start, end)
            for i in range(11):
                t = i / 10
                self.assertVectorClose(evaluate(part, t),
                                       evaluate(source, start + t * (end - start)))

    def test_extended_curved_edge_keeps_original_cubic_exact(self):
        source = ((0, 0, 0), (1, 2, 0), (2, -1, 1), (3, 0, 2))
        for start, end in ((-1.0, 2.0), (2.0, -1.0)):
            pieces = trim_edge(source, start, end, 5.0)
            self.assertEqual(len(pieces), 3)
            middle = pieces[1][0]
            for i in range(11):
                t = i / 10
                self.assertVectorClose(evaluate(middle, t),
                                       evaluate(source, t if start < end else 1.0 - t))
            for left, right in zip(pieces, pieces[1:]):
                self.assertVectorClose(left[0][3], right[0][0])

    def test_radius_at_non_right_angle(self):
        # Turn by 60 degrees: an r=0.2 fillet cuts r*tan(30) along each side.
        points = line_points([(-2, 0, 0), (0, 0, 0), (1, math.sqrt(3), 0)], {1})
        values = bevel_points(points, False, 0.2, 1, amount_type='RADIUS')[0]
        amount = 0.2 * math.tan(math.pi / 6)
        self.assertVectorClose(values[1]['co'], (-amount, 0, 0))
        self.assertVectorClose(values[2]['co'], (amount / 2, amount * math.sqrt(3) / 2, 0))

    def test_cached_preview_matches_uncached(self):
        points = line_points([(-1, 0, 0), (0, 0, 0), (0, 1, 0)], {1})
        prepared = prepare_edges(points, False, True)
        for width in (0.1, 0.4, 10):
            self.assertEqual(bevel_points(points, False, width),
                             bevel_points(points, False, width, prepared=prepared))


if __name__ == '__main__':
    unittest.main()
