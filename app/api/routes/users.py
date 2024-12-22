from decimal import Decimal
from struct import calcsize, unpack
import hashlib

from bitcoinutils.keys import P2trAddress, PublicKey
from bitcoinutils.utils import tweak_taproot_pubkey
from eth_utils import keccak, to_checksum_address
from fastapi import APIRouter, HTTPException
from loguru import logger
from web3 import Web3

from app import zex
from app.config import settings
from app.models.response import (
    Addresses,
    NonceResponse,
    OrderResponse,
    TradeResponse,
    TransferResponse,
    UserAddressesResponse,
    UserAssetResponse,
    UserIDResponse,
    UserPublicResponse,
    Withdraw,
    WithdrawNonce,
)
from app.models.transaction import Deposit, WithdrawTransaction
from app.zex import BUY

router = APIRouter()
light_router = APIRouter()


# @timed_lru_cache(seconds=10)
def _user_assets(user: bytes) -> list[UserAssetResponse]:
    result = []
    for asset in zex.assets:
        if zex.assets[asset].get(user, 0) == 0:
            continue

        balance = zex.assets[asset][user]
        result.append(
            UserAssetResponse(
                asset=asset,
                free=str(balance),
                locked="0",
                freeze="0",
                withdrawing="0",
            )
        )
    return result


@router.get("/asset/getUserAsset")
def user_balances(id: int) -> list[UserAssetResponse]:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    user = zex.id_to_public_lookup[id]
    return _user_assets(user)


def _parse_transaction(tx: bytes) -> tuple[int, Decimal, Decimal, int, bytes]:
    operation, base_token_len, quote_token_len = unpack(">x B B B", tx[:4])

    order_format = f">{base_token_len}s {quote_token_len}s d d I I 33s"
    order_format_size = calcsize(order_format)
    base_token, quote_token, amount, price, t, nonce, public = unpack(
        order_format, tx[4 : 4 + order_format_size]
    )
    base_token = base_token.decode("ascii")
    quote_token = quote_token.decode("ascii")

    return operation, Decimal(str(amount)), Decimal(str(price)), nonce, public


@router.get("/user/trades")
def user_trades(id: int) -> list[TradeResponse]:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    user = zex.id_to_public_lookup[id]
    trades = zex.trades.get(user, [])
    resp = {}
    for time, amount, pair, name, tx in trades:
        base_asset, quote_asset = pair.split("-")

        _, _, price, nonce, _ = _parse_transaction(tx)

        trade = {
            "name": "buy" if name == BUY else "sell",
            "t": time,
            "base_token": base_asset,
            "quote_token": quote_asset,
            "amount": amount,
            "price": price,
            "nonce": nonce,
        }
        if nonce in resp:
            resp[nonce]["amount"] += amount
        else:
            resp[nonce] = trade
    return [value for _, value in sorted(resp.items(), key=lambda x: x[0])]


@router.get("/user/orders")
def user_orders(id: int) -> list[OrderResponse]:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    user = zex.id_to_public_lookup[id]
    orders = zex.orders.get(user, {})
    resp = []
    order: bytes
    for order in orders:
        side, base_token_len, quote_token_len = unpack(">x B B B", order[:4])
        order_format = f">{base_token_len}s {quote_token_len}s d d I I"
        order_format_size = calcsize(order_format)
        base_token, quote_token, amount, price, t, nonce = unpack(
            order_format, order[4 : 4 + order_format_size]
        )
        base_token = base_token.decode("ascii")
        quote_token = quote_token.decode("ascii")

        o = {
            "name": "buy" if side == BUY else "sell",
            "base_token": base_token,
            "quote_token": quote_token,
            "amount": amount,
            "price": price,
            "t": t,
            "nonce": nonce,
            "slice": order[1:].hex(),
        }
        resp.append(o)
    return resp


@router.get("/user/nonce")
def user_nonce(id: int) -> NonceResponse:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    user = zex.id_to_public_lookup[id]
    return NonceResponse(nonce=zex.nonces.get(user, 0))


@router.get("/user/id")
def user_id(public: str):
    try:
        user = bytes.fromhex(public)
    except ValueError:
        return HTTPException(400, {"error": "invalid public"})
    if user not in zex.public_to_id_lookup:
        return HTTPException(404, {"error": "user not found"})

    user_id = zex.public_to_id_lookup[user]
    return UserIDResponse(id=user_id)


@router.get("/user/transfers")
def user_transfers(id: int) -> list[TransferResponse]:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    user = zex.id_to_public_lookup[id]
    if user not in zex.user_deposits:
        return []
    all_deposits = zex.user_deposits.get(user, []).copy()
    all_withdraws = [
        x
        for chain in zex.user_withdraws_on_chain.keys()
        for x in zex.user_withdraws_on_chain[chain].get(user, [])
    ]

    sorted_transfers: list[WithdrawTransaction | Deposit] = sorted(
        all_deposits + all_withdraws, key=lambda transfer: transfer.time
    )
    return [
        TransferResponse(
            chain=t.token_chain,
            token=t.token_name,
            amount=t.amount if isinstance(t, Deposit) else -t.amount,
            time=t.time,
        )
        for t in sorted_transfers
    ]


@router.get("/user/public")
def get_user_public(id: int) -> UserPublicResponse:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    public = zex.id_to_public_lookup[id].hex()
    return UserPublicResponse(public=public)


def tagged_hash(data: bytes, tag: str) -> bytes:
    """
    Tagged hashes ensure that hashes used in one context can not be used in another.
    It is used extensively in Taproot

    A tagged hash is: SHA256( SHA256("TapTweak") ||
                              SHA256("TapTweak") ||
                              data
                            )
    """

    tag_digest = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_digest + tag_digest + data).digest()


# to convert hashes to ints we need byteorder BIG...
def b_to_i(b: bytes) -> int:
    """Converts a bytes to a number"""
    return int.from_bytes(b, byteorder="big")


def i_to_b8(i: int) -> bytes:
    """Converts an integer to bytes"""
    return i.to_bytes(8, byteorder="big")


def calculate_tweak(pubkey: PublicKey, user_id: int) -> int:
    """
    Calculates the tweak to apply to the public and private key when required.
    """

    # only the x coordinate is tagged_hash'ed
    key_x = pubkey.to_bytes()[:32]

    tweak = tagged_hash(key_x + i_to_b8(user_id), "TapTweak")

    # we convert to int for later elliptic curve  arithmetics
    tweak_int = b_to_i(tweak)

    return tweak_int


def get_taproot_address(master_public: PublicKey, user_id: int) -> P2trAddress:
    tweak_int = calculate_tweak(master_public, user_id)
    # keep x-only coordinate
    tweak_and_odd = tweak_taproot_pubkey(master_public.key.to_string(), tweak_int)
    pubkey = tweak_and_odd[0][:32]
    is_odd = tweak_and_odd[1]

    return P2trAddress(witness_program=pubkey.hex(), is_odd=is_odd)


def get_create2_address(deployer_address: str, salt: int, bytecode_hash: str) -> str:
    """
    Computes the CREATE2 address for a contract deployment.

    :param deployer_address: The address of the deploying contract (factory).
    :param salt: A bytes32 value used as the salt in the CREATE2 computation.
    :param bytecode_hash: The bytecode hash of the contract to deploy.
    :return: The computed deployment address as a checksum address.
    """
    # Ensure deployer_address is in bytes format
    if isinstance(deployer_address, str):
        deployer_address = Web3.to_bytes(hexstr=deployer_address)
    elif isinstance(deployer_address, bytes):
        deployer_address = deployer_address
    else:
        raise TypeError("deployer_address must be a string or bytes.")

    if len(deployer_address) != 20:
        raise ValueError("Invalid deployer address length; must be 20 bytes.")

    # Ensure salt is a 32-byte value
    if isinstance(salt, int):
        salt = salt.to_bytes(32, "big")
    elif isinstance(salt, str):
        salt = Web3.to_bytes(hexstr=salt)
    elif isinstance(salt, bytes):
        salt = salt
    else:
        raise TypeError("salt must be an int, string, or bytes.")

    if len(salt) != 32:
        raise ValueError("Invalid salt length; must be 32 bytes.")

    # Ensure bytecode is in bytes format
    if isinstance(bytecode_hash, str):
        bytecode_hash = Web3.to_bytes(hexstr=bytecode_hash)
    else:
        raise TypeError("bytecode must be a string or bytes.")

    # Prepare the data as per the CREATE2 formula
    data = b"\xff" + deployer_address + salt + bytecode_hash

    # Compute the keccak256 hash of the data
    address_bytes = keccak(data)[12:]  # Take the last 20 bytes

    # Return the address in checksum format
    return to_checksum_address(address_bytes)


btc_master_pubkey = PublicKey(settings.zex.keys.btc_public_key)


@router.get("/capital/deposit/address/list")
def get_user_addresses(id: int) -> UserAddressesResponse:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    user = zex.id_to_public_lookup[id]
    if user not in zex.public_to_id_lookup:
        raise HTTPException(404, {"error": "user not found"})
    id = zex.public_to_id_lookup[user]
    taproot_address = get_taproot_address(btc_master_pubkey, id)
    evm_address = get_create2_address(
        settings.zex.deployer_address, id, settings.zex.byte_code_hash
    )
    return UserAddressesResponse(
        user=user.hex(),
        addresses=Addresses(
            BTC=taproot_address.to_string(),
            EVM=evm_address,
        ),
    )


@router.get("/users/latest-id")
def get_latest_user_id():
    return UserIDResponse(id=zex.last_user_id)


@router.get("/user/withdraws/nonce")
def get_withdraw_nonce(id: int, chain: str) -> WithdrawNonce:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    user = zex.id_to_public_lookup[id]
    chain = chain.upper()
    if chain not in zex.user_withdraw_nonce_on_chain:
        raise HTTPException(404, {"error": f"{chain} not found"})
    return WithdrawNonce(
        chain=chain,
        nonce=zex.user_withdraw_nonce_on_chain[chain].get(user, 0),
    )


def get_withdraw_nonce_on_chain(chain: str):
    chain = chain.upper()
    if chain not in zex.withdraw_nonce_on_chain:
        raise HTTPException(404, {"error": "no withdraw on chain"})
    if zex.withdraw_nonce_on_chain[chain] == 0:
        raise HTTPException(404, {"error": "no withdraw on chain"})
    return {"chain": chain, "nonce": zex.withdraw_nonce_on_chain[chain] - 1}


def get_chain_withdraws(
    chain: str, offset: int, limit: int | None = None
) -> list[Withdraw]:
    if chain not in zex.withdraws_on_chain:
        raise HTTPException(404, {"error": "chain not found"})
    transactions = []
    for i, withdraw in enumerate(zex.withdraws_on_chain[chain][offset:limit]):
        token_info = settings.zex.verified_tokens.tokens.get(withdraw.token_name)

        if token_info:
            token_contract = token_info[withdraw.token_chain]
            token = withdraw.token_name
        else:
            token_contract = withdraw.token_name
            token = f"{withdraw.token_chain}:{withdraw.token_name}"

        w = Withdraw(
            chain=withdraw.token_chain,
            tokenContract=token_contract,
            amount=str(int(withdraw.amount * (10 ** zex.token_decimals[token]))),
            destination=withdraw.destination,
            t=withdraw.time,
            nonce=i + offset,
        )
    transactions.append(w)
    return transactions


def get_user_withdraws(
    id: int, chain: str, nonce: int | None = None
) -> Withdraw | list[Withdraw]:
    if nonce and nonce < 0:
        raise HTTPException(400, {"error": "invalid nonce"})
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})

    user = zex.id_to_public_lookup[id]
    chain = chain.upper()
    if chain not in zex.user_withdraws_on_chain:
        raise HTTPException(404, {"error": f"{chain} not found"})
    if user not in zex.user_withdraws_on_chain[chain]:
        return []

    withdraws = zex.user_withdraws_on_chain[chain].get(user, [])
    if nonce and nonce >= len(withdraws):
        logger.debug(f"invalid nonce: maximum nonce is {len(withdraws) - 1}")
        raise HTTPException(400, {"error": "invalid nonce"})

    if nonce is not None:
        withdraw_tx = withdraws[nonce]

        token_info = settings.zex.verified_tokens.tokens.get(withdraw_tx.token_name)
        if token_info:
            token_contract = token_info[withdraw_tx.token_chain]
            token = withdraw_tx.token_name
        else:
            token_contract = withdraw_tx.token_name
            token = f"{withdraw_tx.token_chain}:{withdraw_tx.token_name}"

        return Withdraw(
            chain=withdraw_tx.token_chain,
            tokenContract=token_contract,
            amount=str(int(withdraw_tx.amount * (10 ** zex.token_decimals[token]))),
            user=str(int.from_bytes(user[1:], byteorder="big")),
            destination=Web3.to_checksum_address(withdraw_tx.destination),
            t=withdraw_tx.time,
            nonce=withdraw_tx.nonce,
        )
    else:
        result = []
        for withdraw in zex.user_withdraws_on_chain[chain][user]:
            token_info = settings.zex.verified_tokens.tokens.get(withdraw.token_name)
            if token_info:
                token_contract = token_info[withdraw.token_chain]
                token = withdraw.token_name
            else:
                token_contract = withdraw.token_name
                token = f"{withdraw.token_chain}:{withdraw.token_name}"

            w = Withdraw(
                chain=withdraw.token_chain,
                tokenContract=token_contract,
                amount=str(int(withdraw.amount * (10 ** zex.token_decimals[token]))),
                user=str(int.from_bytes(user[1:], byteorder="big")),
                destination=withdraw.destination,
                t=withdraw.time,
                nonce=withdraw.nonce,
            )
            result.append(w)
        return result


if zex.light_node:
    light_router.get("/user/withdraws")(get_user_withdraws)
    light_router.get("/withdraw/nonce/last")(get_withdraw_nonce_on_chain)
    light_router.get("/withdraws")(get_chain_withdraws)
else:
    router.get("/user/withdraws")(get_user_withdraws)
    router.get("/withdraw/nonce/last")(get_withdraw_nonce_on_chain)
    router.get("/withdraws")(get_chain_withdraws)
