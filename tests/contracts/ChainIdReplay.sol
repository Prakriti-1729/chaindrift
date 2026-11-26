// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Domain without chainId: signatures replay on every chain.
contract NoChainIdPermit {
    bytes32 public immutable DOMAIN_SEPARATOR;

    constructor() {
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,address verifyingContract)"),
                keccak256("Token"),
                keccak256("1"),
                address(this)
            )
        );
    }
}

/// Domain cached at deployment and never re-checked: replays across a chain split.
contract CachedPermit {
    bytes32 public immutable DOMAIN_SEPARATOR;

    constructor() {
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("Token"),
                keccak256("1"),
                block.chainid,
                address(this)
            )
        );
    }
}

/// Correct: recomputes the separator if the chain id changed (OpenZeppelin style). Must not be flagged.
contract GoodPermit {
    bytes32 private immutable _cachedSeparator;
    uint256 private immutable _cachedChainId;
    bytes32 private constant TYPE_HASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");

    constructor() {
        _cachedChainId = block.chainid;
        _cachedSeparator = _build();
    }

    function domainSeparator() public view returns (bytes32) {
        return block.chainid == _cachedChainId ? _cachedSeparator : _build();
    }

    function _build() private view returns (bytes32) {
        return keccak256(abi.encode(TYPE_HASH, keccak256("Token"), keccak256("1"), block.chainid, address(this)));
    }
}
