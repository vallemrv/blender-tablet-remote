"""Persistent main-thread handlers keep transient CAD visibility out of .blend."""
import bpy
from bpy.app.handlers import persistent
from .runtime import runtime


@persistent
def save_pre(*_):
    runtime.suspend_save()


@persistent
def save_post(*_):
    runtime.resume_save()


@persistent
def load_pre(*_):
    runtime.leave()


@persistent
def load_post(*_):
    runtime.reset()


@persistent
def undo_pre(*_):
    runtime.cancel()


@persistent
def undo_post(*_):
    runtime.doc()
    runtime.isolate()


_HOOKS = {'save_pre':save_pre, 'save_post':save_post, 'save_post_fail':save_post,
          'load_pre':load_pre, 'load_post':load_post,
          'undo_pre':undo_pre, 'redo_pre':undo_pre,
          'undo_post':undo_post, 'redo_post':undo_post}


def register_handlers():
    for name,callback in _HOOKS.items():
        handlers = getattr(bpy.app.handlers,name,None)
        if handlers is not None and callback not in handlers:
            handlers.append(callback)


def unregister_handlers():
    for name,callback in _HOOKS.items():
        handlers = getattr(bpy.app.handlers,name,None)
        if handlers is not None and callback in handlers:
            handlers.remove(callback)
