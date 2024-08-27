const utils = require("./monero-utils.js");

async function main() {
	/**
	 * rpc: daemon rpc address
	 * network: 0:mainnet, 1:testnet, 2:stagenet
	 * walletPath: path to wallet file
	 * walletPass: wallet password
	 * from: min block number
	 * to: max block number
	 */
	const args = utils.parseCmdArgv()

	const wallet = await utils.openWallet(
		args.rpc, //'http://127.0.0.1:28081',
		parseInt(args.network), ///utils.NET_TYPE_TESTNET,
		args.walletPath, //'./wallets/wallet_1',
		args.walletPass, //''
	)
	await utils.syncWallet(wallet);

	let rangeTransactions = await utils.getBlockRangeTransactions(wallet, parseInt(args.from), parseInt(args.to))
	console.log(utils.stringifyTransfers(rangeTransactions))

	await wallet.close()
}

main()
	.catch(e => console.log(e))
	.finally(() => process.exit(0))