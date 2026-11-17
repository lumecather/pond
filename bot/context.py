from django.conf import settings

from .models import Network


def current_network(request):
    """The network picked by the user (kept in the session) and the list of enabled networks."""
    nets = list(Network.objects.filter(is_active=True))
    slug = request.session.get("network")
    current = next((n for n in nets if n.slug == slug), nets[0] if nets else None)
    return current, nets


def current_mode(request) -> str:
    """Demo or live. Live is only available once it is allowed in Settings."""
    user = request.user
    if user.is_authenticated and user.live_enabled and request.session.get("mode") == "live":
        return "live"
    return "paper"


def site(request):
    ctx = {"site_name": settings.SITE_NAME}
    if request.user.is_authenticated:
        ctx["network"], ctx["networks"] = current_network(request)
        ctx["mode"] = current_mode(request)
    return ctx
