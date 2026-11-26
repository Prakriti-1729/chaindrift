// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// A deliberately realistic demo: a staking vault with a weekly raffle, gasless permits,
// passkey login and per-user sub-accounts, written for Ethereum and then "just deployed"
// to Arbitrum, Base, ZKsync, Scroll and Linea. Every line compiles and works on Ethereum.
// Run `chaindrift scan examples/OmniStake.sol -o report.html` to see what breaks elsewhere.

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

interface IPriceFeed {
    function latestAnswer() external view returns (int256);
}

contract SubAccount {
    address public immutable owner;

    constructor() {
        owner = msg.sender;
    }
}

contract OmniStake {
    // --- configuration ("same on every chain", right?) --------------------------------
    IERC20 public constant WETH = IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    IPriceFeed public constant ETH_USD = IPriceFeed(0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419);
    address public constant P256_VERIFIER = address(0x100);
    uint256 public constant BLOCKS_PER_DAY = 7200;
    uint256 public constant REWARD_PER_DAY_BPS = 5;

    bytes32 public immutable DOMAIN_SEPARATOR;
    bytes32 public constant PERMIT_TYPEHASH =
        keccak256("Unstake(address owner,uint256 amount,uint256 nonce,uint256 deadline)");

    struct Stake {
        uint256 amount;
        uint256 sinceBlock;
    }

    mapping(address => Stake) public stakes;
    mapping(address => uint256) public nonces;
    address[] public raffleEntrants;

    modifier onlyHumans() {
        require(tx.origin == msg.sender, "humans only");
        _;
    }

    modifier nonReentrant() {
        assembly {
            if tload(0) { revert(0, 0) }
            tstore(0, 1)
        }
        _;
        assembly {
            tstore(0, 0)
        }
    }

    constructor() {
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("OmniStake"),
                keccak256("1"),
                block.chainid,
                address(this)
            )
        );
    }

    // --- staking ------------------------------------------------------------------------
    function stake(uint256 amount) external nonReentrant {
        WETH.transferFrom(msg.sender, address(this), amount);
        stakes[msg.sender] = Stake(stakes[msg.sender].amount + amount, block.number);
    }

    function pendingReward(address user) public view returns (uint256) {
        Stake memory s = stakes[user];
        uint256 daysStaked = (block.number - s.sinceBlock) / BLOCKS_PER_DAY;
        return (s.amount * REWARD_PER_DAY_BPS * daysStaked) / 10_000;
    }

    function stakeValueUsd(address user) external view returns (uint256) {
        return (stakes[user].amount * uint256(ETH_USD.latestAnswer())) / 1e8;
    }

    // --- gasless unstake via signature ---------------------------------------------------
    function unstakeBySig(address owner, uint256 amount, uint256 deadline, uint8 v, bytes32 r, bytes32 s)
        external
        nonReentrant
    {
        require(block.timestamp <= deadline, "expired");
        bytes32 digest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                DOMAIN_SEPARATOR,
                keccak256(abi.encode(PERMIT_TYPEHASH, owner, amount, nonces[owner]++, deadline))
            )
        );
        require(ecrecover(digest, v, r, s) == owner, "bad sig");
        stakes[owner].amount -= amount;
        WETH.transfer(owner, amount);

        // reimburse the relayer for the gas it spent
        uint256 refund = 80_000 * tx.gasprice;
        payable(msg.sender).transfer(refund);
    }

    // --- weekly raffle --------------------------------------------------------------------
    function enterRaffle() external payable onlyHumans {
        require(msg.value == 0.01 ether, "ticket is 0.01 ETH");
        raffleEntrants.push(msg.sender);
    }

    function drawRaffle() external nonReentrant {
        uint256 winner = uint256(keccak256(abi.encode(block.prevrandao, raffleEntrants.length)))
            % raffleEntrants.length;
        address payable w = payable(raffleEntrants[winner]);
        delete raffleEntrants;
        w.transfer(address(this).balance);
    }

    // --- passkey login (WebAuthn / secp256r1) --------------------------------------------
    function verifyPasskey(bytes32 hash, bytes32 r, bytes32 s, bytes32 x, bytes32 y) public view returns (bool) {
        (bool ok, bytes memory out) = P256_VERIFIER.staticcall(abi.encode(hash, r, s, x, y));
        return ok && out.length == 32 && abi.decode(out, (uint256)) == 1;
    }

    // --- per-user sub-accounts at predictable addresses ------------------------------------
    function subAccountOf(address user) public view returns (address) {
        bytes32 salt = bytes32(uint256(uint160(user)));
        bytes32 h = keccak256(
            abi.encodePacked(bytes1(0xff), address(this), salt, keccak256(type(SubAccount).creationCode))
        );
        return address(uint160(uint256(h)));
    }

    function createSubAccount() external returns (address account) {
        account = address(new SubAccount{salt: bytes32(uint256(uint160(msg.sender)))}());
        require(account == subAccountOf(msg.sender), "address mismatch");
    }
}
