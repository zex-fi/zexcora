import time
import heapq
from struct import unpack, pack
from collections import deque
from verify import verify, chunkify

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b'dwbsc'
TRADES_TTL = 1000

class Zex:
    def __init__(self):
        self.queues = {}
        self.balances = {}
        self.amounts = {}
        self.trades = {}
        self.orders = {}
        self.deposited_blocks = { b'pol': 0, b'eth': 0, b'bst': 39493054 }
        self.nonces = {}

    def process(self, txs):
        verify(txs)
        for tx in txs:
            if not tx: continue
            v, name = tx[0:2]
            if v != 1: continue
            try:
                if name == DEPOSIT:
                    self.deposit(tx)
                elif name == WITHDRAW:
                    self.withdraw(tx)
                elif name in (BUY, SELL):
                    pair = tx[2:16]
                    t = unpack('>I', tx[32:36])[0]
                    if pair not in self.queues:
                        self.queues[pair] = TradingQueue(pair[:7], pair[7:], self)
                    self.queues[pair].place(tx)
                    while self.queues[pair].match(t): pass
                elif name == CANCEL:
                    pair = tx[2:16]
                    self.queues[pair].cancel(tx)
            except Exception as e:
                print(e, tx.hex())
                raise

    def deposit(self, tx):
        chain = tx[2:5]
        from_block, to_block, count = unpack('>QQH', tx[5:23])
        assert self.deposited_blocks[chain] == from_block - 1, 'invalid from block'
        self.deposited_blocks[chain] = to_block
        deposits = list(chunkify(tx[23:23+49*count], 49))
        for chunk in deposits:
            token = chain + chunk[:4]
            amount, t = unpack('>dI', chunk[4:16])
            public = chunk[16:49]
            if token not in self.balances:
                self.balances[token] = {}
            if public not in self.balances[token]:
                self.balances[token][public] = 0
            self.balances[token][public] += amount
            if public not in self.trades:
                self.trades[public] = deque()
                self.orders[public] = {}
                self.nonces[public] = 0

    def cancel(self, tx):
        name = tx[2]
        base_token, quote_token = tx[3:10], tx[10:17]
        amount, price = unpack('>dd', tx[17:33])
        t, nonce = unpack('>II', tx[33:41])
        public = tx[41:74]
        order_slice = tx[2:41]
        for order in self.orders[public]:
            if order_slice not in order:
                continue
            self.amounts[order] = 0
            if name == BUY:
                self.balances[quote_token][public] += amount * price
            else:
                self.balances[base_token][public] += amount
            break
        else:
            raise Exception('order not found')

    def withdraw(self, tx):
        pass

class TradingQueue:
    def __init__(self, base_token, quote_token, zex):
        self.buy_orders = []  # Max heap for buy orders, prices negated
        self.sell_orders = []  # Min heap for sell orders
        heapq.heapify(self.buy_orders)
        heapq.heapify(self.sell_orders)
        self.base_token = base_token
        self.quote_token = quote_token
        self.pair = base_token + quote_token
        self.zex = zex

    def place(self, tx):
        name = tx[1]
        base_token, quote_token = tx[2:9], tx[9:16]
        amount, price = unpack('>dd', tx[16:32])
        t, nonce = unpack('>II', tx[32:40])
        public = tx[40:73]
        assert self.zex.nonces[public] == nonce, 'invalid nonce'
        index = unpack('>Q', tx[-8:])[0]
        if name == BUY:
            required = amount * price
            balance = self.zex.balances[quote_token].get(public, 0)
            assert balance >= required, 'balance not enough'
            heapq.heappush(self.buy_orders, (-price, index, tx))
            self.zex.balances[quote_token][public] = balance - required
        else:
            required = amount
            balance = self.zex.balances[base_token].get(public, 0)
            assert balance >= required, 'balance not enough'
            heapq.heappush(self.sell_orders, (price, index, tx))
            self.zex.balances[base_token][public] = balance - required
        self.zex.amounts[tx] = amount
        self.zex.orders[public][tx] = True
        self.zex.nonces[public] += 1

    def match(self, t):
        # Match orders while there are matching orders available
        if not self.buy_orders or not self.sell_orders:
            return False

        # Check if the top buy order matches the top sell order
        buy_price, buy_i, buy_order = self.buy_orders[0]
        sell_price, sell_i, sell_order = self.sell_orders[0]
        buy_price = -buy_price
        if buy_price < sell_price:
            return False            

        # Determine the amount to trade
        trade_amount = min(self.zex.amounts[buy_order], self.zex.amounts[sell_order])

        # Update orders
        buy_public = buy_order[40:73]
        sell_public = sell_order[40:73]

        if self.zex.amounts[buy_order] > trade_amount:
            self.zex.amounts[buy_order] -= trade_amount
        else:
            heapq.heappop(self.buy_orders)
            del self.zex.amounts[buy_order]
            del self.zex.orders[buy_public][buy_order] 

        if self.zex.amounts[sell_order] > trade_amount:
            self.zex.amounts[sell_order] -= trade_amount
        else:
            heapq.heappop(self.sell_orders)
            del self.zex.amounts[sell_order]
            del self.zex.orders[sell_public][sell_order] 

        # Amount for canceled order is set to 0
        if trade_amount == 0:
            return False

        # Update users balances
        price = sell_price if sell_i < buy_i else buy_price
        base_balance = self.zex.balances[self.base_token].get(buy_public, 0)
        self.zex.balances[self.base_token][buy_public] = base_balance + trade_amount
        quote_balance = self.zex.balances[self.quote_token].get(sell_public, 0)
        self.zex.balances[self.quote_token][sell_public] = quote_balance + price * trade_amount
        
        # Add trades to users in-memory history
        buy_q = self.zex.trades[buy_public]
        sell_q = self.zex.trades[sell_public]
        buy_q.append((t, trade_amount, self.pair, BUY))
        sell_q.append((t, trade_amount, self.pair, SELL))

        # Remove trades older than TRADES_TTL from users in-memory history
        while len(buy_q) > 0 and t - buy_q[0][0] > TRADES_TTL: buy_q.popleft()
        while len(sell_q) > 0 and t - sell_q[0][0] > TRADES_TTL: sell_q.popleft()

        return True
