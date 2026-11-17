"""The rule engine: one pass checks every enabled rule."""
import logging
from datetime import timedelta

from django.utils import timezone

from bot.models import Mode, Order, Rule

from . import prices, vault
from .trading import execute_order

log = logging.getLogger("pond.engine")

# A repeating rule fires at most once per this period.
COOLDOWN = timedelta(hours=1)
# After a failed attempt the rule tries again after this pause...
RETRY = timedelta(minutes=5)
# ...and switches off after this many failures in a row, so a broken rule doesn't spam the history.
MAX_FAILURES = 3


def _last_failed(rule) -> bool:
    last = rule.order_set.order_by("-created_at").first()
    return bool(last and last.status == Order.Status.FAILED)


def _failures_in_a_row(rule) -> int:
    count = 0
    for status in rule.order_set.order_by("-created_at").values_list("status", flat=True)[:MAX_FAILURES]:
        if status != Order.Status.FAILED:
            break
        count += 1
    return count


def check_rules() -> int:
    fired = 0
    seen = {}  # token prices for this pass
    rules = Rule.objects.filter(is_active=True).select_related("token__network", "user")
    for rule in rules:
        try:
            if rule.mode == Mode.LIVE and not vault.is_unlocked():
                continue  # the app is locked: the key is not available, try again once it's unlocked
            if rule.last_fired:
                pause = RETRY if _last_failed(rule) else COOLDOWN
                if timezone.now() - rule.last_fired < pause:
                    continue
            tid = rule.token_id
            if tid not in seen:
                try:
                    seen[tid] = prices.get_price_usd(rule.token)
                except prices.PriceUnavailable:
                    seen[tid] = None
            price = seen[tid]
            if price is None:
                continue
            hit = price < rule.trigger_price_usd if rule.trigger == Rule.Trigger.BELOW else price > rule.trigger_price_usd
            if not hit:
                continue
            order = execute_order(
                rule.user, rule.token, rule.action,
                amount_native=rule.amount_native, sell_percent=rule.sell_percent,
                mode=rule.mode, source=Order.Source.RULE, rule=rule,
            )
            rule.last_fired = timezone.now()
            if order.status == Order.Status.FAILED:
                # a failure (network hiccup, empty balance...) must not silently kill a stop-loss: retry a few times
                if _failures_in_a_row(rule) >= MAX_FAILURES:
                    rule.is_active = False
                    log.warning("rule %s switched off after %s failed attempts: %s", rule.pk, MAX_FAILURES, order.error)
            elif not rule.repeat:
                rule.is_active = False
            rule.save(update_fields=["last_fired", "is_active"])
            fired += 1
        except Exception:
            # one broken rule must not stop the others from being checked
            log.exception("rule %s failed", rule.pk)
    return fired
