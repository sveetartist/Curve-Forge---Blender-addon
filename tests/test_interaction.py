"""Numeric input and scheduling checks without a Blender dependency."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('interaction', Path(__file__).resolve().parents[1] / 'interaction.py')
interaction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(interaction)


def event(kind='TEXTINPUT', text='', value='PRESS'):
    return SimpleNamespace(type=kind, unicode=text, value=value)


class NumericTests(unittest.TestCase):
    def test_decimal_editing_and_empty_intermediate_values(self):
        text = ''
        for character in '.25':
            text = interaction.edit_numeric(text, event(text=character))
        self.assertEqual(interaction.numeric_value(text), 0.25)
        self.assertIsNone(interaction.edit_numeric(text, event(text='.')))
        for _ in range(3):
            text = interaction.edit_numeric(text, event('BACK_SPACE'))
        self.assertEqual(text, '')
        for text in ('', '.', '-', '-.'):
            self.assertEqual(interaction.numeric_value(text), 0)

    def test_sign_and_numpad(self):
        text = interaction.edit_numeric('', event('NUMPAD_MINUS'), signed=True)
        text = interaction.edit_numeric(text, event('NUMPAD_PERIOD'))
        text = interaction.edit_numeric(text, event('NUMPAD_5'))
        self.assertEqual(interaction.numeric_value(text), -0.5)
        self.assertEqual(interaction.edit_numeric(text, event('MINUS'), signed=True), '.5')
        self.assertIsNone(interaction.edit_numeric('', event('MINUS')))

    def test_other_keys_releases_and_unbounded_input(self):
        self.assertIsNone(interaction.edit_numeric('1', event('M', 'm')))
        self.assertIsNone(interaction.edit_numeric('1', event(text='2', value='RELEASE')))
        text = '9' * 32
        self.assertEqual(interaction.edit_numeric(text, event(text='9')), text)


class ModalFeedbackTests(unittest.TestCase):
    def test_header_status_session_without_cursor_overlay(self):
        region = SimpleNamespace(type='WINDOW')
        context = SimpleNamespace(
            area=Mock(regions=[region]), workspace=Mock(), window=Mock(),
            window_manager=Mock())
        # No draw-handler API is exposed: feedback must only manage the session.
        with patch.dict('sys.modules', {'bpy': SimpleNamespace()}):
            feedback = interaction.ModalFeedback(context, timer=True)
            self.assertIn(feedback, interaction.ModalFeedback.active)
            context.window_manager.event_timer_add.assert_called_once_with(
                interaction.PreviewSchedule.interval, window=context.window)
            feedback.close()
            feedback.close()
        context.window_manager.event_timer_remove.assert_called_once_with(
            context.window_manager.event_timer_add.return_value)
        context.area.header_text_set.assert_called_once_with(None)
        context.workspace.status_text_set.assert_called_once_with(None)
        context.window.cursor_modal_restore.assert_called_once_with()
        self.assertIsNone(feedback.timer)
        self.assertNotIn(feedback, interaction.ModalFeedback.active)


class ScheduleTests(unittest.TestCase):
    def test_coalescing_skips_duplicates_and_flushes_latest(self):
        now = [0.0]
        schedule = interaction.PreviewSchedule(clock=lambda: now[0])
        calls = []
        self.assertTrue(schedule.apply((0.1, 4), lambda *args: calls.append(args)))
        for index in range(1, 100):
            now[0] = index / 10000
            self.assertFalse(schedule.apply((index, 4), lambda *args: calls.append(args)))
        now[0] = 0.04
        self.assertTrue(schedule.apply((99, 4), lambda *args: calls.append(args)))
        now[0] = 0.041
        self.assertTrue(schedule.apply((0.2, 1), lambda *args: calls.append(args), force=True))
        self.assertFalse(schedule.apply((0.2, 1), lambda *args: calls.append(args), force=True))
        self.assertEqual(calls, [(0.1, 4), (99, 4), (0.2, 1)])

    def test_failed_preview_does_not_mark_settings_as_applied(self):
        schedule = interaction.PreviewSchedule()
        def fail(*args):
            raise ValueError('injected failure')
        with self.assertRaises(ValueError):
            schedule.apply((1,), fail)
        calls = []
        self.assertTrue(schedule.apply((1,), lambda value: calls.append(value)))
        self.assertEqual(calls, [1])


if __name__ == '__main__':
    unittest.main()
