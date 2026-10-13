"""Real QtCore event loop and worker threads; no sockets or GUI plugins."""
import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication, QTimer, QThread
from wordloom.jobs import Job
from wordloom.providers import ApiError


class JobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def until(self, condition, timeout=2):
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.002)
        self.app.processEvents()
        self.assertTrue(condition(), "Qt signal deadline exceeded")

    def test_progress_and_completion_in_gui_thread(self):
        progress, results, threads = [], [], []
        def work(token, emit):
            self.assertNotEqual(QThread.currentThread(), self.app.thread())
            emit("first")
            emit("second")
            return "complete"
        job = Job(work, 2)
        job.progress.connect(lambda value: (progress.append(value), threads.append(QThread.currentThread())))
        job.success.connect(results.append)
        job.start()
        self.until(lambda: bool(results))
        self.assertEqual(progress, ["first", "second"])
        self.assertEqual(results, ["complete"])
        self.assertTrue(all(t == self.app.thread() for t in threads))

    def test_cancel_is_immediate_and_drops_late_results(self):
        gate = threading.Event()
        results, failures, progress = [], [], []
        def work(token, emit):
            gate.wait(1)
            emit("stale text")
            return "stale result"
        job = Job(work, 2)
        job.success.connect(results.append)
        job.progress.connect(progress.append)
        job.failure.connect(lambda code, message: failures.append(code))
        job.start()
        job.cancel()
        self.assertEqual(failures, ["cancelled"])
        gate.set()
        job.thread.join(1)
        self.app.processEvents()
        self.assertEqual(results, [])
        self.assertEqual(progress, [])
        self.assertEqual(failures, ["cancelled"])

    def test_request_does_not_block_event_loop(self):
        finished, ticks = [], []
        def work(token, emit):
            time.sleep(0.1)
            return "ok"
        job = Job(work, 2)
        job.success.connect(finished.append)
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        job.start()
        self.until(lambda: bool(finished))
        timer.stop()
        self.assertGreater(len(ticks), 3)

    def test_ui_deadline_ignores_blocked_worker(self):
        failures, results = [], []
        gate = threading.Event()
        job = Job(lambda token, emit: gate.wait(1), 0.01)
        job.failure.connect(lambda code, message: failures.append(code))
        job.success.connect(results.append)
        job.start()
        self.until(lambda: bool(failures))
        self.assertEqual(failures, ["timeout"])
        gate.set()
        job.thread.join(1)
        self.app.processEvents()
        self.assertEqual(results, [])

    def test_errors_are_safe_and_have_no_automatic_retry(self):
        calls, failures = [], []
        def work(token, emit):
            calls.append(1)
            raise ValueError("not-a-real-secret")
        job = Job(work, 2)
        job.failure.connect(lambda code, message: failures.append((code, message)))
        job.start()
        self.until(lambda: bool(failures))
        self.assertEqual(calls, [1])
        self.assertEqual(failures[0][0], "internal")
        self.assertNotIn("not-a-real-secret", failures[0][1])

    def test_typed_failure_propagates(self):
        failures = []
        def work(token, emit):
            raise ApiError("rate_limit", "请稍后再试")
        job = Job(work, 2)
        job.failure.connect(lambda code, message: failures.append((code, message)))
        job.start()
        self.until(lambda: bool(failures))
        self.assertEqual(failures, [("rate_limit", "请稍后再试")])
