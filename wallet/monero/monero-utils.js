const { MoneroWalletFull, MoneroUtils } = require('monero-ts');

async function openWallet(daemonRpc, networkType, walletPath, password) {
	return await MoneroWalletFull.openWallet({
		server: {
			uri: daemonRpc
		},
		networkType,
		path: walletPath,
		password,
	});
}

async function syncWallet(wallet) {
	await wallet.sync()
	await wallet.save()
}

function generateRandomPaymentId() {
	const chars = 'abcdef0123456789';
	let paymentId = '';
	for (let i = 0; i < 16; i++) {
	  paymentId += chars[Math.floor(Math.random() * chars.length)];
	}
	return paymentId;
}

async function getIntegratedAddress(networkType, primaryAddress, paymentId) {  
	// Generate an integrated address using the primary address and payment ID
	const integratedAddress = await MoneroUtils.getIntegratedAddress(
	  networkType,
	  primaryAddress,
	  paymentId
	)

	return integratedAddress.getIntegratedAddress()
}

async function getLastBlock(wallet) {
	return await wallet.getHeight();
}

async function getBlockTransactions(wallet, blockNumber) {
	return await getBlockRangeTransactions(wallet, blockNumber, blockNumber)
}

async function getBlockRangeTransactions(wallet, fromBlock, toBlock) {
	return await wallet.getTransfers({
		txQuery: {
			hasPaymentId: true,
			minHeight: fromBlock,
			maxHeight: toBlock,
		},
		isIncoming: true,
	});
}

function parseCmdArgv(){
	let args = {}
	for(let item of process.argv.slice(2)) {
		let [key, val] = item.split("=")
		args[key] = val;
	}
	return args;
}

function bigintReplacer(key, val) {
	if(typeof val === 'bigint')
		return val.toString()
	else
		return val
}

function removeCircles(transform) {
	delete transform.tx.incomingTransfers;
	delete transform.tx.block.txs;
	return transform
}

function stringifyTransfers(transfers) {
	transfers = transfers.map(removeCircles)
	return JSON.stringify(transfers, bigintReplacer, 2)
}

const NET_TYPE_MAINNET = 0
const NET_TYPE_TESTNET = 1
const NET_TYPE_STAGENET = 2

module.exports = {
	openWallet,
	syncWallet,
	getIntegratedAddress,
	generateRandomPaymentId,
	getLastBlock,
	getBlockTransactions,
	getBlockRangeTransactions,
	parseCmdArgv,
	bigintReplacer,
	stringifyTransfers,

	NET_TYPE_MAINNET,
	NET_TYPE_TESTNET,
	NET_TYPE_STAGENET
}