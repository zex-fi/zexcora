import random
import sys
import os
from threading import Thread
from tss import pyfrost_blueprint
from flask import Flask, Blueprint, request
from zex import *
from test import get_txs

def api_blueprint():
    api = Blueprint('api', __name__)
    api.route('/users/<user>/transactions', methods=['GET'])(user_transactions)
    api.route('/users/<user>/orders', methods=['GET'])(user_orders)
    return api

def user_transactions(user):
    print(zex)
    return ['transaction', user]

def user_orders(user):
    print(zex)
    return ['order', user]

def main_loop():
    txs = get_txs(1000)
    i = 0
    while True:
        if i >= len(txs): break
        rand = random.randint(10, 100)
        zex.process(txs[i:i+rand])
        i += rand
    print('main loop finished')


if __name__ == '__main__':
    zex = Zex()
    Thread(target=main_loop).start()
    app = Flask(__name__)
    app.register_blueprint(pyfrost_blueprint(), url_prefix="/pyfrost")
    app.register_blueprint(api_blueprint(), url_prefix="/api")
    host = os.environ.get("ZEX_HOST")
    port = int(os.environ.get("ZEX_PORT"))
    app.run(host=host, port=port, debug=True)
