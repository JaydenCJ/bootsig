"""bootsig — statistical significance testing for eval runs.

Give it two JSONL result files and it answers the only question that
matters: *is this difference real, or is it noise?* Bootstrap confidence
intervals, paired/unpaired permutation tests, an exact McNemar test for
pass/fail metrics, and minimum-detectable-effect estimates — standard
library only, fully offline, deterministic under a seed.

The CLI (``bootsig compare / inspect / mde``) and this Python API expose
the same machinery; everything the CLI prints comes from these functions.
"""

from .bootstrap import BootstrapCI, bootstrap_mean, paired_bootstrap, unpaired_bootstrap
from .compare import Comparison, McNemarResult, RunStats, compare_files
from .errors import BootsigError, DataError, PairingError, UsageError
from .loader import Record, Run, load_run
from .pairing import PairedRuns, pair_runs
from .permutation import PermutationResult, paired_permutation_test, unpaired_permutation_test
from .power import mde, required_n

__version__ = "0.1.0"

__all__ = [
    "BootsigError",
    "BootstrapCI",
    "Comparison",
    "DataError",
    "McNemarResult",
    "PairedRuns",
    "PairingError",
    "PermutationResult",
    "Record",
    "Run",
    "RunStats",
    "UsageError",
    "__version__",
    "bootstrap_mean",
    "compare_files",
    "load_run",
    "mde",
    "pair_runs",
    "paired_bootstrap",
    "paired_permutation_test",
    "required_n",
    "unpaired_bootstrap",
    "unpaired_permutation_test",
]
