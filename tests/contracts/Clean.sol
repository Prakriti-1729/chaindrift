// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Look-alikes that are portable across chains. ChainDrift must report nothing here
/// (apart from compiler-emitted opcodes, which the tests exclude).
contract PortableVault {
    address internal constant SENTINEL = address(0x1);
    uint256 public constant DURATION = 365 days;
    uint256 public immutable start;
    mapping(address => uint256) public balance;

    constructor() {
        start = block.timestamp;
    }

    function vested(uint256 total) external view returns (uint256) {
        return (total * (block.timestamp - start)) / DURATION;
    }

    function withdraw() external {
        uint256 amount = balance[msg.sender];
        balance[msg.sender] = 0;
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        require(ok);
    }

    function initializing() external view returns (bool) {
        return address(this).code.length == 0;
    }

    function isSentinel(address a) external pure returns (bool) {
        return a == SENTINEL;
    }

    function recover(bytes32 h, uint8 v, bytes32 r, bytes32 s) external pure returns (address) {
        return ecrecover(h, v, r, s);
    }
}
