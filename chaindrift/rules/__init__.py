from .addresses import KnownAddress, Precompile
from .environment import BlockNumber, ChainGatedLogic, EoaCheck, GasPrice, Prevrandao
from .execution import Create2Address, HardcodedGas, OpcodeSupport, Selfdestruct, TransferSend
from .signatures import ChainIdReplay

ALL_RULES = [
    BlockNumber(),
    Prevrandao(),
    TransferSend(),
    Create2Address(),
    Selfdestruct(),
    HardcodedGas(),
    GasPrice(),
    EoaCheck(),
    ChainIdReplay(),
    ChainGatedLogic(),
    Precompile(),
    KnownAddress(),
    OpcodeSupport(),
]

RULES_BY_ID = {r.id: r for r in ALL_RULES}
