# ChainDrift: your learning guide

This guide is for **you**, the builder of ChainDrift. It explains, from the ground up, every concept, tool and design
decision in the project, so you can understand it fully, extend it, and explain it confidently in an interview.

Read it in order the first time. Later, use the table of contents to jump around.

---

## Contents

- [Part 1: Blockchain basics you need](#part-1-blockchain-basics-you-need)
- [Part 2: Why "EVM chains" are not all the same](#part-2-why-evm-chains-are-not-all-the-same)
- [Part 3: The Solidity features ChainDrift looks at](#part-3-the-solidity-features-chaindrift-looks-at)
- [Part 4: Each bug class, explained simply](#part-4-each-bug-class-explained-simply)
- [Part 5: The tools used in this project](#part-5-the-tools-used-in-this-project)
- [Part 6: Code walkthrough, file by file](#part-6-code-walkthrough-file-by-file)
- [Part 7: Following one finding from start to finish](#part-7-following-one-finding-from-start-to-finish)
- [Part 8: How the project is tested](#part-8-how-the-project-is-tested)
- [Part 9: Explaining ChainDrift in an interview](#part-9-explaining-chaindrift-in-an-interview)
- [Part 10: Exercises to deepen your understanding](#part-10-exercises-to-deepen-your-understanding)
- [Glossary](#glossary)

---

## Part 1: Blockchain basics you need

### Ethereum and smart contracts
**Ethereum** is a blockchain: a shared database that thousands of computers agree on. Besides holding balances, it
runs **smart contracts**, small programs stored on the chain that anyone can call. Once deployed, a contract's code
can't be changed, which is why bugs are so expensive.

### The EVM
Contracts run on the **EVM (Ethereum Virtual Machine)**, a simple, deterministic computer that every node runs
identically. The EVM executes **bytecode**, a sequence of one-byte instructions called **opcodes** (`ADD`, `SSTORE`,
`CALL`...). You don't write bytecode. You write **Solidity**, and the compiler (**solc**) turns it into bytecode.

```
Solidity source  --solc-->  bytecode (e.g. 6080604052...)  --deploy-->  lives at an address on chain
```

### Accounts: EOAs and contracts
- An **EOA (Externally Owned Account)** is a normal wallet controlled by a private key, like MetaMask. Historically it had *no code*.
- A **contract account** has code and is controlled by that code.

`msg.sender` is whoever called the current function. `tx.origin` is the EOA that signed the whole transaction.

### Gas
Every opcode costs **gas**. A transaction pays `gas used x gas price`. Gas stops infinite loops and pays the network.
When a contract calls another contract, it can choose how much gas to forward. That matters a lot in Part 4.

### Blocks and block globals
Transactions are grouped into **blocks**. Solidity can read information about the current block:
`block.number` (height), `block.timestamp` (time), `block.prevrandao` (a random-ish value), `block.chainid` (which
chain this is), `block.basefee` (base gas price) and `tx.gasprice`. ChainDrift's first big insight is that **these
values mean different things on different chains.**

### Hard forks and EIPs
Ethereum improves through **EIPs (Ethereum Improvement Proposals)**, bundled into upgrades called **hard forks**.
The ones that matter here:

| Fork (year) | Relevant change |
|---|---|
| Shanghai (2023) | new opcode `PUSH0` (EIP-3855) |
| Cancun (2024) | transient storage `TLOAD`/`TSTORE` (EIP-1153), `MCOPY` (EIP-5656), blobs (EIP-4844), `SELFDESTRUCT` mostly disabled (EIP-6780) |
| Prague/Pectra (2025) | BLS12-381 precompiles (EIP-2537); **EIP-7702**, which lets EOAs have code |
| Osaka/Fusaka (late 2025) | P-256 signature precompile (EIP-7951), `CLZ` opcode (EIP-7939) |

Other chains adopt these forks **at different times, partially, or not at all**. That's ChainDrift's second big insight.

---

## Part 2: Why "EVM chains" are not all the same

### Layer 1 vs Layer 2
Ethereum (**Layer 1, L1**) is secure but slow and expensive. **Layer 2s (L2s)** run transactions off Ethereum and post
compressed results back to it, inheriting much of its security at lower cost.

- **Optimistic rollups** (Arbitrum, OP Mainnet, Base) assume posted results are correct and allow a challenge
  window for fraud proofs. Base and OP Mainnet share the **OP Stack** codebase.
- **ZK rollups** (ZKsync Era, Scroll, Linea) post cryptographic **zero-knowledge proofs** that the results are correct.
  Proving EVM execution is hard, so some ZK chains changed parts of the EVM to make proving easier. ZKsync Era even
  runs its own VM, **EraVM**, and compiles Solidity with its own compiler, **zksolc**.

Other EVM chains, like Polygon PoS, BNB Smart Chain and Avalanche C-Chain, are independent L1s or sidechains that run
EVM-compatible software.

### The sequencer
Most L2s have a **sequencer**: one operator that orders transactions and produces L2 blocks. This is why L2 block
values like `prevrandao` can't be truly random. There's no large validator set producing randomness, and the
sequencer can know values in advance.

### Two costs on rollups
On a rollup you pay (1) L2 execution gas and (2) an **L1 data fee** for posting your transaction data to Ethereum.
Contracts that compute "what did this transaction cost?" from `tx.gasprice` miss the second part.

### "EVM-equivalent" vs "EVM-compatible"
- **EVM-equivalent** means the same bytecode behaves the same way. That's the goal, but there are small exceptions
  (block values, precompiles, gas).
- **EVM-compatible** means Solidity works, but with documented differences (ZKsync is the clearest example).

Every chain publishes a "differences from Ethereum" page. ChainDrift's knowledge base is essentially those pages,
turned into structured data and checked against your code automatically.

---

## Part 3: The Solidity features ChainDrift looks at

### Sending ETH: `transfer`, `send`, `call`
```solidity
payable(to).transfer(amount);            // forwards only 2300 gas; reverts on failure
bool ok = payable(to).send(amount);      // forwards only 2300 gas; returns false on failure
(bool ok, ) = to.call{value: amount}(""); // forwards (almost) all gas; recommended today
```
The **2300 gas stipend** was a reentrancy defense. It's now considered harmful because gas costs change.

### CREATE and CREATE2
Contracts can deploy contracts.
- `CREATE`: the address depends on the deployer address and its nonce.
- `CREATE2`: the address is `keccak256(0xff ++ deployer ++ salt ++ keccak256(initcode))`, so you can **predict an
  address before deploying**. This is used for "counterfactual" wallets and same-address-on-every-chain deployments.
  In Solidity: `new Child{salt: s}()`.

### `selfdestruct`
This used to delete a contract and send its ETH somewhere. Since Cancun (EIP-6780) it only deletes when called in the
same transaction that created the contract. It's deprecated.

### Inline assembly (Yul)
Solidity lets you write low-level code:
```solidity
assembly { n := number() }   // same as block.number
assembly { ok := staticcall(gas(), 0x05, ptr, len, out, 32) }
```
Many tools only look at the Solidity part and miss assembly. ChainDrift catches both (see Part 5, SlithIR).

### Constants and immutables
```solidity
uint256 public constant BLOCKS_PER_YEAR = 2_628_000;  // fixed at compile time
uint256 public immutable start;                         // set once in the constructor
```

### Interfaces and calls to fixed addresses
```solidity
IArbSys(address(100)).arbBlockNumber();  // call a contract at a hardcoded address
```

### Precompiles
**Precompiles** are built-in contracts at tiny addresses, implemented natively for speed: `0x01` ecrecover (signature
recovery), `0x02` sha256, `0x03` ripemd160, `0x05` modexp, `0x06`–`0x08` elliptic-curve maths, `0x09` blake2f,
`0x0a` KZG, `0x0b`–`0x11` BLS12-381, and `0x100` P256VERIFY (used by passkeys and WebAuthn).
**Key fact:** calling an address with no code *succeeds* and returns empty data. So a missing precompile doesn't
cause an error. It silently returns nothing.

### EIP-712 signatures and replay
**EIP-712** is the standard for signing structured data ("I authorise unstaking 5 ETH"). The signature covers a
**domain separator** built from the contract name, version, **chainId** and contract address. The chainId is what
stops a signature made for one chain from working on another chain where the same contract exists at the same address.
The safe pattern, used by OpenZeppelin, caches the separator but **recomputes it if `block.chainid` changes** (after a
chain fork).

### EIP-7702 and account abstraction
- **Account abstraction** means accounts whose rules are defined by code (smart wallets). ZKsync has it natively.
- **EIP-7702** (Pectra, 2025) lets an ordinary EOA *delegate* to contract code. After that, the EOA has code, and it
  can run batched logic while still being `tx.origin`.

So checks like `tx.origin == msg.sender` or `addr.code.length == 0` no longer prove "this is a human, not a contract".

### Opcodes the compiler adds for you
Newer `solc` versions emit new opcodes **by default**: `PUSH0` since 0.8.20 and `MCOPY` since 0.8.25. A chain that
hasn't adopted those forks can't run that bytecode. You fix it with the compiler flag `--evm-version paris` (or
another older version).

### Bytecode metadata
`solc` appends a small **CBOR-encoded metadata** blob to the end of the bytecode (a hash of the source and the
compiler version). Its length is stored in the last 2 bytes. It isn't code, so a bytecode scanner must cut it off.

---

## Part 4: Each bug class, explained simply

For each rule: the **idea**, a **bad example**, **why it breaks**, and the **fix**.

**1. `block-number`.** Using block counts as a clock.
```solidity
uint256 constant BLOCKS_PER_DAY = 7200;  // assumes 12s blocks
uint256 daysStaked = (block.number - since) / BLOCKS_PER_DAY;
```
On Base (2s blocks), a "day" passes in 4 hours, so rewards are paid 6x too fast. On Arbitrum, `block.number` is an
approximate *Ethereum* block number. **Fix:** use `block.timestamp`.

**2. `prevrandao`.** "Random" numbers from block data.
On Arbitrum it's always `1`, on ZKsync a constant, on Scroll `0`, and on OP Stack it's an L1 value known in advance.
A raffle winner becomes predictable. **Fix:** a VRF oracle or a commit-reveal scheme.

**3. `transfer-send`.** The 2300 gas stipend.
On ZKsync, gas costs differ and 2300 is often too little, so the transfer reverts and funds get stuck. This
reportedly happened in the Gemholic sale (~921 ETH, 2023). **Fix:** `call{value: x}("")` plus a reentrancy guard.

**4. `create2-address`.** Predicting deployment addresses.
ZKsync computes CREATE2 addresses with a different formula, so the predicted address is wrong. **Fix:** use the
chain's own address helper, or don't assume addresses are equal across chains.

**5. `selfdestruct`.** Rejected by the ZKsync compiler, disabled on Scroll, and changed meaning on Ethereum.
**Fix:** remove it and use pause/withdraw patterns.

**6. `hardcoded-gas`.** `call{gas: 50_000}` or `if (gasleft() < 100_000)`.
Gas numbers tuned on Ethereum don't hold where gas pricing differs (L1 data costs on Arbitrum, pubdata on ZKsync).
**Fix:** avoid fixed gas, or make it configurable.

**7. `gas-price`.** Refunding gas using `tx.gasprice`.
Rollups charge an extra L1 data fee, so the refund is too small and relayers lose money. **Fix:** use the chain's fee
oracle, or avoid on-chain refund maths.

**8. `eoa-check`.** "Humans only" checks. EIP-7702 and native account abstraction break them. **Fix:** don't use
EOA checks as security. Design against the actual threat instead.

**9. `chainid-replay`.** EIP-712 without `chainId`, a hardcoded one, or one cached forever. Signatures work on other
chains or forks. **Fix:** include `block.chainid` and recompute the separator when it changes.

**10. `chain-gated-logic`.** `if (block.chainid == 42161)`. Not a bug on its own, but those paths are often only
tested on one chain. Reported as info.

**11. `precompile`.** Calling precompiles that may be missing, which *silently succeeds*. **Fix:** check support on
every target chain and check the returned data length.

**12. `known-address`.** Hardcoded WETH, USDC, Chainlink or system-contract addresses that only exist on some chains.
**Fix:** pass addresses in at deploy time.

**13. `opcode-support`.** The compiler emitted `PUSH0`, `MCOPY`, `TSTORE`... that a target chain may not support.
**Fix:** compile with an older `--evm-version`.

---

## Part 5: The tools used in this project

### Python, venv, pip
- The project is written in **Python 3.11+**. It uses `tomllib`, which was added to the standard library in 3.11.
- A **virtual environment** (`.venv/`) keeps this project's packages separate from the rest of your system.
- **pip** installs packages. `pip install -e .` installs the project in *editable* mode, so code changes take effect
  immediately.
- `pyproject.toml` is the project's config file: its name, dependencies, the `chaindrift` command, and pytest settings.

### solc and solc-select
- **solc** is the official Solidity compiler.
- **solc-select** installs and switches between solc versions. On this machine it put the compiler in
  `.venv/.solc-select/artifacts/solc-0.8.39/`.
- `chaindrift/solc.py` finds the compiler directly instead of relying on the `solc` command. That's because Windows
  Application Control blocked the small `solc-select.exe` launcher during setup.

### Slither and crytic-compile
- **Slither** is a widely used static analyzer for Solidity, built by Trail of Bits. ChainDrift uses Slither as a
  *library*, not its existing detectors.
- **crytic-compile** is the part of Slither that runs the compiler (or Foundry/Hardhat) and collects the outputs:
  the AST and the bytecode.

### What "static analysis" means
**Static** analysis examines code *without running it*. **Dynamic** analysis runs it (tests, fuzzing). Static
analysis can check every line of a contract in seconds, but it reports what *could* happen, so a human still judges
whether each finding matters.

### SlithIR, the key idea
Slither converts Solidity into a simpler **intermediate representation (IR)** called **SlithIR**. Each line becomes a
few small operations. This is real output from the probe contract used to explore Slither while building ChainDrift:

```text
NODE  'b = block.number + block.prevrandao + tx.gasprice + block.chainid'
   vars_read: block.number, block.chainid, block.prevrandao, tx.gasprice
NODE  'to.transfer(b)'
   IR Transfer      dest:to value:b
NODE  '(ok,None) = to.call{gas: 5000}()'
   IR LowLevelCall  dest:to, function:call  gas:5000
NODE  '(ok,None) = address(0x100).staticcall()'
   IR TypeConversion TMP_9 = CONVERT 256 to address
   IR LowLevelCall  dest:TMP_9, function:staticcall
NODE  (inside assembly) 'y := number()'
   IR SolidityCall  TMP_33 = SOLIDITY_CALL number()()
```

Notice the following:
- Solidity's `block.number` shows up as a **variable read**. Assembly's `number()` shows up as a **SolidityCall**.
  ChainDrift checks both (see `global_read` in `rules/base.py`).
- `.transfer()` becomes a dedicated `Transfer` operation, which makes the transfer rule trivial.
- `address(0x100)` becomes `CONVERT 256 to address` into a temporary `TMP_9`, and then the call uses `TMP_9`. To know
  the call goes to `0x100`, you must follow `TMP_9` back to its constant. That's what the **ConstTracker** in `ir.py`
  does.

Slither's structure: **Contract → Functions → Nodes** (roughly one per statement) **→ IR operations**.

### TOML
**TOML** is a simple configuration format (like JSON or YAML, but easier to read). The knowledge base uses it so
non-programmers can update chain facts:
```toml
[rules.prevrandao.chains]
arbitrum = { severity = "high", confidence = "high", note = "always returns the constant 1." }
```

### SARIF
**SARIF** is a standard JSON format for static-analysis results. GitHub reads it and shows the results as
**code-scanning alerts** on pull requests. ChainDrift writes it with `-o results.sarif`.

### pytest
**pytest** is Python's most popular test framework. Any function named `test_*` in `tests/` is a test, and `assert`
checks a condition. Features used here:
- `tmp_path` gives a fresh temporary folder per test.
- `capsys` captures printed output.
- `monkeypatch` temporarily changes environment variables.
- `@pytest.mark.parametrize` runs one test with several inputs.
- `pytest.raises` asserts that an error is raised.

### GitHub Actions
`.github/workflows/ci.yml` tells GitHub to install the project, run the tests and upload a SARIF scan on every push.
It's the "green checkmark" on a repository.

### The HTML report
The report is one self-contained file: HTML, CSS and a little JavaScript, with no external libraries. Severity colours
follow a status palette (red = high, orange = medium, yellow = verify, grey = low, green = unaffected), and every cell
also has a **text label**, so meaning never depends on colour alone. That matters for colour-blind readers. Tooltips
insert text with `textContent`, never `innerHTML`, so a malicious string inside a scanned contract can't inject code
into the report.

---

## Part 6: Code walkthrough, file by file

### `models.py`: the vocabulary
- `SEVERITIES = ("none", "info", "low", "check", "medium", "high")` is ordered from least to most urgent. `check`
  ("unknown, verify") sits above `low` on purpose: not knowing is riskier than a known small issue.
- `Site` is a *chain-independent* fact: rule id, contract, function, file, line, code snippet, detail, and an
  optional `variant` (a sub-type, like `"no-chainid"` or a precompile address).
- `Assessment` is how one chain treats a site: severity, confidence and note.
- `Finding` is a site plus its metadata plus one assessment per chain. `finding.severity` is the worst across chains.

### `knowledge/__init__.py`: loading and validating the data
- `KnowledgeBase` loads the five TOML files.
- `assess_rule(rule, chain, variant)` looks things up from most to least specific: variant+chain, variant default,
  rule+chain, rule default.
- `render()` fills in `{chain}` and `{block_time_s}`.
- `_validate()` fails loudly on typos (an unknown chain, an invalid severity).
- `load_knowledge()` is cached with `lru_cache`, so the files are read once.

### `ir.py`: helpers over SlithIR
- `call_name(ir)` turns `"staticcall(uint256,...)"` into `"staticcall"`.
- `constant_int(v)` gets the integer value of a Slither `Constant` (addresses included).
- `ConstTracker` walks a function's IR in order and remembers which temporaries hold a known integer, following
  `TypeConversion` chains and `constant` state variables. It also marks which values were converted *to an address or
  contract type*. That's how `address(0x1)` the sentinel is told apart from `address(0x100)` the precompile being
  called.
- `function_trackers(function)` yields `(node, ir, tracker)` so rules can ask "what is this value?" at any point.

### `context.py`: one compiled project
- It filters out dependency contracts (unless `--include-deps`).
- It provides `functions()`, `nodes()` and `irs()`, generators that make rules short.
- `site(...)` builds a `Site` from anything with a source mapping and reads the code line for the snippet.
- `bytecodes()` matches compiled bytecode to contracts for the opcode rule.

### `rules/`: the 13 detectors
Each rule subclasses `Rule` and implements `detect(ctx)`, which yields Sites. Most rules use the default `assess()`
(a knowledge-base lookup). Three override it because they use their own tables:
- `Precompile.assess` maps `support = yes/no/limited/unknown` to `none/high/medium/check`.
- `KnownAddress.assess` checks whether the chain is in the address's `on` list, or in its `missing` list for
  `on = "*"` entries.
- `OpcodeSupport.assess` combines all the opcodes in one contract and reports the worst.

Patterns worth learning from:
- `GlobalReadRule` (`environment.py`) is a small base class, so `BlockNumber`, `Prevrandao` and `GasPrice` are each
  just two sets of names. That's reuse through inheritance.
- `ChainIdReplay` (`signatures.py`) reasons about a whole contract: does it read `block.chainid` *only* in the
  constructor? If yes, the separator is cached and never re-checked.
- `scan_opcodes` (`execution.py`) is a tiny disassembler. Opcodes `0x60`–`0x7f` (`PUSH1`–`PUSH32`) are followed by
  1–32 bytes of *data*, which must be skipped, or data bytes would be miscounted as opcodes.

### `engine.py`: the orchestrator
1. Validates inputs (chains, rules, the target exists, there are `.sol` files).
2. Decides compile units: a framework project root, a single file, or each `.sol` file in a folder (skipping `lib/`,
   `node_modules/`...).
3. For each unit: compiles with Slither, records compile errors (it doesn't crash), builds a `Context`, runs every
   rule, **de-duplicates** sites (the same imported file can be compiled several times), assesses every site for every
   selected chain, and applies `--min-severity`.
4. Sorts findings: most severe first, then by file and line.

### `report/`: four outputs
- `common.py`'s `grouped_assessments()` merges chains with identical notes ("HIGH: Arbitrum One, Base, Scroll").
- `text.py` gives terminal output (colour only when printing to a terminal).
- `jsonout.py` gives machine-readable output.
- `sarif.py` gives GitHub code scanning output.
- `html.py` gives the visual report: summary tiles, the matrix, the per-chain table and detail cards.

### `cli.py`: the command line
`argparse` defines `scan`, `chains` and `rules`. The exit-code policy lives here: **2** if anything failed to compile
(this wins, so CI can't pass on broken input), **1** if a finding reaches `--fail-on`, otherwise **0**.

---

## Part 7: Following one finding from start to finish

Command: `python -m chaindrift scan examples/OmniStake.sol --chains ethereum,arbitrum`

1. **`cli.main`** parses the arguments and calls `engine.analyze(...)`.
2. **`engine.analyze`** checks the file exists, finds `solc` (`solc.find_solc`), and calls `Slither("OmniStake.sol", solc=...)`.
3. **Slither/crytic-compile** runs solc, builds the AST, and lowers it to SlithIR.
4. The engine wraps the result in a **`Context`** and runs each rule. Take **`Prevrandao`**:
   - `ctx.nodes()` reaches the node for line 120: `uint256 winner = uint256(keccak256(abi.encode(block.prevrandao, ...)))`.
   - `global_read(node, {"block.prevrandao", "block.difficulty"}, {"prevrandao", "difficulty"})` finds
     `block.prevrandao` in `node.solidity_variables_read`.
   - The rule yields `ctx.site("prevrandao", contract, function, node, "reads block.prevrandao")`, which records file,
     line 120 and the source snippet.
5. The engine checks the dedupe key `(rule, file, line, contract, variant)`. It's new, so it builds a `Finding` with the
   title, description and fix from `divergences.toml`.
6. For each chain it calls `rule.assess(...)`, which becomes `kb.assess_rule("prevrandao", chain)`:
   - `ethereum` has its own entry: **medium**, "RANDAO output... proposer can bias it".
   - `arbitrum` has its own entry: **high**, "always returns the constant 1."
7. The finding's severity is the worst of those, **high**, which is above `--min-severity`, so it's kept.
8. Findings are sorted and handed to `render_text`, which groups chains and prints them.

Every finding follows this same path. Only step 4 differs between rules.

---

## Part 8: How the project is tested

**44 tests, run with `python -m pytest -q`.** They compile real Solidity with real solc. Nothing is mocked, so a
passing test means the whole pipeline works.

1. **One fixture contract per rule** (`tests/contracts/*.sol`). Each contains the bad pattern in several forms
   (Solidity *and* assembly where possible). The tests assert exact counts, variants and per-chain severities.
2. **Negative controls.** `Clean.sol` is full of patterns that *look* risky but aren't, and must produce zero findings.
   Several fixtures also contain correct code that must not be flagged (`GoodPermit`, `address(this).code.length`,
   the `SENTINEL` constant). This guards against **false positives**, which make people stop trusting a tool.
3. **Unit tests** for small pieces: the bytecode scanner, knowledge-base validation, lookup precedence, grouping.
4. **End-to-end CLI tests**: every output format, exit codes, error handling.

**A real bug the tests caught.** Running the CLI end to end showed that `scan does/not/exist.sol`, an empty folder,
and a folder containing a broken contract all **exited with code 0**. In CI, a typo in a path would have made the
security check "pass" while scanning nothing. The engine now raises clear errors, the CLI exits with `2`, and
`test_cli_and_errors.py` keeps it that way. Mention this in interviews: it shows you test the *tool's* failure modes,
not just the happy path.

---

## Part 9: Explaining ChainDrift in an interview

### 30-second pitch
> "Teams deploy the same Solidity contract to many EVM chains, but chains differ in subtle ways. `block.number`
> means something else on Arbitrum, `prevrandao` is a constant on most L2s, `.transfer()` can lock funds on ZKsync,
> and missing precompiles fail silently. I built ChainDrift, a static analyzer on top of Slither's IR, that finds
> those lines and tells you, chain by chain, what changes and how to fix it. Chain behaviour lives in a confidence-rated
> TOML knowledge base, separate from detection logic, and it outputs SARIF so it plugs straight into GitHub code
> scanning."

### Likely questions, and good answers

**Why not just write Slither detectors?**
Slither detectors give one severity per finding. Here the *same* line is fine on one chain and critical on another,
so I separated *detection* (where a construct appears) from *assessment* (per-chain behaviour), which needs its own
data model and output format (the findings × chains matrix).

**Why put chain facts in TOML instead of code?**
They change every few months when chains upgrade. Data in a validated TOML file can be updated by anyone, reviewed in
a pull request, and carries a confidence level and a source. The detection code stays stable.

**How do you avoid false positives?**
Precise patterns (only constants that are actually *called* count as precompile calls), explicit look-alike exclusions
(`address(this).code.length`), negative-control fixtures in the test suite, and a `check` severity instead of guessing
when the data is unsure.

**How do you handle inline assembly?**
Slither lowers Yul into the same IR as Solidity. Yul builtins appear as `SolidityCall`s, so each rule checks both
forms through one helper.

**What's the hardest part?**
Two things. (1) Constant tracking: following `address(100)` through type conversions to an interface call.
(2) Keeping the knowledge base honest: every claim has a confidence level, and unknowns are surfaced as "verify".

**Why scan bytecode as well as source?**
Because the *compiler* introduces some dependencies. Solidity 0.8.20+ emits `PUSH0` by default, which no source code
mentions. I wrote a small disassembler that skips PUSH data and strips solc's metadata. As a check, compiling with
`--evm-version paris` makes the PUSH0 finding disappear.

**What are the limitations?**
It's static. Constant tracking is within one function. The knowledge base is a snapshot that needs maintenance. And
for ZKsync it models EVM-level differences, not every zksolc constraint.

**What would you build next?**
Scanning deployed contracts by address (verified source from block explorers), running it on real multi-chain
protocols and publishing the findings, and a `--diff` mode: "what breaks if I add chain X?"

---

## Part 10: Exercises to deepen your understanding

Do these in order. Each one forces you to touch a different part of the code.

1. **Run a single rule.** `python -m chaindrift scan tests/contracts/Prevrandao.sol --rules prevrandao --chains arbitrum`
   and match each line of output to the code in Part 7.
2. **Change a fact.** In `divergences.toml`, change Scroll's `prevrandao` note, re-run, and see it in the output.
   Then set a severity to `"catastrophic"` and watch the validator reject it.
3. **Add a chain.** Add `[chains.mantle]` to `chains.toml` (look up its chain id and block time). Run `chaindrift chains`.
4. **Add an address.** Add a mainnet contract you know to `addresses.toml`, use it in a test contract, and check it's flagged.
5. **Explore SlithIR yourself.** In Python:
   ```python
   from slither import Slither
   sl = Slither("tests/contracts/HardcodedGas.sol", solc="<path from chaindrift.solc.find_solc()>")
   for c in sl.contracts:
       for f in c.functions:
           for n in f.nodes:
               print(n, [str(ir) for ir in n.irs])
   ```
6. **Write a new rule**, for example flagging `block.coinbase` (it's the sequencer or a fee vault on L2s):
   copy `GasPrice` in `rules/environment.py`, add an entry in `divergences.toml`, register it in `rules/__init__.py`,
   add a fixture plus a test, and run `pytest`.
7. **Try `--solc-args "--evm-version paris"`** on `tests/contracts/Opcodes.sol` and explain why it fails (`tload`/`tstore`
   don't exist before Cancun), while `Selfdestruct.sol` loses its `PUSH0` finding.
8. **Scan real code.** Clone an open-source multi-chain protocol and scan it. Check each finding by hand: real issue,
   intended behaviour, or false positive? This is the best preparation for interviews.

---

## Glossary

| Term | Meaning |
|---|---|
| **Account abstraction** | accounts whose validation rules are code (smart wallets) |
| **AST** | Abstract Syntax Tree, the compiler's tree-shaped view of source code |
| **Bytecode** | the compiled program the EVM runs: a sequence of opcodes |
| **CBOR metadata** | data solc appends to bytecode (source hash, compiler version); not executable |
| **Chain ID** | a number identifying a chain (1 = Ethereum, 42161 = Arbitrum One, 8453 = Base...) |
| **CREATE2** | a deployment opcode whose resulting address can be predicted in advance |
| **crytic-compile** | the library that runs compilers and frameworks for Slither |
| **Domain separator** | the EIP-712 value binding a signature to one contract on one chain |
| **EIP** | Ethereum Improvement Proposal |
| **EOA** | Externally Owned Account, a key-controlled wallet |
| **EraVM / zksolc** | ZKsync's own virtual machine and Solidity compiler |
| **EVM** | Ethereum Virtual Machine |
| **False positive** | a tool reports a problem that isn't real |
| **Gas stipend** | the fixed 2300 gas forwarded by `transfer`/`send` |
| **Hard fork** | a network upgrade that changes the rules (Shanghai, Cancun...) |
| **IR** | Intermediate Representation, a simplified form of code that is easier to analyse |
| **L1 / L2** | the base chain (Ethereum) / chains built on top of it |
| **L1 data fee** | the extra rollup fee for posting transaction data to Ethereum |
| **Opcode** | a single EVM instruction (one byte) |
| **Optimistic rollup** | an L2 that assumes correctness, with a fraud-proof window |
| **OP Stack** | the shared software behind OP Mainnet and Base |
| **Precompile** | a built-in contract at a tiny address, implemented natively |
| **PUSH0** | an opcode added in Shanghai; emitted by solc ≥ 0.8.20 by default |
| **RANDAO / prevrandao** | Ethereum's validator-generated randomness value |
| **Replay attack** | reusing a valid signature somewhere it wasn't intended |
| **SARIF** | the standard JSON format for static-analysis results (used by GitHub) |
| **Sequencer** | the operator that orders transactions on an L2 |
| **Site** | (ChainDrift) a chain-independent code location where a rule matched |
| **Slither / SlithIR** | Trail of Bits' Solidity analysis framework / its intermediate representation |
| **solc / solc-select** | the Solidity compiler / a tool to install and switch its versions |
| **Static analysis** | analysing code without running it |
| **TOML** | a simple, human-friendly config file format |
| **Transient storage** | storage that clears after each transaction (`TLOAD`/`TSTORE`, EIP-1153) |
| **Yul** | the low-level language used in Solidity `assembly { }` blocks |
| **ZK rollup** | an L2 that proves correctness with zero-knowledge proofs |
