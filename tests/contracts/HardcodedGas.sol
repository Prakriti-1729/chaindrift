// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IHook {
    function onEvent(uint256 id) external;
}

/// Gas constants tuned for Ethereum's gas schedule.
contract Notifier {
    function notifyHook(address hook, uint256 id) external {
        (bool ok, ) = hook.call{gas: 50_000}(abi.encodeCall(IHook.onEvent, (id)));
        ok;
    }

    function notifyTyped(IHook hook, uint256 id) external {
        hook.onEvent{gas: 30_000}(id);
    }

    function guarded() external view returns (bool) {
        if (gasleft() < 100_000) return false;
        return true;
    }

    function rawCall(address target) external returns (bool ok) {
        assembly {
            ok := call(25000, target, 0, 0, 0, 0, 0)
        }
    }
}
