# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Rate limiter utilities for CXAS Scrapi."""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """A thread-safe request-bucket rate limiter.

    Useful for limiting request rates to APIs to avoid quota exhaustion.
    """

    def __init__(self, requests_per_minute: float):
        """Initializes the RateLimiter.

        Args:
            requests_per_minute: The sustained rate allowed (RPM).
        """
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be greater than 0")

        self.rate = requests_per_minute / 60.0  # requests per second
        self.capacity = 1.0  # Capacity of 1.0 enforces strict pacing
        self.available_requests = self.capacity
        self.last_update = time.time()
        self.lock = threading.Lock()

        logger.debug(f"Initialized RateLimiter with rate={self.rate}/s")

    def consume(self, requests: float = 1.0) -> bool:
        """Attempts to consume requests immediately.

        Args:
            requests: Number of requests to consume.

        Returns:
            True if requests were successfully consumed, False otherwise.
        """
        with self.lock:
            self._refill()
            if self.available_requests >= requests:
                self.available_requests -= requests
                return True
            return False

    def wait_and_consume(self, requests: float = 1.0) -> None:
        """Consumes requests, blocking if necessary until they become available.

        Args:
            requests: Number of requests to consume.
        """
        while True:
            with self.lock:
                self._refill()
                if self.available_requests >= requests:
                    self.available_requests -= requests
                    return

                # Calculate how long we need to wait
                needed = requests - self.available_requests
                wait_time = needed / self.rate

            logger.debug(f"Rate limit reached. Waiting {wait_time:.2f}s...")
            time.sleep(wait_time)

    def _refill(self) -> None:
        """Refills the bucket based on elapsed time.

        Must be called while holding the lock.
        """
        now = time.time()
        elapsed = now - self.last_update
        self.last_update = now

        new_requests = elapsed * self.rate
        if new_requests > 0:
            self.available_requests = min(
                self.capacity, self.available_requests + new_requests
            )
            logger.debug(
                f"Refilled {new_requests:.2f} requests. "
                f"Current: {self.available_requests:.2f}"
            )
