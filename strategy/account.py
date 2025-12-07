import os
from typing import Any, Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OpenOrderParams, OrderType
from py_clob_client.order_builder.constants import BUY, SELL


CLOB_HOST = "https://clob.polymarket.com"
DEFAULT_CHAIN_ID = 137


def _derive_address_from_pk(pk_hex: str) -> str:
    try:
        from eth_account import Account
    except ImportError as e:
        raise RuntimeError(
            "POLY_FUNDER_ADDRESS not set. Install 'eth-account' to derive it "
            "from POLY_PRIVATE_KEY automatically (uv add eth-account), or set "
            "POLY_FUNDER_ADDRESS manually."
        ) from e

    acct = Account.from_key(pk_hex)
    return acct.address


def create_client(
    private_key: str,
    funder: str,
    *,
    host: str = CLOB_HOST,
    chain_id: int = DEFAULT_CHAIN_ID,
    signature_type: int = 0,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    api_passphrase: Optional[str] = None,
) -> ClobClient:
    client = ClobClient(
        host,
        key=private_key,
        chain_id=chain_id,
        signature_type=signature_type,
        funder=funder,
    )

    if api_key and api_secret and api_passphrase:
        client.set_api_creds(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "passphrase": api_passphrase,
            }
        )
    else:
        client.set_api_creds(client.create_or_derive_api_creds())

    # Convenience attribute to mirror the trading address
    try:
        client.address = client.get_address()
    except Exception:
        pass

    return client


def create_client_from_env(
    *,
    host: str = CLOB_HOST,
    chain_id: int = DEFAULT_CHAIN_ID,
    signature_type: int | None = None,
    pk_env: str = "POLY_PRIVATE_KEY",
    funder_env: str = "POLY_FUNDER_ADDRESS",
    api_key_env: str = "POLY_API_KEY",
    api_secret_env: str = "POLY_API_SECRET",
    api_passphrase_env: str = "POLY_API_PASSPHRASE",
    signature_type_env: str = "POLY_SIGNATURE_TYPE",
    funder_override: Optional[str] = None,
) -> ClobClient:
    private_key = os.environ[pk_env]
    funder = funder_override or os.environ.get(funder_env) or _derive_address_from_pk(
        private_key
    )

    if signature_type is None:
        sig_env = os.environ.get(signature_type_env)
        signature_type = int(sig_env) if sig_env is not None else 0

    api_key = os.environ.get(api_key_env)
    api_secret = os.environ.get(api_secret_env)
    api_passphrase = os.environ.get(api_passphrase_env)

    return create_client(
        private_key=private_key,
        funder=funder,
        host=host,
        chain_id=chain_id,
        signature_type=signature_type,
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
    )


try:
    IOC_ORDER_TYPE = OrderType.FAK  # Fill-And-Kill == IOC-style
    ORDER_TYPE_MAP = {
        "FAK": OrderType.FAK,
        "FOK": OrderType.FOK,
        "GTC": OrderType.GTC,
        "GTD": OrderType.GTD,
    }
except AttributeError as e:
    raise RuntimeError(
        "This version of py-clob-client does not define OrderType.FAK "
        "(required for IOC orders)."
    ) from e


def place_order(
    client: ClobClient,
    token_id: str,
    side: str,
    price: float,
    size: float,
    order_type: str | OrderType = "FAK",
) -> Any:
    side_upper = side.upper()
    if side_upper == "BUY":
        side_const = BUY
    elif side_upper == "SELL":
        side_const = SELL
    else:
        raise ValueError("side must be 'buy' or 'sell'")

    if isinstance(order_type, str):
        ot = ORDER_TYPE_MAP.get(order_type.upper())
        if not ot:
            raise ValueError(f"order_type must be one of {list(ORDER_TYPE_MAP.keys())}")
        order_type = ot

    order_args = OrderArgs(
        token_id=token_id,
        price=price,
        size=size,
        side=side_const,
    )

    signed_order = client.create_order(order_args)
    return client.post_order(signed_order, order_type)


def get_orders(
    client: ClobClient,
    market: Optional[str] = None,
    asset_id: Optional[str] = None,
) -> Any:
    params = OpenOrderParams(market=market, asset_id=asset_id)
    return client.get_orders(params)
