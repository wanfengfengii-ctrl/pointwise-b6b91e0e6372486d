"""Source readings and hand-calculated stop review examples."""
import json
import sqlite3
from contextlib import closing

from issue.codec import decode_piece
from issue.receipts import issue
from tests.fixtures import gap, prepare_station, reading


SOURCES = {
    "steady": {
        "rows": (reading(-4, 12),),
        "affine": [["-4", "12", "0", "5"]],
    },
    "missing": {
        "rows": (reading(-4, "1/2"), gap("1/2", "3/4"), reading("3/4", 12)),
        "affine": [["-4", "1/2", "0", "5"], ["3/4", "12", "0", "5"]],
    },
    "jump": {
        "rows": (reading(-4, 1), reading(1, 12, 6)),
        "affine": [["-4", "1", "0", "5"], ["1", "12", "0", "6"]],
    },
}


def _case(name, left, right, window, result, right_source="steady"):
    lag_min, lag_max = window
    size, lags = result
    return {
        "name": name,
        "batch_id": "coil-stop-01",
        "left": {"source": "steady", "commands": left},
        "right": {"source": right_source, "commands": right},
        "request": {"threshold": 5, "dwell": 1, "tolerance": 1, "lag_min": lag_min, "lag_max": lag_max},
        "expected": {"max_pairs": size, "optimal_lags": lags},
    }


CASES = (
    _case("shared-command", (("a0", 0), ("a1", 1)), (("b0", 0),), (0, 0), (1, ((0, 0),))),
    _case("empty-log", (("a0", 0), ("a1", 1)), (), (0, 0), (0, ((0, 0),))),
    _case("missing-evidence", (("a0", 0), ("a1", 1)), (("b0", 0),), (0, 0), (0, ((0, 0),)), "missing"),
    _case("touching-at-zero", (("a0", 0), ("a1", 10)), (("b0", 1), ("b1", 9)), (-1, 1), (2, ((0, 0),))),
    _case("split-optimum", (("a0", 0),), (("b0", -3), ("b1", 0)), (1, 2), (1, ((1, 1), (2, 2)))),
    _case("excluded-right-end", (("a0", 0), ("a1", 1)), (("b0", 0), ("b1", 1)), (0, 0), (1, ((0, 0),)), "jump"),
)


def main():
    """Check that the sample readings produce the stated V1 evidence."""
    for name, source in SOURCES.items():
        with closing(sqlite3.connect(":memory:")) as db:
            revision = prepare_station(db, "A", source["rows"])
            receipt = issue(db, "A", revision.revision_id, 5)
            evidence = decode_piece(receipt.piece_bytes).body["affine"]
        if evidence != source["affine"]:
            raise AssertionError(f"unexpected source evidence for {name}: {evidence!r}")
        print(json.dumps({"source": name, "affine": evidence}, sort_keys=True))


if __name__ == "__main__":
    main()
