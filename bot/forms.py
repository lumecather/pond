from django import forms

from .models import Rule, Side


class RuleForm(forms.ModelForm):
    class Meta:
        model = Rule
        fields = ["token", "trigger", "trigger_price_usd", "action", "amount_native", "sell_percent", "repeat"]

    def __init__(self, *args, tokens, limit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit = limit  # live mode: the single-buy limit
        self.fields["token"].queryset = tokens
        self.fields["token"].empty_label = None

    def clean(self):
        data = super().clean()
        price = data.get("trigger_price_usd")
        if price is not None and price <= 0:
            self.add_error("trigger_price_usd", "The price must be above zero.")
        if data.get("action") == Side.BUY:
            data["sell_percent"] = None
            if not data.get("amount_native") or data["amount_native"] <= 0:
                self.add_error("amount_native", "Enter how much to buy for.")
            elif self.limit is not None and data["amount_native"] > self.limit:
                self.add_error("amount_native", f"That is above your single-buy limit of {self.limit.normalize():f}. Change the limit in Settings.")
        elif data.get("action") == Side.SELL:
            data["amount_native"] = None
            if not data.get("sell_percent") or not 1 <= data["sell_percent"] <= 100:
                self.add_error("sell_percent", "Enter a percentage from 1 to 100.")
        return data
