"""
IB TWS connection manager — connect/disconnect with reconnect logic.
"""

import asyncio
import time
from loguru import logger
from ib_insync import IB, util

from config import TWS_HOST, TWS_PORT, TWS_CLIENT_ID


class IBConnection:
    """Manages a single ib_insync connection to TWS Desktop."""

    def __init__(self, host=None, port=None, client_id=None):
        self.ib = IB()
        self.host = host or TWS_HOST
        self.port = port or TWS_PORT
        self.client_id = client_id or TWS_CLIENT_ID

    def connect(self, max_retries=3, retry_delay=5):
        """Connect to TWS with retry logic."""
        if self.ib.isConnected():
            return self.ib

        # Ensure an asyncio event loop exists (needed by ib_insync)
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        cid = self.client_id
        for attempt in range(1, max_retries + 1):
            try:
                self.ib.connect(
                    self.host, self.port,
                    clientId=cid,
                    readonly=True,
                    timeout=20,
                )
                logger.info(
                    f"Connected to TWS at {self.host}:{self.port} "
                    f"(clientId={cid}, account: {self.ib.managedAccounts()})"
                )
                self.client_id = cid
                return self.ib
            except Exception as e:
                err_msg = str(e)
                is_client_id_err = "client id" in err_msg.lower() or "already in use" in err_msg.lower()
                if is_client_id_err:
                    cid += 1
                    logger.warning(
                        f"TWS client id {cid - 1} in use, trying id {cid} "
                        f"(attempt {attempt}/{max_retries})"
                    )
                else:
                    logger.warning(f"TWS connect attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay if is_client_id_err else retry_delay * attempt)
        raise ConnectionError(f"Failed to connect to TWS after {max_retries} attempts")

    def disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from TWS")

    def is_connected(self):
        return self.ib.isConnected()

    def ensure_connected(self):
        """Reconnect if connection was lost."""
        if not self.ib.isConnected():
            logger.warning("TWS connection lost, reconnecting...")
            self.connect()
        return self.ib

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
