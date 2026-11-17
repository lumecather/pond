import re

import markdown
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe

from . import figures
from .models import Guide


def _published():
    return Guide.objects.filter(is_published=True)


def guide_list(request):
    guides = _published()
    return render(request, "guides/list.html", {
        "tab": "guides",
        "novice": [g for g in guides if g.level == Guide.Level.NOVICE],
        "pro": [g for g in guides if g.level == Guide.Level.PRO],
    })


def guide_detail(request, slug):
    guide = get_object_or_404(_published(), slug=slug)
    # guide texts ship with the app (or are edited by the user in the admin), so the HTML from Markdown is trusted
    html = markdown.markdown(guide.body, extensions=["tables"])
    # a [[fig:name]] line in the text is replaced with an illustration from guides/figures.py
    html = re.sub(r"<p>\[\[fig:([\w-]+)\]\]</p>", lambda m: figures.render(m.group(1)), html)
    body = mark_safe(html)
    nxt = _published().filter(order__gt=guide.order).first()
    return render(request, "guides/detail.html", {"tab": "guides", "guide": guide, "body": body, "next": nxt})
