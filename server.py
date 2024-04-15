import time
import sys
import os
from threading import Thread
from tss import pyfrost_blueprint
from flask import Flask, Blueprint, request
from zex import *

def api_blueprint():
    api = Blueprint('api', __name__)
    api.route('/users/<user>/txs', methods=['GET'])(user_txs)
    api.route('/users/<user>/orders', methods=['GET'])(user_orders)
    api.route('/txs', methods=['POST'])(send_txs)
    return api

def user_txs(user):
    print(zex)
    return ['transaction', user]

def user_orders(user):
    print(zex)
    return ['order', user]

txs_q = []

def send_txs():
    txs = [tx.encode('latin-1') for tx in request.json]
    txs_q.extend(txs)
    return { 'success': True }

def main_loop():
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
    Thread(target=main_loop).start()
    app = Flask(__name__)
    app.register_blueprint(pyfrost_blueprint(), url_prefix="/pyfrost")
    app.register_blueprint(api_blueprint(), url_prefix="/api")
    host = os.environ.get("ZEX_HOST")
    port = int(os.environ.get("ZEX_PORT"))
    app.run(host=host, port=port, debug=True)
