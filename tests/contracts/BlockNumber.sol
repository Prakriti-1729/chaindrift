// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Vesting measured in blocks: correct on Ethereum, wildly wrong on most L2s.
contract BlockVesting {
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000; // 12s blocks
    uint256 public immutable start;

    constructor() {
        start = block.number;
    }

    function vested(uint256 total) external view returns (uint256) {
        return (total * (block.number - start)) / BLOCKS_PER_YEAR;
    }

    function rawBlock() external view returns (uint256 n) {
        assembly {
            n := number()
        }
    }
}
