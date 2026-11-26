// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Passkey (P-256) verification plus classic precompiles with uneven L2 support.
contract Verifier {
    address constant P256 = address(0x100);
    address internal constant SENTINEL = address(0x1); // linked-list sentinel: NOT a precompile call

    function verifyPasskey(bytes calldata input) external view returns (bool) {
        (bool ok, bytes memory out) = P256.staticcall(input);
        return ok && out.length == 32 && abi.decode(out, (uint256)) == 1;
    }

    function verifyInline(bytes calldata input) external view returns (bool ok) {
        (ok, ) = address(0x100).staticcall(input);
    }

    function legacyHash(bytes calldata data) external pure returns (bytes20) {
        return ripemd160(data);
    }

    function modexp(bytes memory input) external view returns (bytes32 r) {
        assembly {
            let ok := staticcall(gas(), 0x05, add(input, 0x20), mload(input), 0, 32)
            r := mload(0)
        }
    }

    function isSentinel(address a) external pure returns (bool) {
        return a == SENTINEL;
    }
}
