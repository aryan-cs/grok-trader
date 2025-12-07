import time
from polymarket.feed import PolymarketFeed

# Demo: subscribe to a single market within an event to verify subscribe_market.
event_slug = "fed-decision-in-january"
market_slug = "fed-decreases-interest-rates-by-50-bps-after-january-2026-meeting"

feed = PolymarketFeed(verbose=False)

# subscribe_market will fetch the event data when given event_slug.
feed.subscribe_market(market_slug, event_slug=event_slug)
feed.start_in_background()

while True:
    print("\n==== REPORT (single market) ====")
    print(feed.get_report())
    time.sleep(5)
