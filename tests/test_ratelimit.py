import unittest
from unittest import mock

from src.utils.ratelimit import RateLimiter, _env_float


class TestRateLimiter(unittest.TestCase):
    def test_first_call_never_sleeps(self):
        limiter = RateLimiter(2.0)
        with mock.patch("time.sleep") as sleep_mock:
            limiter.wait()
        sleep_mock.assert_not_called()

    def test_second_rapid_call_sleeps_remaining_interval(self):
        limiter = RateLimiter(2.0)
        clock = [100.0]
        with mock.patch("time.monotonic", side_effect=lambda: clock[0]), \
             mock.patch("time.sleep", side_effect=lambda s: clock.__setitem__(0, clock[0] + s)):
            limiter.wait()          # t=100, no sleep
            limiter.wait()          # 0s elapsed -> sleeps 2.0
            limiter.wait()          # t=102, no sleep
            clock[0] = 102.5
            limiter.wait()          # 0.5s elapsed -> sleeps 1.5

    def test_zero_interval_disables_limiting(self):
        limiter = RateLimiter(0.0)
        with mock.patch("time.sleep") as sleep_mock:
            for _ in range(5):
                limiter.wait()
        sleep_mock.assert_not_called()

    def test_reset_clears_state(self):
        limiter = RateLimiter(5.0)
        with mock.patch("time.sleep") as sleep_mock:
            limiter.wait()
            limiter.reset()
            limiter.wait()
        sleep_mock.assert_not_called()

    def test_wait_updates_timestamp_even_when_sleeping(self):
        # _last is set after sleeping, so the interval counts from the end
        # of the previous wait().
        limiter = RateLimiter(1.0)
        clock = [10.0]
        sleeps = []
        with mock.patch("time.monotonic", side_effect=lambda: clock[0]), \
             mock.patch("time.sleep", side_effect=lambda s: (sleeps.append(s), clock.__setitem__(0, clock[0] + s))):
            limiter.wait()
            limiter.wait()          # elapsed 0.0 -> sleeps 1.0, clock -> 11.0
            clock[0] = 11.5
            limiter.wait()          # elapsed 0.5 -> sleeps 0.5, clock -> 12.0
        self.assertEqual(sleeps, [1.0, 0.5])


class TestEnvFloat(unittest.TestCase):
    def test_default_when_unset(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_env_float("NOPE_XYZ", 1.5), 1.5)

    def test_env_override(self):
        with mock.patch.dict("os.environ", {"NOPE_XYZ": "0.25"}):
            self.assertEqual(_env_float("NOPE_XYZ", 1.5), 0.25)

    def test_invalid_env_falls_back(self):
        with mock.patch.dict("os.environ", {"NOPE_XYZ": "abc"}):
            self.assertEqual(_env_float("NOPE_XYZ", 1.5), 1.5)

    def test_negative_env_clamped_to_zero(self):
        with mock.patch.dict("os.environ", {"NOPE_XYZ": "-3"}):
            self.assertEqual(_env_float("NOPE_XYZ", 1.5), 0.0)


if __name__ == "__main__":
    unittest.main()
