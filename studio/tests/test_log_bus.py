"""Pure-logic tests for studio/log_bus.py -- the real, central log stream
every controller/handler feeds and studio.overlays.LogsConsole reads.

No Qt import: runs in CI's light `test` group.
"""
import logging

from studio import log_bus
from studio.log_bus import (
    LogBus, StudioLogHandler, install_handler, emit_prefixed, short_source,
)


# ── LogBus mechanics ─────────────────────────────────────────────────────────
def test_emit_appends_and_assigns_increasing_seq():
    bus = LogBus()
    r1 = bus.emit(log_bus.INFO, "first", source="a")
    r2 = bus.emit(log_bus.INFO, "second", source="a")
    assert r2.seq == r1.seq + 1
    assert [r.message for r in bus.snapshot()] == ["first", "second"]


def test_convenience_level_methods_set_the_right_level():
    bus = LogBus()
    assert bus.debug("x").level == log_bus.DEBUG
    assert bus.info("x").level == log_bus.INFO
    assert bus.warning("x").level == log_bus.WARNING
    assert bus.error("x").level == log_bus.ERROR
    assert bus.critical("x").level == log_bus.CRITICAL


def test_level_name_reflects_canonical_names():
    bus = LogBus()
    assert bus.warning("careful").level_name == "WARNING"


def test_level_name_floors_a_custom_in_between_level():
    assert log_bus.level_name(25) == "INFO"
    assert log_bus.level_name(5) == "DEBUG"


def test_records_carry_a_source_tag_and_timestamp():
    bus = LogBus()
    before = __import__("time").time()
    rec = bus.info("hello", source="segment")
    assert rec.source == "segment"
    assert rec.ts >= before


def test_maxlen_evicts_oldest():
    bus = LogBus(maxlen=3)
    for i in range(5):
        bus.info(str(i))
    assert [r.message for r in bus.snapshot()] == ["2", "3", "4"]


def test_subscribe_backlog_then_receives_only_future_records():
    bus = LogBus()
    bus.info("before")
    received = []
    backlog, unsubscribe = bus.subscribe(received.append)
    assert [r.message for r in backlog] == ["before"]
    bus.info("after")
    assert [r.message for r in received] == ["after"]
    unsubscribe()
    bus.info("ignored")
    assert [r.message for r in received] == ["after"]


def test_unsubscribe_is_safe_to_call_twice():
    bus = LogBus()
    _, unsubscribe = bus.subscribe(lambda rec: None)
    unsubscribe()
    unsubscribe()  # must not raise


def test_multiple_subscribers_all_receive_a_record():
    bus = LogBus()
    a, b = [], []
    bus.subscribe(a.append)
    bus.subscribe(b.append)
    bus.info("x")
    assert len(a) == 1 and len(b) == 1


def test_clear_empties_the_buffer_but_seq_keeps_advancing():
    bus = LogBus()
    bus.info("one")
    bus.clear()
    assert bus.snapshot() == []
    rec = bus.info("two")
    assert rec.seq == 2  # not reset -- always uniquely orderable


def test_len_reflects_current_buffer_size():
    bus = LogBus()
    assert len(bus) == 0
    bus.info("x")
    assert len(bus) == 1


def test_emit_is_safe_from_multiple_threads():
    import threading

    bus = LogBus()

    def worker(n):
        for i in range(50):
            bus.info(f"{n}-{i}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(bus.snapshot()) == 400
    seqs = [r.seq for r in bus.snapshot()]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 400  # every seq unique -- no lost update


# ── emit_prefixed: the ML core's existing on_log(msg) convention ───────────
def test_emit_prefixed_parses_error_warn_hint_info_and_defaults_to_info():
    bus = LogBus()
    r = emit_prefixed(bus, "[ERROR] boom", source="segment")
    assert (r.level, r.message) == (log_bus.ERROR, "boom")
    r = emit_prefixed(bus, "[WARN] careful", source="segment")
    assert (r.level, r.message) == (log_bus.WARNING, "careful")
    r = emit_prefixed(bus, "[HINT] try this", source="segment")
    assert (r.level, r.message) == (log_bus.INFO, "try this")
    r = emit_prefixed(bus, "[INFO] 3-D result: 12 cells", source="segment")
    assert (r.level, r.message) == (log_bus.INFO, "3-D result: 12 cells")
    r = emit_prefixed(bus, "✓ 247 cells", source="segment")
    assert (r.level, r.message) == (log_bus.INFO, "✓ 247 cells")


def test_emit_prefixed_strips_leading_whitespace_before_matching():
    bus = LogBus()
    r = emit_prefixed(bus, "  [ERROR] nested benchmark failure", source="segment")
    assert (r.level, r.message) == (log_bus.ERROR, "nested benchmark failure")


def test_emit_prefixed_preserves_a_multiline_traceback_message():
    bus = LogBus()
    r = emit_prefixed(bus, "[ERROR] boom\nTraceback (most recent call last):\n  ...",
                       source="segment")
    assert r.message.startswith("boom\nTraceback")


# ── short_source ─────────────────────────────────────────────────────────────
def test_short_source_strips_the_studio_prefix():
    assert short_source("studio.segment") == "segment"
    assert short_source("segment") == "segment"


# ── StudioLogHandler: the real stdlib logging bridge ────────────────────────
def test_studio_log_handler_bridges_a_real_logger_record():
    bus = LogBus()
    logger = logging.getLogger("studio.log_bus.tests.handler")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = StudioLogHandler(bus)
    logger.addHandler(handler)
    try:
        logger.warning("careful: %s", "disk almost full")
    finally:
        logger.removeHandler(handler)
    [rec] = bus.snapshot()
    assert rec.level == logging.WARNING
    assert rec.message == "careful: disk almost full"
    assert rec.source == "studio.log_bus.tests.handler"


def test_studio_log_handler_formats_exception_info():
    bus = LogBus()
    logger = logging.getLogger("studio.log_bus.tests.handler.exc")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = StudioLogHandler(bus)
    logger.addHandler(handler)
    try:
        try:
            raise ValueError("kaboom")
        except ValueError:
            logger.critical("unhandled", exc_info=True)
    finally:
        logger.removeHandler(handler)
    [rec] = bus.snapshot()
    assert rec.level == logging.CRITICAL
    assert "unhandled" in rec.message
    assert "ValueError: kaboom" in rec.message


def test_studio_log_handler_never_raises_on_a_bad_record(monkeypatch):
    bus = LogBus()
    handler = StudioLogHandler(bus)

    def _boom(record):
        raise ValueError("formatting exploded")

    monkeypatch.setattr(handler, "format", _boom)
    monkeypatch.setattr(handler, "handleError", lambda record: None)
    logger = logging.getLogger("studio.log_bus.tests.bad")
    record = logger.makeRecord(logger.name, logging.INFO, __file__, 1, "x", (), None)
    handler.emit(record)  # must not raise -- handleError absorbs it
    assert bus.snapshot() == []


# ── install_handler ──────────────────────────────────────────────────────────
def test_install_handler_is_idempotent_for_the_same_bus():
    bus = LogBus()
    logger = logging.getLogger("studio.log_bus.tests.install")
    logger.handlers.clear()
    logger.setLevel(logging.WARNING)
    install_handler(bus, logger=logger)
    install_handler(bus, logger=logger)
    handler_count = sum(isinstance(h, StudioLogHandler) for h in logger.handlers)
    assert handler_count == 1


def test_install_handler_raises_a_less_verbose_level_to_info():
    bus = LogBus()
    logger = logging.getLogger("studio.log_bus.tests.install_level")
    logger.handlers.clear()
    logger.setLevel(logging.WARNING)
    install_handler(bus, logger=logger)
    assert logger.level == logging.INFO


def test_install_handler_does_not_lower_an_already_more_verbose_level():
    bus = LogBus()
    logger = logging.getLogger("studio.log_bus.tests.install_verbose")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    install_handler(bus, logger=logger)
    assert logger.level == logging.DEBUG


def test_install_handler_makes_the_studio_namespace_verbose():
    bus = LogBus()
    logger = logging.getLogger("studio.log_bus.tests.install_ns")
    logger.handlers.clear()
    install_handler(bus, logger=logger)
    assert logging.getLogger("studio").level == logging.DEBUG


def test_install_handler_end_to_end_through_a_real_logger_call():
    bus = LogBus()
    logger = logging.getLogger("studio.log_bus.tests.install_e2e")
    logger.handlers.clear()
    logger.propagate = False
    install_handler(bus, logger=logger)
    logger.info("real end to end line")
    assert any(r.message == "real end to end line" for r in bus.snapshot())


def test_get_log_bus_returns_a_process_wide_singleton():
    assert log_bus.get_log_bus() is log_bus.get_log_bus()


def test_install_handler_honors_an_explicit_but_still_empty_bus():
    # Regression: LogBus defines __len__ for len(bus), which means a
    # freshly constructed (empty) bus is falsy under Python's truthiness
    # rules -- `bus or get_log_bus()` would have silently swapped a real,
    # intentionally-passed-in empty test bus for the global singleton.
    empty_bus = LogBus()
    other_bus = log_bus.get_log_bus()
    logger = logging.getLogger("studio.log_bus.tests.explicit_empty_bus")
    logger.handlers.clear()
    logger.propagate = False
    returned = install_handler(empty_bus, logger=logger)
    assert returned is empty_bus
    logger.info("goes to the explicit bus")
    assert any(r.message == "goes to the explicit bus" for r in empty_bus.snapshot())
    assert not any(r.message == "goes to the explicit bus" for r in other_bus.snapshot())
