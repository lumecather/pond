from django.urls import path

from . import views, views_desktop

urlpatterns = [
    path("", views.home, name="home"),
    path("desktop/start/", views_desktop.start, name="desktop_start"),
    path("setup/", views_desktop.setup, name="setup"),
    path("unlock/", views_desktop.unlock, name="unlock"),
    path("lock/", views_desktop.lock, name="lock"),
    path("settings/", views_desktop.app_settings, name="app_settings"),
    path("pond/", views.dashboard, name="dashboard"),
    path("trade/", views.trade, name="trade"),
    path("tokens/", views.tokens, name="tokens"),
    path("api/price/", views.price_data, name="price_data"),
    path("demo/reset/", views.demo_reset, name="demo_reset"),
    path("api/chart/", views.chart_data, name="chart_data"),
    path("tokens/add/", views.token_add, name="token_add"),
    path("tokens/<int:pk>/remove/", views.token_remove, name="token_remove"),
    path("rules/", views.rules, name="rules"),
    path("rules/<int:pk>/toggle/", views.rule_toggle, name="rule_toggle"),
    path("rules/<int:pk>/delete/", views.rule_delete, name="rule_delete"),
    path("wallet/", views.wallet, name="wallet"),
    path("history/", views.history, name="history"),
    path("network/<slug:slug>/", views.set_network, name="set_network"),
    path("mode/<slug:mode>/", views.set_mode, name="set_mode"),
    path("settings/pro/", views.toggle_pro, name="toggle_pro"),
]
