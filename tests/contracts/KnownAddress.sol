// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IArbSys {
    function arbBlockNumber() external view returns (uint256);
}

interface IL1Block {
    function number() external view returns (uint64);
}

/// Addresses that only exist (or only mean this) on some chains.
contract Integrations {
    address public constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address public constant MULTICALL3 = 0xcA11bde05977b3631167028862bE2a173976CA11;
    IL1Block public constant L1_BLOCK = IL1Block(0x4200000000000000000000000000000000000015);

    function l2Block() external view returns (uint256) {
        return IArbSys(address(100)).arbBlockNumber();
    }

    function l1Number() external view returns (uint64) {
        return L1_BLOCK.number();
    }
}
