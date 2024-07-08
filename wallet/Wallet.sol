// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {BLSSignatureChecker, IRegistryCoordinator} from "@eigenlayer-middleware/src/BLSSignatureChecker.sol";

contract Wallet is Ownable, BLSSignatureChecker {

    uint256 internal constant _THRESHOLD_DENOMINATOR = 100;
    uint256 internal constant _THRESHOLD_PERCENTAGE = 70;

    mapping(address => uint256) public nonces;
    mapping(address => uint256) private tokenToIndex;
    mapping(uint256 => address) private indexToToken;
    uint256 private nextTokenIndex = 1;

    event Deposit(uint256 indexed tokenIndex, uint256 amount, uint256 indexed pubKeyX, uint8 indexed pubKeyYParity);
    event Withdrawal(address indexed token, address indexed to, uint256 amount);
    event PublicKeySet(uint256 indexed pubKeyX, uint8 indexed pubKeyYParity);

    constructor(
        IRegistryCoordinator _registryCoordinator
    ) BLSSignatureChecker(_registryCoordinator) {}

    function deposit(address token, uint256 amount, uint256 _publicKeyX, uint8 _pubKeyYParity) external {
        require(amount > 0, "Amount must be greater than 0");

        uint256 tokenIndex = tokenToIndex[token];
        if (tokenIndex == 0) {
            tokenIndex = nextTokenIndex++;
            tokenToIndex[token] = tokenIndex;
            indexToToken[tokenIndex] = token; // Update reverse lookup mapping
        }

        bool sent = IERC20(token).transferFrom(msg.sender, address(this), amount);
        require(sent, "Token transfer failed");
        emit Deposit(tokenIndex, amount, _publicKeyX, _pubKeyYParity);
    }

    function withdraw(
        uint256 tokenIndex,
        uint256 amount,
        address dest,
        uint256 nonce,
        bytes calldata quorumNumbers,
        NonSignerStakesAndSignature memory nonSignerStakesAndSignature
    ) external {
        require(nonce == nonces[dest], "Invalid nonce");
        bytes32 message = keccak256(abi.encode(dest, tokenIndex, amount, nonce));

        // check the BLS signature
        (
            QuorumStakeTotals memory quorumStakeTotals,
            bytes32 hashOfNonSigners
        ) = checkSignatures(
                message,
                quorumNumbers,
                uint32(block.number) - 1,
                nonSignerStakesAndSignature
            );

        // check that signatories own at least a threshold percentage of each quourm
        for (uint i = 0; i < quorumNumbers.length; i++) {
            require(
                quorumStakeTotals.signedStakeForQuorum[i] *
                    _THRESHOLD_DENOMINATOR >=
                    quorumStakeTotals.totalStakeForQuorum[i] *
                        _THRESHOLD_PERCENTAGE,
                "Signatories do not own at least threshold percentage of a quorum"
            );
        }

        nonces[dest] += 1;

        address token = indexToToken[tokenIndex];
        bool sent = IERC20(token).transfer(dest, amount);
        require(sent, "Token transfer failed");
        emit Withdrawal(token, dest, amount);
    }
}
