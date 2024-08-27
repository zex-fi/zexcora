# install dependencies
```bash
$ npm install
```

# Initialize wallet

```bash
$ mkdir wallets
$ cd wallets

$ monero-wallet-cli --testnet --generate-from-view-key wallet_1 --password "" << EOF
<primary_address>
<view_key>
<restore_height>
EOF

$ cd ..
```

#### Example
```bash
$ monero-wallet-cli --testnet --generate-from-view-key wallet_1 --password "" << EOF
9u5K8hWkw1QVCJb3d64eyeJ9oxD9VPr4UF7HUwbzMB17Ms1re4ZvbBk9X41QDzaazvMQvQDb1hieViHutNME2DrjJiQ9hLj
bc8ce2ac8649c69d3cbe623c634f5d3a6e660ff08bb03e4c189340fd0b043606
0
EOF
```

# test

```bash
$ node index.js
```
