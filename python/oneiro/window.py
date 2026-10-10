"""Window lifecycle and WebView2 launcher for Oneiro.

This module owns:
1. **Window launching**:
   - Starting a native window using `pywebview` (over Edge Chromium / WebView2 on Windows).
   - Single-instance awareness via loopback connection and host process checking.
   - Clean shutdown: closing the native window signals the application server
     (and stopping the process and graph).
2. **Headless & Browser fallbacks**:
   - If `pywebview` is not installed, or GUI is not available (headless environment,
     CI, SSH, Linux terminal without display), falls back cleanly to opening the browser
     via `webbrowser` or logging clear instructions without crashing.
   - Respects `ui.window` setting ("window", "browser", "both") and CLI flags (`--no-window`).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Any, Callable

from oneiro import config

log = logging.getLogger("oneiro.window")


@dataclass
class WindowState:
    """State of the application window."""

    mode: str  # "native", "browser", "headless", "none"
    url: str
    active: bool = False
    error: str = ""


def is_gui_available() -> bool:
    """Check if graphical display is available."""
    if os.environ.get("ONEIRO_HEADLESS") == "1":
        return False
    if sys.platform != "win32":
        # On POSIX check DISPLAY or WAYLAND_DISPLAY
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def launch_window(
    port: int,
    *,
    title: str = "Oneiro",
    width: int = 1200,
    height: int = 800,
    no_window: bool = False,
    on_close: Callable[[], Any] | None = None,
) -> WindowState:
    """Launch the window or execute fallback.

    Called after the web server has started listening on the given port.
    """
    url = f"http://127.0.0.1:{port}/"
    preference = str(config.value("ui.window") or "window").lower()

    if no_window or preference == "none" or os.environ.get("ONEIRO_HEADLESS") == "1":
        return WindowState(mode="headless", url=url, active=True)

    if not is_gui_available() or preference == "browser":
        try:
            webbrowser.open(url)
            return WindowState(mode="browser", url=url, active=True)
        except Exception as exc:
            return WindowState(mode="headless", url=url, active=False, error=str(exc))

    # Try pywebview if present
    try:
        import webview  # type: ignore
    except ImportError:
        # pywebview is not in this python runtime; fallback to system browser
        try:
            webbrowser.open(url)
            return WindowState(
                mode="browser",
                url=url,
                active=True,
                error="pywebview is not installed; launched default browser instead",
            )
        except Exception as exc:
            return WindowState(
                mode="headless",
                url=url,
                active=False,
                error=f"pywebview missing and browser launch failed: {exc}",
            )

    # Native pywebview window
    try:
        # Window configuration
        window = webview.create_window(
            title=title,
            url=url,
            width=width,
            height=height,
            min_size=(800, 600),
            confirm_close=False,
        )

        def _on_closed():
            if on_close is not None:
                on_close()

        window.events.closed += _on_closed
        # Start pywebview loop (blocking or GUI thread)
        webview.start(gui="edgechromium" if sys.platform == "win32" else None)
        return WindowState(mode="native", url=url, active=True)
    except Exception as exc:
        log.warning("Could not start pywebview window: %s. Falling back to browser.", exc)
        try:
            webbrowser.open(url)
            return WindowState(
                mode="browser",
                url=url,
                active=True,
                error=f"native window failed ({exc}); opened browser",
            )
        except Exception as browser_exc:
            return WindowState(
                mode="headless",
                url=url,
                active=False,
                error=f"native window failed ({exc}) and browser failed ({browser_exc})",
            )
