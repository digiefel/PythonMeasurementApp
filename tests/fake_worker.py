"""Hardware-free instrument double, run through the production executor."""
import json
import os
import sys
import threading
import time

from instrumentio import bridge_worker


class FakeSession:
    def __init__(self, address):
        self.options = json.loads(address)
        self.interrupted = threading.Event()
        self.wgfmu = self
        self.record("connect")
        time.sleep(self.options.get("connect_delay", 0))
        if self.options.get("connect_error"):
            raise RuntimeError("Simulated vendor load failure")

    def record(self, value):
        if path := self.options.get("record"):
            with open(path, "a") as output:
                output.write(json.dumps(value) + "\n")

    def echo(self, value):
        self.record(value)
        return value

    def slow(self, seconds):
        self.record("slow_started")
        if self.options.get("interruptible"):
            if self.interrupted.wait(seconds):
                self.record("io_returned_after_interrupt")
                raise RuntimeError("Simulated VISA I/O cancellation")
        else:
            time.sleep(seconds)
        self.record("slow_finished")

    def interrupt_io(self):
        if self.options.get("interruptible"):
            self.interrupted.set()

    def fail(self):
        raise RuntimeError("Simulated instrument failure")

    def crash(self):
        os._exit(23)

    def corrupt(self):
        sys.__stdout__.write("not-json\n")
        sys.__stdout__.flush()
        time.sleep(10)

    def noisy(self):
        print("Vendor diagnostic: åäö")
        return "åäö"

    def samples(self, count, callback):
        return [callback(i) for i in range(count)]

    def stream_cv_sweep(self, channel, mode, rng, count, callback):
        for index in range(count):
            callback(index, 1., 2., 3., 4., 5, 6)

    def close(self):
        self.record("close")
        time.sleep(self.options.get("close_delay", 0))
        if self.options.get("close_error"):
            raise RuntimeError("Simulated cleanup failure")


bridge_worker.configure_logging = lambda: None
bridge_worker.main(FakeSession)
