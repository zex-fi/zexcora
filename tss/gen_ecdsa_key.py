from fastecdsa import keys, curve
from fastecdsa.encoding.sec1 import SEC1Encoder

secret_key, public_key = keys.gen_keypair(curve.secp256k1)
print('private:', secret_key.to_bytes(32, 'big').hex())
print('public:', SEC1Encoder.encode_public_key(public_key, True).hex())
