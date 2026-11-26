// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Transient-storage reentrancy lock (EIP-1153): needs Cancun opcodes on the target chain.
contract TransientLock {
    function guarded() external returns (uint256 v) {
        assembly {
            if tload(0) { revert(0, 0) }
            tstore(0, 1)
        }
        v = 42;
        assembly {
            tstore(0, 0)
        }
    }

    function copy(bytes memory data) external pure returns (bytes memory) {
        return abi.encode(data, data);
    }
}
