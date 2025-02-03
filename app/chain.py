from dataclasses import dataclass
from decimal import Decimal

from .models.transaction import WithdrawTransaction
from .proto import zex_pb2


@dataclass
class ChainState:
    """Manages state for a specific blockchain."""

    deposits: set[tuple[str, int]]
    balances: dict[str, Decimal]  # contract_address -> balance
    withdraw_nonce: int
    user_withdraw_nonces: dict[bytes, int]  # public_key -> nonce
    user_withdraws: dict[bytes, list[WithdrawTransaction]]  # public_key -> withdraws
    withdraws: list[WithdrawTransaction]
    contract_decimals: dict[str, int]  # contract_address -> decimal

    @classmethod
    def create_empty(cls):
        return cls(
            deposits=set(),
            balances={},
            withdraw_nonce=0,
            user_withdraw_nonces={},
            user_withdraws={},
            withdraws=[],
            contract_decimals={},
        )

    def to_protobuf(self, chain: str, pb_state: zex_pb2.ZexState):
        """Serialize chain state to protobuf."""
        # Serialize deposits
        pb_deposits = pb_state.deposits[chain]
        for tx_hash, vout in self.deposits:
            entry = pb_deposits.deposits.add()
            entry.tx_hash = tx_hash
            entry.vout = vout

        # Serialize withdraws
        pb_withdraws = pb_state.withdraws_on_chain[chain]
        pb_withdraws.raw_txs.extend([w.raw_tx for w in self.withdraws])

        # Serialize user withdraws
        pb_user_withdraws = pb_state.user_withdraws_on_chain[chain]
        for public, withdraw_list in self.user_withdraws.items():
            entry = pb_user_withdraws.withdraws.add()
            entry.public_key = public
            entry.raw_txs.extend([w.raw_tx for w in withdraw_list])

        # Serialize user withdraw nonces
        pb_withdraw_nonces = pb_state.user_withdraw_nonce_on_chain[chain]
        for public, nonce in self.user_withdraw_nonces.items():
            entry = pb_withdraw_nonces.nonces.add()
            entry.public_key = public
            entry.nonce = nonce

        # Serialize withdraw nonce
        pb_state.withdraw_nonce_on_chain[chain] = self.withdraw_nonce

        # Serialize contract decimals
        pb_state.contract_decimal_on_chain[chain].contract_decimal.update(
            self.contract_decimals
        )

    @classmethod
    def from_protobuf(cls, chain: str, pb_state: zex_pb2.ZexState) -> "ChainState":
        """Deserialize chain state from protobuf."""
        # Deserialize deposits
        deposits = {
            (item.tx_hash, item.vout) for item in pb_state.deposits[chain].deposits
        }

        # Deserialize withdraws
        withdraws = [
            WithdrawTransaction.from_tx(raw_tx)
            for raw_tx in pb_state.withdraws_on_chain[chain].raw_txs
        ]

        # Deserialize user withdraws
        user_withdraws = {
            entry.public_key: [
                WithdrawTransaction.from_tx(raw_tx) for raw_tx in entry.raw_txs
            ]
            for entry in pb_state.user_withdraws_on_chain[chain].withdraws
        }

        # Deserialize user withdraw nonces
        user_withdraw_nonces = {
            entry.public_key: entry.nonce
            for entry in pb_state.user_withdraw_nonce_on_chain[chain].nonces
        }

        # Deserialize contract decimals
        contract_decimals = dict(
            pb_state.contract_decimal_on_chain[chain].contract_decimal
        )

        return cls(
            deposits=deposits,
            balances={},  # This will be populated from assets
            withdraw_nonce=pb_state.withdraw_nonce_on_chain[chain],
            user_withdraw_nonces=user_withdraw_nonces,
            user_withdraws=user_withdraws,
            withdraws=withdraws,
            contract_decimals=contract_decimals,
        )
