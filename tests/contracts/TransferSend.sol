// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Payouts with a 2300 gas stipend: the Gemholic bug class on ZKsync.
contract Payouts {
    mapping(address => uint256) public owed;

    function withdraw() external {
        uint256 amount = owed[msg.sender];
        owed[msg.sender] = 0;
        payable(msg.sender).transfer(amount);
    }

    function tryPay(address payable to, uint256 amount) external returns (bool) {
        return to.send(amount);
    }
}
