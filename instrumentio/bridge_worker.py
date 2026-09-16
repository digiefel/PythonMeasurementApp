"""Single-owner executor; cancellation may only terminate pending host VISA I/O."""

from __future__ import annotations

import json
import logging
import os
import queue
import struct
import sys
import threading
import time
import traceback

from app_logging import configure_logging
from .protocol import InstrumentCancelled, STOP_TIMEOUT_S

logger = logging.getLogger(__name__)


def main(session_factory=None):
    configure_logging()
    # Python prints and driver diagnostics must not share the protocol stream.
    protocol_out, sys.stdout = sys.stdout, sys.stderr
    inbox = queue.SimpleQueue()
    cancelled = threading.Event()
    finished = threading.Event()
    session = None
    operation_active = False
    io_handoff = threading.Lock()
    terminal = ["stopped"]

    def emit(message):
        protocol_out.write(json.dumps(message, separators=(",", ":")) + "\n")
        protocol_out.flush()

    def read_commands():
        try:
            for line in sys.stdin:
                message = json.loads(line)
                if message == ["cancel"]:
                    break
                inbox.put(message)
        except Exception as exc:
            logger.exception("Invalid instrument command stream")
            inbox.put(exc)
        finally:
            cancelled.set()
            inbox.put(None)

    def watch_shutdown():
        cancelled.wait()
        deadline = time.monotonic() + STOP_TIMEOUT_S
        interrupt_failed = False
        while not finished.is_set():
            with io_handoff:
                if operation_active and session is not None and not interrupt_failed:
                    try:
                        session.interrupt_io()
                    except Exception:
                        # Never clear or close here: the native call still owns
                        # the session. The bounded process fallback handles it.
                        logger.exception("Could not interrupt pending instrument I/O")
                        interrupt_failed = True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.critical("Instrument worker did not complete cancellation and device clear within %.1fs",
                                STOP_TIMEOUT_S)
                os._exit(1)
            # Termination is a host-I/O request, not a retried instrument command.
            # Repeat until the owner returns: cancellation can arrive immediately
            # before native I/O starts or between calls inside a driver function.
            finished.wait(min(0.05, remaining))

    def receive():
        message = inbox.get()
        if isinstance(message, Exception):
            raise message
        if cancelled.is_set():
            raise InstrumentCancelled()
        if not isinstance(message, list) or not message:
            raise ValueError("Invalid command envelope")
        return message

    def unpack(value):
        if not isinstance(value, dict) or set(value) != {"__callback__"}:
            return value
        index = value["__callback__"]

        def callback(*args, **kwargs):
            if cancelled.is_set():
                raise InstrumentCancelled()
            emit(["callback", index, args, kwargs])
            reply = receive()
            if len(reply) != 2 or reply[0] != "return":
                raise ValueError("Expected callback acknowledgement")
            return reply[1]

        return callback

    threading.Thread(target=read_commands, daemon=True).start()
    threading.Thread(target=watch_shutdown, daemon=True).start()
    try:
        if session_factory is None:
            if struct.calcsize("P") != 4:
                raise RuntimeError("The instrument interpreter must be 32-bit")
            from instrumentio.sessions import B1500Session
            session_factory = B1500Session
        message = receive()
        if len(message) != 2 or message[0] != "connect":
            raise ValueError("Expected connection request")
        session = session_factory(message[1])
        if cancelled.is_set():
            raise InstrumentCancelled()
        emit(["result", {"pid": os.getpid(), "python_executable": sys.executable,
                         "session_initialized": True}])
        while True:
            message = receive()
            if len(message) != 5 or message[0] != "call":
                raise ValueError("Expected instrument call")
            _, target, method, args, kwargs = message
            if target not in ("", "wgfmu") or method.startswith("_") or method in ("close", "interrupt_io"):
                raise ValueError("Invalid instrument method")
            receiver = session if not target else getattr(session, target)
            with io_handoff:
                if cancelled.is_set():
                    raise InstrumentCancelled()
                operation_active = target == ""  # WGFMU has its own opaque driver session.
            try:
                result = getattr(receiver, method)(
                    *(unpack(value) for value in args),
                    **{key: unpack(value) for key, value in kwargs.items()},
                )
            finally:
                # Wait for any in-flight viTerminate to return before entering
                # cleanup. No terminate can touch this session after this point.
                with io_handoff:
                    operation_active = False
            if cancelled.is_set():
                raise InstrumentCancelled()
            emit(["result", result])
    except InstrumentCancelled:
        pass
    except Exception:
        details = traceback.format_exc()
        if cancelled.is_set():
            logger.info("Instrument call ended during cancellation:\n%s", details)
        else:
            logger.error("Instrument executor failed:\n%s", details)
            terminal = ["error", "Instrument operation failed. See the application log for details.", details]
    finally:
        cancelled.set()
        if session is not None:
            try:
                session.close()
            except Exception:
                details = traceback.format_exc()
                logger.error("Instrument cleanup failed:\n%s", details)
                terminal = ["error", "Instrument cleanup failed. See the application log for the failed operation.", details]
        try:
            emit(terminal)
        except (OSError, ValueError):
            logger.exception("Could not deliver instrument shutdown result")
        finished.set()


if __name__ == "__main__":
    main()
