import timeit
from struct import unpack

# Example data
tx = b"\x01bBST\x00\x00\x00\x01BST\x00\x00\x00\x02?\xb9\x99\x99\x99\x99\x99\x9a@\x93J=p\xa3\xd7\nf\xa8\x13\x1f\x00\x00\x00\x00\x02\x08v\x02\xe7\x1a\x82wzz\x9c#Kf\x8a\x1d\xc9B\xc9\xa2\x9b\xf3\x1c\x93\x11T\xeb3\x1c!\xb6\xf6\xfd\x11c\x92\x83\x89?J\xc9\x16\xe5\xc23\xe1)\x05\x03:'\x0e>\x95q\x84P\x02`\xf2\x14\x07\x9f$#*\xc4\x1c\t\x84$\x8c\xd1\x08\xa0\x84\x10\xd0Y\n%z\xfe\xfa\xcc\x96[\x7fT\x0cw\xa4Y\xeb!\xc97\x00\x00\x00\x00\x00\x00\x00\x00"


# Method using struct.unpack
def parse_with_unpack(tx):
    operation, amount, price, nonce, public, index = unpack(">xB14xdd4xI33s64xQ", tx)
    return operation, amount, price, nonce, public, index


# Method using int.from_bytes for integer and struct.unpack for others
def parse_with_int_from_bytes(tx):
    operation = tx[1]
    amount, price = unpack(">dd", tx[16:32])
    nonce = int.from_bytes(tx[36:40], byteorder="big")
    public = tx[40:73]
    index = unpack(">Q", tx[137:145])[0]
    return operation, amount, price, nonce, public, index


# Benchmarking
iterations = 1000000
time_unpack = timeit.timeit(lambda: parse_with_unpack(tx), number=iterations)
time_int_from_bytes = timeit.timeit(
    lambda: parse_with_int_from_bytes(tx), number=iterations
)

print(f"Time with unpack: {time_unpack:.6f} seconds")
print(f"Time with int.from_bytes: {time_int_from_bytes:.6f} seconds")
