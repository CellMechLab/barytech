"""
Intelligent Buffer Manager for MQTT → Kafka Pipeline
Prevents subscriber choking when Kafka lags with multi-tier buffering
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.metrics import OVERFLOW_QUEUE_SIZE, record_message_loss


@dataclass
class BufferConfig:
    """Configuration for buffer zones"""

    # Primary buffer (fastest access)
    primary_size: int = 100000  # 100K messages
    primary_timeout: float = 0.001  # 1ms timeout

    # Secondary buffer (medium priority)
    secondary_size: int = 200000  # 200K messages
    secondary_timeout: float = 0.01  # 10ms timeout

    # Overflow buffer (persistent fallback)
    overflow_size: int = 500000  # 500K messages
    overflow_timeout: float = 0.1  # 100ms timeout

    # Kafka health monitoring
    kafka_health_check_interval: float = 5.0  # 5 seconds
    kafka_unhealthy_threshold: int = 3  # 3 consecutive failures

    # Backpressure thresholds
    backpressure_warning_threshold: float = 0.7  # 70% full
    backpressure_critical_threshold: float = 0.9  # 90% full
    backpressure_emergency_threshold: float = 0.95  # 95% full


class MessageBuffer:
    """Individual message buffer with priority handling"""

    def __init__(self, max_size: int, timeout: float, name: str):
        self.max_size = max_size
        self.timeout = timeout
        self.name = name
        self.queue = asyncio.Queue(maxsize=max_size)
        self.dropped_count = 0
        self.last_drop_time = 0

    async def put(self, message: bytes, priority: int = 0) -> bool:
        """Put message in buffer with priority handling"""
        try:
            # Try to put immediately
            self.queue.put_nowait((priority, time.time(), message))
            return True
        except asyncio.QueueFull:
            # Buffer full, try to drop lowest priority message
            if await self._drop_lowest_priority():
                try:
                    self.queue.put_nowait((priority, time.time(), message))
                    return True
                except asyncio.QueueFull:
                    pass

            # Still full, drop this message
            self._record_drop()
            return False

    async def get(self) -> Optional[bytes]:
        """Get message from buffer (highest priority first)"""
        try:
            # Get with timeout
            priority, timestamp, message = await asyncio.wait_for(
                self.queue.get(), timeout=self.timeout
            )
            return message
        except asyncio.TimeoutError:
            return None

    async def _drop_lowest_priority(self) -> bool:
        """Drop lowest priority message to make room"""
        if self.queue.empty():
            return False

        # Find lowest priority message
        lowest_priority = float("inf")
        lowest_message = None

        # Create temporary queue to find lowest priority
        temp_queue = asyncio.Queue()
        while not self.queue.empty():
            priority, timestamp, message = await self.queue.get()
            if priority < lowest_priority:
                lowest_priority = priority
                lowest_message = (priority, timestamp, message)
            temp_queue.put_nowait((priority, timestamp, message))

        # Restore queue without lowest priority message
        while not temp_queue.empty():
            item = await temp_queue.get()
            if item != lowest_message:
                self.queue.put_nowait(item)

        return True

    def _record_drop(self):
        """Record message drop for monitoring"""
        self.dropped_count += 1
        self.last_drop_time = time.time()

    def qsize(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()

    def is_full(self) -> bool:
        """Check if buffer is full"""
        return self.queue.qsize() >= self.max_size

    def utilization(self) -> float:
        """Get buffer utilization percentage"""
        return self.queue.qsize() / self.max_size


class IntelligentBufferManager:
    """Multi-tier buffer manager with intelligent backpressure handling"""

    def __init__(self, config: BufferConfig = None):
        self.config = config or BufferConfig()

        # Initialize buffer tiers
        self.primary_buffer = MessageBuffer(
            self.config.primary_size, self.config.primary_timeout, "primary"
        )
        self.secondary_buffer = MessageBuffer(
            self.config.secondary_size, self.config.secondary_timeout, "secondary"
        )
        self.overflow_buffer = MessageBuffer(
            self.config.overflow_size, self.config.overflow_timeout, "overflow"
        )

        # Kafka health monitoring
        self.kafka_healthy = True
        self.kafka_failure_count = 0
        self.last_kafka_health_check = 0

        # Backpressure state
        self.backpressure_level = 0  # 0=normal, 1=warning, 2=critical, 3=emergency
        self.last_backpressure_check = 0

        # Statistics
        self.total_messages_received = 0
        self.total_messages_processed = 0
        self.total_messages_dropped = 0

        # Start background tasks
        self._running = True
        asyncio.create_task(self._health_monitor())
        asyncio.create_task(self._backpressure_monitor())
        asyncio.create_task(self._buffer_balancer())

    async def put_message(
        self, message: bytes, priority: int = 0, source: str = "mqtt"
    ) -> bool:
        """Put message in appropriate buffer tier"""
        self.total_messages_received += 1

        # Try primary buffer first (fastest)
        if await self.primary_buffer.put(message, priority):
            return True

        # Primary full, try secondary
        if await self.secondary_buffer.put(message, priority):
            return True

        # Secondary full, try overflow
        if await self.overflow_buffer.put(message, priority):
            return True

        # All buffers full, message dropped
        self.total_messages_dropped += 1
        record_message_loss("all_buffers_full")
        return False

    async def get_message(self, timeout: float = None) -> Optional[bytes]:
        """Get message from buffers in priority order"""
        # Try primary buffer first
        message = await self.primary_buffer.get()
        if message:
            self.total_messages_processed += 1
            return message

        # Primary empty, try secondary
        message = await self.secondary_buffer.get()
        if message:
            self.total_messages_processed += 1
            return message

        # Secondary empty, try overflow
        message = await self.overflow_buffer.get()
        if message:
            self.total_messages_processed += 1
            return message

        return None

    async def get_batch(self, max_size: int, timeout: float = None) -> List[bytes]:
        """Get batch of messages from buffers"""
        batch = []
        start_time = time.time()

        while len(batch) < max_size:
            if timeout and (time.time() - start_time) > timeout:
                break

            message = await self.get_message(timeout=0.001)
            if message:
                batch.append(message)
            else:
                # No more messages available
                break

        return batch

    async def _health_monitor(self):
        """Monitor Kafka health and adjust buffer behavior"""
        while self._running:
            try:
                current_time = time.time()

                # Check Kafka health periodically
                if (
                    current_time - self.last_kafka_health_check
                    > self.config.kafka_health_check_interval
                ):
                    await self._check_kafka_health()
                    self.last_kafka_health_check = current_time

                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ Error in health monitor: {e}")
                await asyncio.sleep(5)

    async def _check_kafka_health(self):
        """Check if Kafka is healthy and adjust buffer behavior"""
        try:
            # Try to import and check Kafka health
            from app.kafka_client import kafka_health_check

            health = await kafka_health_check()

            if health.get("status") == "healthy":
                self.kafka_healthy = True
                self.kafka_failure_count = 0
                print("✅ Kafka health check passed")
            else:
                self.kafka_healthy = False
                self.kafka_failure_count += 1
                print(f"⚠️ Kafka health check failed: {health}")

        except Exception as e:
            self.kafka_healthy = False
            self.kafka_failure_count += 1
            print(f"❌ Kafka health check error: {e}")

        # Adjust buffer behavior based on Kafka health
        if self.kafka_failure_count >= self.config.kafka_unhealthy_threshold:
            print(
                f"🚨 Kafka unhealthy for {self.kafka_failure_count} checks - enabling emergency buffering"
            )
            # Increase buffer timeouts when Kafka is unhealthy
            self.primary_buffer.timeout *= 2
            self.secondary_buffer.timeout *= 2
            self.overflow_buffer.timeout *= 2

    async def _backpressure_monitor(self):
        """Monitor buffer utilization and trigger backpressure handling"""
        while self._running:
            try:
                current_time = time.time()

                # Check backpressure every second
                if current_time - self.last_backpressure_check > 1.0:
                    await self._check_backpressure()
                    self.last_backpressure_check = current_time

                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ Error in backpressure monitor: {e}")
                await asyncio.sleep(5)

    async def _check_backpressure(self):
        """Check buffer utilization and trigger appropriate backpressure levels"""
        # Calculate overall utilization
        total_size = (
            self.config.primary_size
            + self.config.secondary_size
            + self.config.overflow_size
        )
        total_used = (
            self.primary_buffer.qsize()
            + self.secondary_buffer.qsize()
            + self.overflow_buffer.qsize()
        )
        utilization = total_used / total_size

        # Determine backpressure level
        old_level = self.backpressure_level

        if utilization >= self.config.backpressure_emergency_threshold:
            self.backpressure_level = 3  # Emergency
        elif utilization >= self.config.backpressure_critical_threshold:
            self.backpressure_level = 2  # Critical
        elif utilization >= self.config.backpressure_warning_threshold:
            self.backpressure_level = 1  # Warning
        else:
            self.backpressure_level = 0  # Normal

        # Log backpressure changes
        if old_level != self.backpressure_level:
            level_names = ["Normal", "Warning", "Critical", "Emergency"]
            print(
                f"🚨 Backpressure level changed: {level_names[old_level]} → {level_names[self.backpressure_level]} ({utilization:.1%} utilization)"
            )

            # Update Prometheus metrics
            try:
                OVERFLOW_QUEUE_SIZE.set(total_used)
            except ImportError:
                pass

    async def _buffer_balancer(self):
        """Balance messages between buffer tiers for optimal performance"""
        while self._running:
            try:
                # Move messages from overflow to secondary if secondary has space
                if (
                    self.overflow_buffer.qsize() > 0
                    and self.secondary_buffer.qsize() < self.config.secondary_size * 0.5
                ):

                    message = await self.overflow_buffer.get()
                    if message:
                        await self.secondary_buffer.put(message, priority=1)

                # Move messages from secondary to primary if primary has space
                if (
                    self.secondary_buffer.qsize() > 0
                    and self.primary_buffer.qsize() < self.config.primary_size * 0.5
                ):

                    message = await self.secondary_buffer.get()
                    if message:
                        await self.primary_buffer.put(message, priority=2)

                await asyncio.sleep(0.1)  # Check every 100ms

            except Exception as e:
                print(f"❌ Error in buffer balancer: {e}")
                await asyncio.sleep(1)

    def get_stats(self) -> Dict:
        """Get comprehensive buffer statistics"""
        return {
            "total_messages_received": self.total_messages_received,
            "total_messages_processed": self.total_messages_processed,
            "total_messages_dropped": self.total_messages_dropped,
            "kafka_healthy": self.kafka_healthy,
            "kafka_failure_count": self.kafka_failure_count,
            "backpressure_level": self.backpressure_level,
            "buffers": {
                "primary": {
                    "size": self.primary_buffer.qsize(),
                    "max_size": self.primary_buffer.max_size,
                    "utilization": self.primary_buffer.utilization(),
                    "dropped": self.primary_buffer.dropped_count,
                },
                "secondary": {
                    "size": self.secondary_buffer.qsize(),
                    "max_size": self.secondary_buffer.max_size,
                    "utilization": self.secondary_buffer.utilization(),
                    "dropped": self.secondary_buffer.dropped_count,
                },
                "overflow": {
                    "size": self.overflow_buffer.qsize(),
                    "max_size": self.overflow_buffer.max_size,
                    "utilization": self.overflow_buffer.utilization(),
                    "dropped": self.overflow_buffer.dropped_count,
                },
            },
            "overall_utilization": (
                (
                    self.primary_buffer.qsize()
                    + self.secondary_buffer.qsize()
                    + self.overflow_buffer.qsize()
                )
                / (
                    self.config.primary_size
                    + self.config.secondary_size
                    + self.config.overflow_size
                )
            ),
        }

    def print_stats(self):
        """Print buffer statistics"""
        stats = self.get_stats()
        print("\n📊 INTELLIGENT BUFFER MANAGER STATS:")
        print(f"   Total Messages: {stats['total_messages_received']:,}")
        print(f"   Processed: {stats['total_messages_processed']:,}")
        print(f"   Dropped: {stats['total_messages_dropped']:,}")
        print(
            f"   Kafka Health: {'✅ Healthy' if stats['kafka_healthy'] else '❌ Unhealthy'}"
        )
        print(f"   Kafka Failures: {stats['kafka_failure_count']}")
        print(f"   Backpressure Level: {stats['backpressure_level']}")
        print(f"   Overall Utilization: {stats['overall_utilization']:.1%}")

        for buffer_name, buffer_stats in stats["buffers"].items():
            print(
                f"   {buffer_name.title()} Buffer: {buffer_stats['size']:,}/{buffer_stats['max_size']:,} ({buffer_stats['utilization']:.1%}) - Dropped: {buffer_stats['dropped']}"
            )

    async def shutdown(self):
        """Gracefully shutdown the buffer manager"""
        self._running = False
        print("🔄 Shutting down Intelligent Buffer Manager...")


# Global buffer manager instance
buffer_manager: Optional[IntelligentBufferManager] = None


def get_buffer_manager() -> IntelligentBufferManager:
    """Get the global buffer manager instance"""
    global buffer_manager
    if buffer_manager is None:
        raise RuntimeError("Buffer manager not initialized!")
    return buffer_manager


async def initialize_buffer_manager(
    config: BufferConfig = None,
) -> IntelligentBufferManager:
    """Initialize the global buffer manager"""
    global buffer_manager
    if buffer_manager is None:
        buffer_manager = IntelligentBufferManager(config)
        print("🚀 Intelligent Buffer Manager initialized")
    return buffer_manager


async def shutdown_buffer_manager():
    """Shutdown the global buffer manager"""
    global buffer_manager
    if buffer_manager:
        await buffer_manager.shutdown()
        buffer_manager = None
        print("🔌 Intelligent Buffer Manager shutdown complete")


__all__ = [
    "BufferConfig",
    "MessageBuffer",
    "IntelligentBufferManager",
    "get_buffer_manager",
    "initialize_buffer_manager",
    "shutdown_buffer_manager",
]
