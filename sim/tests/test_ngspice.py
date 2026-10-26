"""Reading a deck's output, finding things in a netlist, and saying out loud
which deck is running -- all without ngspice.

These are the parts that decide what a simulation *said*. A parser that drops a
result, or reads one name as another, turns a correct circuit into a failing
test or a broken one into a passing test, and neither needs the simulator to
happen.
"""

from __future__ import annotations

import logging
import shutil

import pytest

import ngspice

NETLIST = """\
* two cells, declared out of order on purpose
.lib /pdk/sky130A/libs.tech/combined/sky130.lib.spice tt
.subckt array top bot1 bot0
C0 top bot0 1f
C1 top bot1 2f
.ends
.subckt array_dummy top
C0 top 0 1f
.ends
"""


def test_every_draw_of_a_repeated_measurement_is_kept_in_order():
    """A loop prints the same name each pass; each pass is one draw."""
    out = "c = 1.0e-15\nc = 2.0e-15\nc = 3.0e-15\n"
    assert ngspice.results(out) == {"c": [1.0e-15, 2.0e-15, 3.0e-15]}


def test_names_are_matched_whole():
    """`vtop` and `top` are different measurements, not one name's suffix."""
    out = "vtop = 1\ntop = 2\n"
    assert ngspice.results(out) == {"vtop": [1.0], "top": [2.0]}


def test_measure_trailers_do_not_hide_the_value():
    """`meas` prints a position after the value; the value is what is read."""
    out = "tmax = 4.5e-09 at= 3.2e-09\n"
    assert ngspice.results(out)["tmax"] == [4.5e-09]


def test_signed_and_exponent_forms_parse():
    out = "a = -1.5e-3\nb = +2E+6\nc = 7\n"
    assert ngspice.results(out) == {"a": [-1.5e-3], "b": [2e6], "c": [7.0]}


def test_chatter_is_not_a_result():
    """A result starts its line. ngspice's own lines can contain `x = n`
    mid-sentence, and reading those would add a measurement nobody asked for."""
    out = "Circuit: * deck\nWarning: something\nDoing analysis at TEMP = 27.000000\n"
    assert ngspice.results(out) == {}


def test_the_library_is_found_without_its_corner():
    assert ngspice.library(NETLIST).endswith("sky130.lib.spice")


def test_a_netlist_with_no_library_is_an_error():
    with pytest.raises(ngspice.DeckError):
        ngspice.library(".subckt x a\n.ends\n")


def test_a_subcircuit_is_found_by_its_whole_name():
    """`array` must not match `array_dummy`, or the wrong cell is simulated."""
    cell = ngspice.subckt(NETLIST, "array")
    assert "bot1" in cell and "array_dummy" not in cell


def test_ports_come_out_in_declared_order():
    """Wiring is by name; this is the order a caller must follow."""
    assert ngspice.ports(ngspice.subckt(NETLIST, "array")) == ["top", "bot1", "bot0"]


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")
def test_a_real_deck_round_trips(tmp_path):
    """One trivial circuit through the real simulator: a divider halves."""
    deck = "\n".join(
        [
            "* divider",
            "V1 in 0 2",
            "R1 in mid 1k",
            "R2 mid 0 1k",
            ".control",
            "op",
            "let vmid = v(mid)",
            "print vmid",
            ".endc",
            ".end",
        ]
    )
    assert ngspice.run(deck, tmp_path)["vmid"] == [pytest.approx(1.0)]


#: A deck whose answer nobody cares about: these tests are about what a run
#: says while it works, not what it found.
DIVIDER = "\n".join(
    [
        "* divider",
        "V1 in 0 2",
        "R1 in 0 1k",
        ".control",
        "op",
        "let vin = v(in)",
        "print vin",
        ".endc",
        ".end",
    ]
)


def test_a_deck_is_named_by_its_own_first_line():
    """What the heartbeat calls a simulation while it runs. The marker and the
    space after it are ngspice's comment syntax, not part of the name."""
    assert ngspice.title("* bench: one strobe\nV1 a 0 1\n") == "bench: one strobe"


def test_a_deck_with_nothing_but_a_title_still_has_one():
    assert ngspice.title("* nothing else") == "nothing else"


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")
def test_a_run_says_which_deck_it_is_in_before_the_answer_arrives(tmp_path, caplog):
    """The heartbeat's whole purpose is the record that survives a run which
    never finishes, so the start of a simulation is on the record before the
    simulator is asked anything."""
    with caplog.at_level(logging.INFO, logger=ngspice.__name__):
        ngspice.run(DIVIDER, tmp_path)
    started, finished = [r.getMessage() for r in caplog.records]
    assert ngspice.title(DIVIDER) in started and ngspice.title(DIVIDER) in finished
    assert "start" in started and "done" in finished


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")
def test_a_deck_that_outlasts_its_bound_is_a_stall_and_keeps_its_deck(tmp_path, monkeypatch):
    """A wedged solver returns nothing, ever. Bounding one run turns that from
    a job that dies of its own time limit with no idea which circuit did it
    into a named failure holding the text that caused it."""
    monkeypatch.setenv(ngspice.TIMEOUT_ENV, "0.001")
    with pytest.raises(ngspice.DeckError, match="stalled"):
        ngspice.run(DIVIDER, tmp_path)
    assert list(tmp_path.glob("*.spice")), "the deck that stalled was thrown away"
