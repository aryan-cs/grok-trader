import time
from polymarket.feed import PolymarketFeed

feed = PolymarketFeed(verbose=False)
feed.subscribe_event("fed-decision-in-january")
feed.start_in_background()

while True:
    print("\n==== REPORT ====")
    print(feed.get_report())
    time.sleep(5)