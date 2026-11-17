# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared numeric entry, preview scheduling, and modal viewport feedback."""

from math import isfinite
from time import monotonic


def numeric_value(text):
    return float(text) if text not in {'', '-', '.', '-.'} else 0.0


def edit_numeric(text, event, signed=False):
    """Return edited text, or None when the event is not numeric input."""
    if event.value != 'PRESS':
        return None
    if event.type == 'BACK_SPACE':
        return text[:-1]
    character = getattr(event, 'unicode', '')
    if not character:
        character = {'NUMPAD_PERIOD': '.', 'PERIOD': '.'}.get(event.type, '')
        if event.type.startswith('NUMPAD_') and event.type[-1:] in '0123456789':
            character = event.type[-1]
    if signed and (character == '-' or event.type in {'MINUS', 'NUMPAD_MINUS'}):
        return text[1:] if text.startswith('-') else '-' + text
    if character and (character in '0123456789' or character == '.' and '.' not in text):
        candidate = text + character
        if len(candidate) <= 32 and isfinite(numeric_value(candidate)):
            return candidate
        return text
    return None


class PreviewSchedule:
    """Coalesce settings while enforcing a maximum of 30 previews per second."""

    interval = 1.0 / 30.0

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.last_time = float('-inf')
        self.applied = None

    def apply(self, settings, callback, force=False):
        if settings == self.applied:
            return False
        now = self.clock()
        if not force and now - self.last_time < self.interval:
            return False
        callback(*settings)
        self.applied = settings
        self.last_time = self.clock()
        return True


class ModalFeedback:
    """Own the timer, cursor and header/status cleanup for one modal session."""

    active = set()

    def __init__(self, context, timer=False):
        import bpy

        self.area, self.workspace, self.window = context.area, context.workspace, context.window
        self.manager = context.window_manager
        self.region = next(r for r in self.area.regions if r.type == 'WINDOW')
        self.timer = None
        self.closed = False
        self.on_cancel = None
        try:
            self.window.cursor_modal_set('CROSSHAIR')
            if timer:
                self.timer = self.manager.event_timer_add(PreviewSchedule.interval, window=self.window)
            self.active.add(self)
        except Exception:
            self.close()
            raise

    def close(self):
        import bpy

        if self.closed:
            return
        self.closed = True
        self.on_cancel = None
        self.active.discard(self)
        callbacks = []
        if self.timer is not None:
            timer = self.timer
            callbacks.append(lambda: self.manager.event_timer_remove(timer))
            self.timer = None
        # A screen or workspace may have been closed while a modal tool ran.
        callbacks.extend((lambda: self.area.header_text_set(None),
                          lambda: self.workspace.status_text_set(None),
                          lambda: self.window.cursor_modal_restore(), lambda: self.area.tag_redraw()))
        for callback in callbacks:
            try:
                callback()
            except (ReferenceError, RuntimeError, ValueError):
                pass


def close_feedback(operator):
    feedback = getattr(operator, '_feedback', None)
    if feedback is not None:
        feedback.close()


def cancel_all(context):
    import bpy
    import traceback

    for feedback in tuple(ModalFeedback.active):
        try:
            if feedback.on_cancel is not None:
                with context.temp_override(window=feedback.window, area=feedback.area, region=feedback.region):
                    feedback.on_cancel(bpy.context)
        except Exception:
            traceback.print_exc()
        finally:
            feedback.close()
