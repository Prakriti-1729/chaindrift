// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract FeeConfig {
    function fee() external view returns (uint256) {
        if (block.chainid == 42161) return 5;
        if (block.chainid != 1) return 10;
        return 30;
    }
}
