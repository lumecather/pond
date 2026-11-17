from django.contrib import admin
from django.contrib.staticfiles.views import serve
from django.urls import include, path, re_path
from django.views.generic import RedirectView

urlpatterns = [
    # the app has no login screen to come back to, so the admin's "Log out" just returns to the app
    path("admin/logout/", RedirectView.as_view(url="/pond/")),
    path("admin/", admin.site.urls),
    path("guides/", include("guides.urls")),
    path("", include("bot.urls")),
    # there is no nginx inside a desktop app, so Django serves the CSS and JS itself
    re_path(r"^static/(?P<path>.*)$", serve, {"insecure": True}),
]
