"""Access control for the app: login by launch token and the password screen.

Django inside the app listens on 127.0.0.1 on a random port. So that no other program or web page
can use it, the only way in is the per-launch token that the app window knows.
"""
from django.shortcuts import redirect, render

from bot.services import vault

OPEN_PATHS = ("/static/", "/desktop/start/", "/favicon.ico")


class DesktopMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(OPEN_PATHS):
            return self.get_response(request)
        if not request.user.is_authenticated:
            return render(request, "desktop/closed.html", status=403)
        if not vault.is_set():
            if request.path != "/setup/":
                return redirect("setup")
        elif not vault.is_unlocked() and request.path != "/unlock/":
            return redirect("unlock")
        return self.get_response(request)
