// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Killable {
    address payable public owner = payable(msg.sender);

    function kill() external {
        require(msg.sender == owner);
        selfdestruct(owner);
    }
}
