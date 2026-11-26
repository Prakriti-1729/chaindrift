// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Child {
    uint256 public x;
}

/// Counterfactual deployment: the precomputed address is wrong on ZKsync.
contract Factory {
    function predict(bytes32 salt) public view returns (address) {
        bytes32 h = keccak256(
            abi.encodePacked(bytes1(0xff), address(this), salt, keccak256(type(Child).creationCode))
        );
        return address(uint160(uint256(h)));
    }

    function deploySalted(bytes32 salt) external returns (address) {
        return address(new Child{salt: salt}());
    }

    function deployRaw(bytes memory code, bytes32 salt) external returns (address a) {
        assembly {
            a := create2(0, add(code, 0x20), mload(code), salt)
        }
    }
}
