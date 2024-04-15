import time
import sys
import os
from struct import unpack, pack
from threading import Thread
from tss import pyfrost_blueprint
from flask import Flask, Blueprint, request
from zex import Zex, BUY, SELL, CANCEL, DEPOSIT, WITHDRAW

def api_blueprint():
    api = Blueprint('api', __name__)
    api.route('/orders/<pair>/<name>', methods=['GET'])(pair_orders)
    api.route('/users/<user>/balances', methods=['GET'])(user_balances)
    api.route('/users/<user>/trades', methods=['GET'])(user_trades)
    api.route('/users/<user>/orders', methods=['GET'])(user_orders)
    api.route('/txs', methods=['POST'])(send_txs)
    return api

def pair_orders(pair, name):
    pair = pair.split('_')
    pair = pair[0].encode() + pack('I', int(pair[1])) +\
           pair[2].encode() + pack('I', int(pair[3]))
    q = zex.queues.get(pair)
    if not q:
        return []
    q = q.buy_orders if name == 'buy' else q.sell_orders
    return [{
        'amount': unpack('d', o[16:24])[0],
        'price': unpack('d', o[24:32])[0],
    } for price, index, o in q]

def user_balances(user):
    user = bytes.fromhex(user)
    return [{
        'chain': token[0:3].decode('ascii'),
        'token': unpack('I', token[3:7])[0],
        'balance': zex.balances[token][user]
    } for token in zex.balances if zex.balances[token].get(user, 0) > 0]

def user_trades(user):
    trades = zex.trades.get(bytes.fromhex(user), [])
    return [{
        'name': 'buy' if name == BUY else 'sell',
        't': t,
        'amount': amount,
        'base_chain': pair[0:3].decode('ascii'),
        'base_token': unpack('I', pair[3:7])[0],
        'quote_chain': pair[7:10].decode('ascii'),
        'quote_token': unpack('I', pair[10:14])[0],
    } for t, amount, pair, name in trades]
    print(list(trades)[:1])
    return list(trades)

def user_orders(user):
    orders = zex.orders.get(bytes.fromhex(user), {})
    orders = [{
        'name': 'buy' if o[1] == BUY else 'sell',
        'base_chain': o[2:5].decode('ascii'),
        'base_token': unpack('I', o[5:9])[0],
        'quote_chain': o[9:12].decode('ascii'),
        'quote_token': unpack('I', o[12:16])[0],
        'amount': unpack('d', o[16:24])[0],
        'price': unpack('d', o[24:32])[0],
        't': unpack('I', o[32:36])[0],
        'nonce': unpack('I', o[36:40])[0],
        'index': unpack('Q', o[-8:])[0],
    } for o in orders]
    return orders

txs_q = []

def send_txs():
    txs = [tx.encode('latin-1') for tx in request.json]
    txs_q.extend(txs)
    return { 'success': True }

def process_loop():
    while True:
        if len(txs_q) == 0:
            time.sleep(1)
            continue
        txs = txs_q[:]
        print(f'processing {len(txs)} txs')
        zex.process(txs_q)
        txs_q.clear()

if __name__ == '__main__':
    zex = Zex()
    Thread(target=process_loop).start()
    app = Flask(__name__)
    app.register_blueprint(pyfrost_blueprint(), url_prefix="/pyfrost")
    app.register_blueprint(api_blueprint(), url_prefix="/api")
    host = os.environ.get("ZEX_HOST")
    port = int(os.environ.get("ZEX_PORT"))
    app.run(host=host, port=port, debug=True)
