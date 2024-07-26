from struct import unpack


def version(tx: bytes):
    return tx[0]


def operation(tx: bytes):
    return tx[1]


def base_chain(tx: bytes):
    return tx[2:5].lower().decode()


def base_token_id(tx: bytes):
    return unpack(">I", tx[5:9])[0]


def quote_chain(tx: bytes):
    return tx[9:12].lower().decode()


def quote_token_id(tx: bytes):
    return unpack(">I", tx[12:16])[0]


def amount(tx: bytes):
    return unpack(">d", tx[16:24])[0]


def price(tx: bytes):
    return unpack(">d", tx[24:32])[0]


def time(tx: bytes):
    return unpack(">I", tx[32:36])[0]


def nonce(tx: bytes):
    return unpack(">I", tx[36:40])[0]


def public(tx: bytes):
    return tx[40:73]


def signature(tx: bytes):
    return tx[73:137]


def index(tx: bytes):
    return unpack(">Q", tx[137:145])[0]


def pair(tx: bytes):
    return f"{base_token(tx)}-{quote_token(tx)}"


def base_token(tx: bytes):
    return f"{base_chain(tx)}:{base_token_id(tx)}"


def quote_token(tx: bytes):
    return f"{quote_chain(tx)}:{quote_token_id(tx)}"


def order_slice(tx: bytes):
    return tx[2:41]
