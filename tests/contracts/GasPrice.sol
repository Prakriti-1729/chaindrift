// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Meta-transaction relayer refund: ignores the L1 data fee on rollups.
contract Relayer {
    function relay(address target, bytes calldata data) external {
        uint256 startGas = gasleft();
        (bool ok, ) = target.call(data);
        require(ok);
        uint256 refund = (startGas - gasleft() + 21_000) * tx.gasprice;
        (ok, ) = payable(msg.sender).call{value: refund}("");
    }

    function minFee() external view returns (uint256) {
        return block.basefee * 2;
    }
}
