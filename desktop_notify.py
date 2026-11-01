"""Notificaciones locales, sin enviar mensajes a servicios externos."""
from __future__ import annotations

import sys

_toaster = None


def notify(title: str, body: str) -> tuple:
    global _toaster
    try:
        if sys.platform != 'win32':
            return False, 'Notificaciones nativas implementadas para Windows 10/11.'
        from windows_toasts import WindowsToaster, Toast
        if _toaster is None:
            _toaster = WindowsToaster('Docking Matrix')
        toast = Toast()
        toast.text_fields = [title, body]
        _toaster.show_toast(toast)
        return True, ''
    except Exception as exc:
        return False, str(exc)
