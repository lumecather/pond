from django.contrib import admin

from .models import Network, Order, PaperBalance, Rule, Token, TradingWallet

admin.site.site_header = "Pond admin"
admin.site.site_title = "Pond"


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "chain_id", "native_symbol", "rpc_env", "gecko_id", "is_active")
    list_editable = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "network", "category", "decimals", "is_verified", "description")
    list_filter = ("network", "category", "is_verified")
    list_editable = ("category", "is_verified")
    search_fields = ("symbol", "name", "address")


@admin.register(TradingWallet)
class TradingWalletAdmin(admin.ModelAdmin):
    # the encrypted key is never shown here
    list_display = ("address", "created_at")
    readonly_fields = ("user", "address", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("__str__", "mode", "is_active", "repeat", "last_fired")
    list_filter = ("mode", "is_active", "action", "token__network")
    search_fields = ("token__symbol",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("created_at", "side", "token", "amount_native", "amount_token", "price_usd", "mode", "status", "source", "tx_hash")
    list_filter = ("mode", "status", "side", "source", "token__network")
    search_fields = ("token__symbol", "tx_hash")
    date_hierarchy = "created_at"


@admin.register(PaperBalance)
class PaperBalanceAdmin(admin.ModelAdmin):
    list_display = ("network", "token", "amount")
    list_filter = ("network",)
