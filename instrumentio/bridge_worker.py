"""Single-owner instrument executor. The input thread never calls a driver."""

from __future__ import annotations

import json
import logging
import os
import queue
import struct
import sys
import threading
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
        # Bound cleanup after either a command failure or a parent crash, even
        # when the native driver will not return to the executor.
        cancelled.wait()
        if not finished.wait(STOP_TIMEOUT_S):
            logger.critical("Instrument stop timed out; output state could not be confirmed")
            os._exit(1)

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
            if target not in ("", "wgfmu") or method.startswith("_") or method == "close":
                raise ValueError("Invalid instrument method")
            receiver = session if not target else getattr(session, target)
            result = getattr(receiver, method)(
                *(unpack(value) for value in args),
                **{key: unpack(value) for key, value in kwargs.items()},
            )
            if cancelled.is_set():
                raise InstrumentCancelled()
            emit(["result", result])
    except InstrumentCancelled:
        pass
    except Exception:
        details = traceback.format_exc()
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
                terminal = ["error", "Instrument shutdown failed; output state could not be confirmed.", details]
        try:
            emit(terminal)
        except (OSError, ValueError):
            logger.exception("Could not deliver instrument shutdown result")
        finished.set()


if __name__ == "__main__":
    main()
