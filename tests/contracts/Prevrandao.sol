// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// "Random" winner selection. Predictable on every L2 (constant 1 on Arbitrum).
contract Raffle {
    address[] public players;

    function enter() external payable {
        players.push(msg.sender);
    }

    function pickWinner() external view returns (address) {
        return players[block.prevrandao % players.length];
    }

    function seed() external view returns (uint256 r) {
        assembly {
            r := prevrandao()
        }
    }
}
