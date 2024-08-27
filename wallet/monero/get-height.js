const utils = require("./monero-utils.js");
const { connectToDaemonRpc } = require('monero-ts');

async function main() {
	const args = utils.parseCmdArgv()
	let daemon = await connectToDaemonRpc(args.rpc);
	let height = await daemon.getHeight();
	let block = await daemon.getBlockHeaderByHeight(height-1);

	console.log(JSON.stringify({
		"height": height-1,
		"block": block
	}, utils.bigintReplacer))
}

main()
	.catch(e => console.log(e))
	.finally(() => process.exit(0))