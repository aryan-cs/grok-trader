#!/usr/bin/env python3
"""
Dry-run (or send) a single IOC limit order on Polymarket.

Defaults to dry-run: builds and prints the signed order without posting.
Set --send to actually post the order.
Env vars needed:
  POLY_PRIVATE_KEY=0x...
  POLY_FUNDER_ADDRESS=0x...   # optional; derived from private key if omitted
  (optionally POLY_API_KEY / POLY_API_SECRET / POLY_API_PASSPHRASE)
"""

import argparse
import os
import sys
import math
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from strategy.account import create_client_from_env, place_order
from polymarket.asset_id import fetch_event_market_clobs
from polymarket.feed import PolymarketFeed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", default="spacex-ipo-closing-market-cap")
    parser.add_argument("--market", default="will-spacex-not-ipo-by-december-31-2027")
    parser.add_argument("--side", default="buy", choices=["buy", "sell"])
    parser.add_argument("--price", type=float, default=None, help="override price; otherwise best ask for buy / best bid for sell")
    parser.add_argument("--size", type=float, default=5.0)
    parser.add_argument("--send", action="store_true", help="post the IOC order")
    parser.add_argument("--signature-type", type=int, default=None, help="0=EOA, 1=proxy/magic")
    parser.add_argument("--funder", type=str, default=None, help="override funder address")
    args = parser.parse_args()

    # Resolve token_id for YES side of the target market
    clobs = fetch_event_market_clobs(args.event)
    market_tokens = clobs.get(args.market)
    if not market_tokens:
        raise SystemExit(f"Market slug not found: {args.market}")
    token_id = market_tokens["yes"]

    # spin up a quick feed to fetch best bid/ask
    feed = PolymarketFeed(verbose=False)
    feed.subscribe([token_id])
    feed.start_in_background()
    book_price = args.price

    for _ in range(50):  # wait up to ~5s
        ob = feed.orderbooks.get(token_id)
        if ob and ob.best_ask() and ob.best_bid():
            best_bid = ob.best_bid()[0][0]
            best_ask = ob.best_ask()[0][0]
            if args.side == "buy":
                book_price = book_price if book_price is not None else best_ask
            else:
                book_price = book_price if book_price is not None else best_bid
            break
        time.sleep(0.1)

    if book_price is None:
        raise SystemExit("Could not fetch orderbook to determine price; try passing --price.")

    client = create_client_from_env(
        signature_type=args.signature_type,
        funder_override=args.funder,
    )

    print("\n--- IOC order preview ---")
    print(f"address: {client.get_address()}")
    print(f"market:  {args.market}")
    print(f"token:   {token_id}")
    print(f"side:    {args.side}")
    print(f"price:   {book_price}")
    print(f"size:    {args.size}")
    print(f"send:    {args.send}")

    notional = book_price * args.size
    if notional < 1.0:
        min_size = math.ceil((1.0 / args.price) * 10_000) / 10_000
        print(
            f"\nPolymarket min notional is ~$1.00. "
            f"Current notional ${notional:.4f} is too low. "
            f"Increase size to at least {min_size} at this price."
        )
        return

    if not args.send:
        print("\nDRY RUN complete (order not sent). Use --send to post.")
        return

    resp = place_order(
        client=client,
        token_id=token_id,
        side=args.side,
        price=book_price,
        size=args.size,
    )
    print("\nPosted IOC order. Response:")
    print(resp)


if __name__ == "__main__":
    main()
