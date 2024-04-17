const BASE_URL = 'http://localhost/zex-api/api/';

tokenIndexes = {
    'bst': {
        '1': 'ALICE',
        '2': 'PION'
    }
}

function recoverPublicKey(msgHashHex, signatureHex) {
    const msgHash = ethUtil.toBuffer(msgHashHex);
    const signature = ethUtil.toBuffer(signatureHex);
    const r = signature.slice(0, 32);
    const s = signature.slice(32, 64);
    const v = ethUtil.bufferToInt(signature.slice(64, 65));
    const recoveredPubKey = ethUtil.ecrecover(msgHash, v, r, s);
    return ethUtil.bufferToHex(recoveredPubKey);
}

function showBalances() {
    fetch(BASE_URL + `/users/${public}/balances`).then(response => {
        return response.json();
    }).then(data => {
        const balancesDisplay = document.getElementById('balances');
        const balances = data.map(
            (item) => `${item.chain}-${tokenIndexes[item.chain][item.token]}: ${item.balance/1e18}`).join(', ');
        balancesDisplay.textContent = balances;
    });
}

const web3 = new Web3(window.ethereum);

const connectButton = document.getElementById('connect');
const accountDisplay = document.getElementById('account');

connectButton.onclick = async () => {
    try {
        await window.ethereum.request({ method: 'eth_requestAccounts' });
        console.log('Connected to MetaMask');
        const accounts = await web3.eth.getAccounts();
        const userAddress = accounts[0];
        accountDisplay.textContent = userAddress;
    } catch (error) {
        console.error('User denied account access');
    }
};

const signButton = document.getElementById('sign');
const publicXDisplay = document.getElementById('publicX');
const publicYParityDisplay = document.getElementById('publicYParity');

signButton.onclick = async () => {
    const accounts = await web3.eth.getAccounts();
    if (accounts.length === 0) {
        return alert('Please connect to MetaMask first.');
    }

    const message = "I confirm deposit tokens into Zex.";
    window.ethereum.request({
        method: 'personal_sign',
        params: [web3.utils.utf8ToHex(message), accounts[0]],
    }).then((signature) => {
        const fullMessage = "\x19Ethereum Signed Message:\n" + message.length + message;
        const hash = web3.utils.keccak256(fullMessage)
        const publicKeyHex = recoverPublicKey(hash, signature);
        const x = publicKeyHex.slice(2, 66);
        publicXDisplay.textContent = '0x' + x;
        const y = publicKeyHex.slice(66);
        const yBN = BigInt('0x' + y);
        const yParity = yBN % 2n == 0n ? '0' : '1';
        publicYParityDisplay.textContent = yParity;
        window.public = (yParity == '0' ? '02' : '03') + x;
        console.log(public, 'load balances');
        showBalances();
    }).catch((error) => {
        console.error('Error signing message:', error);
    });
};

const contractABI = [{"inputs":[{"internalType":"address","name":"_verifier","type":"address"},{"internalType":"uint256","name":"_pubKeyX","type":"uint256"},{"internalType":"uint8","name":"_pubKeyYParity","type":"uint8"}],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"tokenIndex","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":true,"internalType":"uint256","name":"pubKeyX","type":"uint256"},{"indexed":true,"internalType":"uint8","name":"pubKeyYParity","type":"uint8"}],"name":"Deposit","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"previousOwner","type":"address"},{"indexed":true,"internalType":"address","name":"newOwner","type":"address"}],"name":"OwnershipTransferred","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"pubKeyX","type":"uint256"},{"indexed":true,"internalType":"uint8","name":"pubKeyYParity","type":"uint8"}],"name":"PublicKeySet","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"token","type":"address"},{"indexed":true,"internalType":"address","name":"to","type":"address"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"Withdrawal","type":"event"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"_publicKeyX","type":"uint256"},{"internalType":"uint8","name":"_pubKeyYParity","type":"uint8"}],"name":"deposit","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"nonces","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pubKeyX","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pubKeyYParity","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"renounceOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"_pubKeyX","type":"uint256"},{"internalType":"uint8","name":"_pubKeyYParity","type":"uint8"}],"name":"setPublicKey","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"_verifier","type":"address"}],"name":"setVerifier","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"newOwner","type":"address"}],"name":"transferOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"verifier","outputs":[{"internalType":"contract ISchnorrVerifier","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"tokenIndex","type":"uint256"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"address","name":"dest","type":"address"},{"internalType":"uint256","name":"nonce","type":"uint256"},{"internalType":"uint256","name":"signature","type":"uint256"},{"internalType":"address","name":"nonceTimesGeneratorAddress","type":"address"}],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"}];
const contractAddress = "0xEca9036cFbfD61C952126F233682f9A6f97E4DBD";
let contract = new web3.eth.Contract(contractABI, contractAddress);

const tokenABI = [{"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"}];

const approveBtn = document.getElementById('approveBtn');
const depositBtn = document.getElementById('depositBtn');

approveBtn.onclick = async () => {
    const accounts = await web3.eth.getAccounts();
    const tokenAddress = document.getElementById('tokenAddress').value;
    const amount = document.getElementById('amount').value;
    const amountInWei = web3.utils.toWei(amount, 'ether');

    let tokenContract = new web3.eth.Contract(tokenABI, tokenAddress);
    tokenContract.methods.approve(contractAddress, amountInWei)
        .send({from: accounts[0]})
        .then(function(result) {
            console.log('Approval successful:', result);
        })
        .catch(function(error) {
            console.error('Error during approval:', error);
        });
}

depositBtn.onclick = async () => {
    const accounts = await web3.eth.getAccounts();
    const tokenAddress = document.getElementById('tokenAddress').value;
    const amount = document.getElementById('amount').value;
    const amountInWei = web3.utils.toWei(amount, 'ether');
    const publicX = publicXDisplay.textContent;
    const publicYParity = parseInt(publicYParityDisplay.textContent);
    contract.methods.deposit(tokenAddress, amountInWei, publicX, publicYParity)
        .send({from: accounts[0]})
        .then(function(result) {
            console.log('Deposit successful:', result);
        })
        .catch(function(error) {
            console.error('Error depositing:', error);
        });
};

function strToHex(str) {
    let hex = '';
    for (let i = 0; i < str.length; i++) {
        const c = str.charCodeAt(i).toString(16);
        hex += c.length === 1 ? '0' + c : c; // Padding with zero if necessary (to form 2 digits)
    }
    return hex;
}

function intToHex(int, size) {
    return int.toString(16).padStart(size*2, '0');
}

function float64ToHex(float64) {
    let buffer = new ArrayBuffer(8);
    let view = new DataView(buffer);
    view.setFloat64(0, float64, false); // Set the float in the buffer, big-endian

    let result = '';
    for (let i = 0; i < 8; i++) {
        result += view.getUint8(i).toString(16).padStart(2, '0');
    }
    return result;
}

function hexToStr(hex) {
    let str = '';    
    for (let i = 0; i < hex.length; i += 2) {
        const hexCode = hex.substring(i, i + 2);
        const byteValue = parseInt(hexCode, 16);
        str += String.fromCharCode(byteValue);
    }
    return str;
}

const placeButton = document.getElementById('placeBtn');
placeBtn.onclick = async () => {
    const name = document.getElementById('orderName').value;
    const amount = parseFloat(document.getElementById('orderAmount').value);
    const price = parseFloat(document.getElementById('orderPrice').value);
    const baseChain = document.getElementById('baseChain').value;
    const baseToken = parseInt(document.getElementById('baseToken').value);
    const quoteChain = document.getElementById('quoteChain').value;
    const quoteToken = parseInt(document.getElementById('quoteToken').value);
    const version = intToHex(1, 1);
    const nonce = 0;
    const t = parseInt(Date.now()/1000);
    let tx = version;
    tx += name == 'buy' ? strToHex('b') : strToHex('s');
    tx += strToHex(baseChain) + intToHex(baseToken, 4);
    tx += strToHex(quoteChain) + intToHex(quoteToken, 4);
    tx += float64ToHex(amount) + float64ToHex(price);
    tx += intToHex(t);
    tx += intToHex(nonce, 4);
    tx += public;
    let msg = 'v: 1\n';
    msg += `name: ${name}\n`;
    msg += `base token: ${baseChain}:${baseToken}\n`;
    msg += `quote token: ${quoteChain}:${quoteToken}\n`;
    msg += `amount: ${Number.isInteger(price) ? amount+'.0' : amount}\n`;
    msg += `price: ${Number.isInteger(price) ? price+'.0' : price}\n`;
    msg += `t: ${t}\n`;
    msg += `nonce: ${nonce}\n`;
    msg += `public: ${public}\n`;

    const accounts = await web3.eth.getAccounts();
    window.ethereum.request({
        method: 'personal_sign',
        params: [web3.utils.utf8ToHex(msg), accounts[0]],
    }).then((signature) => {
        console.log('signature', signature);
        fetch(BASE_URL + '/txs', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify([hexToStr(tx + signature.slice(2))])
        });
    });
};