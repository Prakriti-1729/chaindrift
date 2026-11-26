// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// "Humans only" checks that EIP-7702 and native account abstraction break.
contract HumansOnly {
    modifier onlyEOA() {
        require(tx.origin == msg.sender, "no contracts");
        _;
    }

    function mint() external onlyEOA {}

    function isPerson(address a) external view returns (bool) {
        return a.code.length == 0;
    }

    function initializing() external view returns (bool) {
        // Standard constructor-detection idiom: NOT an EOA check, must not be flagged.
        return address(this).code.length == 0;
    }
}
