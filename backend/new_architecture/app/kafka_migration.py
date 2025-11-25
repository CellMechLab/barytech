"""
Kafka Migration Module
Provides migration path from per-device topics to scalable shared topics
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Dict, List, Optional

# Import both architectures
from app.kafka_client import forward_to_kafka as forward_to_per_device_kafka
from app.kafka_client import get_kafka_stats as get_per_device_stats
from app.kafka_scalable_client import get_scalable_kafka_stats, send_to_scalable_kafka

logger = logging.getLogger(__name__)


class KafkaMigrationMode(Enum):
    """Migration modes for transitioning between architectures"""

    PER_DEVICE_ONLY = "per_device_only"  # Original per-device topics
    DUAL_WRITE = "dual_write"  # Write to both architectures
    SCALABLE_ONLY = "scalable_only"  # New scalable architecture
    GRADUAL_MIGRATION = "gradual_migration"  # Device-by-device migration


class KafkaMigrationManager:
    """Manages migration between per-device and scalable Kafka architectures"""

    def __init__(self):
        self.mode = KafkaMigrationMode.PER_DEVICE_ONLY
        self.migrated_devices = set()  # Devices that have been migrated
        self.migration_config = {
            "dual_write_timeout": 10.0,  # Timeout for dual writes
            "migration_batch_size": 10,  # Devices to migrate per batch
            "health_check_interval": 30,  # Health check interval in seconds
        }

    def set_migration_mode(self, mode: KafkaMigrationMode):
        """Set the current migration mode and manage Kafka stack"""
        old_mode = self.mode
        logger.info(
            f"🔄 Setting Kafka migration mode: {old_mode.value if old_mode else 'None'} → {mode.value}"
        )
        self.mode = mode

        # Record mode change in stats
        self.stats["mode_changes"] = self.stats.get("mode_changes", 0) + 1
        self.stats["current_mode"] = mode.value
        self.stats["mode_changed_at"] = time.time()

        # ✅ Start/stop Kafka components based on mode
        asyncio.create_task(self._manage_kafka_stack(mode, old_mode))

    async def _manage_kafka_stack(
        self, new_mode: KafkaMigrationMode, old_mode: Optional[KafkaMigrationMode]
    ):
        """Start/stop Kafka components based on migration mode"""
        try:
            # Start scalable stack if needed
            if new_mode in (
                KafkaMigrationMode.DUAL_WRITE,
                KafkaMigrationMode.SCALABLE_ONLY,
                KafkaMigrationMode.GRADUAL_MIGRATION,
            ):
                if not old_mode or old_mode not in (
                    KafkaMigrationMode.DUAL_WRITE,
                    KafkaMigrationMode.SCALABLE_ONLY,
                    KafkaMigrationMode.GRADUAL_MIGRATION,
                ):
                    logger.info("🚀 Starting scalable Kafka stack...")
                    try:
                        from app.kafka_scalable_client import (
                            start_scalable_kafka_consumer,
                            start_scalable_kafka_producer,
                        )

                        await start_scalable_kafka_producer()
                        logger.info("✅ Scalable Kafka producer started")

                        # Start scalable consumer if not already running
                        from app.kafka_scalable_client import active_scalable_consumers

                        if "migration" not in active_scalable_consumers:
                            # Define device handlers for scalable consumer
                            from app.message_processor import (
                                device_config,
                                device_queues,
                                start_device_broadcaster,
                            )

                            async def scalable_device_handler(
                                device_id: str, messages: List[dict]
                            ):
                                """Handler for scalable Kafka consumer during migration"""
                                if device_id not in device_config:
                                    device_config[device_id] = {}  # Device tracking only, save_flag handled by shared_state
                                await start_device_broadcaster(device_id)
                                if device_id not in device_queues:
                                    from app.message_processor import (
                                        MAX_DEVICE_QUEUE_SIZE,
                                    )

                                    device_queues[device_id] = asyncio.Queue(
                                        maxsize=MAX_DEVICE_QUEUE_SIZE
                                    )
                                for i, message in enumerate(messages):
                                    try:
                                        device_queues[device_id].put_nowait(message)
                                    except asyncio.QueueFull:
                                        dropped = len(messages) - i
                                        logger.warning(
                                            f"⚠️ Migration handler: Device queue full for {device_id}, dropped {dropped} messages"
                                        )
                                        break

                            device_handlers = {
                                "frontend1_device": scalable_device_handler,
                                "frontend1_high_perf_device": scalable_device_handler,
                                "frontend1_ultra_high_perf_device": scalable_device_handler,
                                "frontend2_device": scalable_device_handler,
                                "frontend2_high_perf_device": scalable_device_handler,
                                "frontend2_ultra_high_perf_device": scalable_device_handler,
                            }

                            await start_scalable_kafka_consumer(
                                "migration", device_handlers
                            )
                            logger.info("✅ Scalable Kafka consumer started")

                    except Exception as e:
                        logger.error(f"❌ Failed to start scalable Kafka stack: {e}")
                        self.stats["stack_start_failures"] = (
                            self.stats.get("stack_start_failures", 0) + 1
                        )

            # Start per-device stack if needed
            if new_mode in (
                KafkaMigrationMode.PER_DEVICE_ONLY,
                KafkaMigrationMode.DUAL_WRITE,
                KafkaMigrationMode.GRADUAL_MIGRATION,
            ):
                if not old_mode or old_mode not in (
                    KafkaMigrationMode.PER_DEVICE_ONLY,
                    KafkaMigrationMode.DUAL_WRITE,
                    KafkaMigrationMode.GRADUAL_MIGRATION,
                ):
                    logger.info("🚀 Starting per-device Kafka stack...")
                    try:
                        from app.kafka_client import start_kafka_producer
                        from app.kafka_message_processor import (
                            start_kafka_consumers_for_known_devices,
                        )

                        await start_kafka_producer()
                        await start_kafka_consumers_for_known_devices()
                        logger.info("✅ Per-device Kafka stack started")
                    except Exception as e:
                        logger.error(f"❌ Failed to start per-device Kafka stack: {e}")
                        self.stats["stack_start_failures"] = (
                            self.stats.get("stack_start_failures", 0) + 1
                        )

        except Exception as e:
            logger.error(f"❌ Error managing Kafka stack during migration: {e}")
            self.stats["stack_management_errors"] = (
                self.stats.get("stack_management_errors", 0) + 1
            )

    async def health_check(self) -> Dict[str, Dict]:
        """Perform health checks on both Kafka architectures with tolerance"""
        health_status = {
            "per_device": {"status": "unknown", "details": {}},
            "scalable": {"status": "unknown", "details": {}},
            "migration": {
                "current_mode": self.mode.value if self.mode else "unset",
                "stats": self.stats,
            },
        }

        # Check per-device architecture
        try:
            from app.kafka_client import get_kafka_stats

            per_device_stats = get_kafka_stats()

            # ✅ Health check with tolerance (allow some errors)
            production_errors = per_device_stats.get("production_errors", 0)
            consumption_errors = per_device_stats.get("consumption_errors", 0)

            # Allow up to 10 errors per health check window
            is_healthy = production_errors < 10 and consumption_errors < 10

            health_status["per_device"] = {
                "status": "healthy" if is_healthy else "degraded",
                "details": {
                    **per_device_stats,
                    "error_threshold": 10,
                    "is_within_tolerance": is_healthy,
                },
            }
        except ImportError:
            health_status["per_device"] = {
                "status": "unavailable",
                "details": {"error": "Per-device Kafka not available"},
            }
        except Exception as e:
            health_status["per_device"] = {
                "status": "error",
                "details": {"error": str(e)},
            }

        # Check scalable architecture
        try:
            from app.kafka_scalable_client import get_scalable_kafka_stats

            scalable_stats = get_scalable_kafka_stats()

            # ✅ Health check with tolerance
            production_errors = scalable_stats.get("production_errors", 0)
            consumption_errors = scalable_stats.get("consumption_errors", 0)

            # Allow up to 10 errors per health check window
            is_healthy = production_errors < 10 and consumption_errors < 10

            health_status["scalable"] = {
                "status": "healthy" if is_healthy else "degraded",
                "details": {
                    **scalable_stats,
                    "error_threshold": 10,
                    "is_within_tolerance": is_healthy,
                },
            }
        except ImportError:
            health_status["scalable"] = {
                "status": "unavailable",
                "details": {"error": "Scalable Kafka not available"},
            }
        except Exception as e:
            health_status["scalable"] = {
                "status": "error",
                "details": {"error": str(e)},
            }

        return health_status

    async def send_message(self, device_id: str, batch_data: List[dict]) -> bool:
        """Send message based on current migration mode"""

        if self.mode == KafkaMigrationMode.PER_DEVICE_ONLY:
            return await self._send_per_device_only(device_id, batch_data)

        elif self.mode == KafkaMigrationMode.DUAL_WRITE:
            return await self._send_dual_write(device_id, batch_data)

        elif self.mode == KafkaMigrationMode.SCALABLE_ONLY:
            return await self._send_scalable_only(device_id, batch_data)

        elif self.mode == KafkaMigrationMode.GRADUAL_MIGRATION:
            return await self._send_gradual_migration(device_id, batch_data)

        else:
            logger.error(f"❌ Unknown migration mode: {self.mode}")
            return False

    async def _send_per_device_only(
        self, device_id: str, batch_data: List[dict]
    ) -> bool:
        """Send to per-device topics only"""
        return await forward_to_per_device_kafka(device_id, batch_data)

    async def _send_scalable_only(self, device_id: str, batch_data: List[dict]) -> bool:
        """Send to scalable shared topics only"""
        return await send_to_scalable_kafka(device_id, batch_data)

    async def _send_dual_write(self, device_id: str, batch_data: List[dict]) -> bool:
        """Send to both architectures (for validation)"""
        try:
            # Send to both systems concurrently
            tasks = [
                forward_to_per_device_kafka(device_id, batch_data),
                send_to_scalable_kafka(device_id, batch_data),
            ]

            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.migration_config["dual_write_timeout"],
            )

            per_device_success = (
                results[0] if not isinstance(results[0], Exception) else False
            )
            scalable_success = (
                results[1] if not isinstance(results[1], Exception) else False
            )

            if isinstance(results[0], Exception):
                logger.error(
                    f"❌ Per-device write failed for {device_id}: {results[0]}"
                )
            if isinstance(results[1], Exception):
                logger.error(f"❌ Scalable write failed for {device_id}: {results[1]}")

            # Consider success if at least one write succeeds
            success = per_device_success or scalable_success

            if not success:
                logger.error(f"❌ Both writes failed for device {device_id}")
            elif per_device_success and scalable_success:
                logger.debug(f"✅ Dual write successful for device {device_id}")
            else:
                logger.warning(f"⚠️ Partial dual write success for device {device_id}")

            return success

        except asyncio.TimeoutError:
            logger.error(f"❌ Dual write timeout for device {device_id}")
            return False
        except Exception as e:
            logger.error(f"❌ Dual write error for device {device_id}: {e}")
            return False

    async def _send_gradual_migration(
        self, device_id: str, batch_data: List[dict]
    ) -> bool:
        """Send based on per-device migration status"""
        if device_id in self.migrated_devices:
            # Device has been migrated, use scalable architecture
            return await send_to_scalable_kafka(device_id, batch_data)
        else:
            # Device not yet migrated, use per-device architecture
            return await forward_to_per_device_kafka(device_id, batch_data)

    def migrate_device(self, device_id: str):
        """Mark a device as migrated to scalable architecture"""
        self.migrated_devices.add(device_id)
        logger.info(f"📦 Device {device_id} migrated to scalable architecture")
        logger.info(
            f"📊 Migration progress: {len(self.migrated_devices)} devices migrated"
        )

    def rollback_device(self, device_id: str):
        """Rollback a device to per-device architecture"""
        if device_id in self.migrated_devices:
            self.migrated_devices.remove(device_id)
            logger.info(f"↩️ Device {device_id} rolled back to per-device architecture")

    async def migrate_devices_batch(self, device_ids: List[str]):
        """Migrate a batch of devices with health checks"""
        logger.info(f"🚀 Starting batch migration of {len(device_ids)} devices")

        # Pre-migration health check
        if not await self._health_check():
            logger.error("❌ Pre-migration health check failed, aborting")
            return False

        migrated_count = 0
        failed_devices = []

        for device_id in device_ids:
            try:
                # Migrate device
                self.migrate_device(device_id)
                migrated_count += 1

                # Brief pause between migrations
                await asyncio.sleep(0.1)

                # Health check every few devices
                if migrated_count % 5 == 0:
                    if not await self._health_check():
                        logger.warning(
                            f"⚠️ Health check failed after migrating {migrated_count} devices"
                        )
                        break

            except Exception as e:
                logger.error(f"❌ Failed to migrate device {device_id}: {e}")
                failed_devices.append(device_id)

        # Post-migration health check
        await asyncio.sleep(2)  # Let metrics stabilize
        final_health = await self._health_check()

        logger.info("📊 Batch migration results:")
        logger.info(f"   Successfully migrated: {migrated_count}")
        logger.info(f"   Failed migrations: {len(failed_devices)}")
        logger.info(
            f"   Final health check: {'✅ Passed' if final_health else '❌ Failed'}"
        )

        if failed_devices:
            logger.info(f"   Failed devices: {failed_devices}")

        return len(failed_devices) == 0 and final_health

    async def _health_check(self) -> bool:
        """Perform health check on both architectures"""
        try:
            # Get stats from both systems
            per_device_stats = get_per_device_stats()
            scalable_stats = get_scalable_kafka_stats()

            # Basic health checks
            per_device_healthy = (
                per_device_stats.get("production_errors", 0) == 0
                and per_device_stats.get("consumption_errors", 0) == 0
            )

            scalable_healthy = (
                scalable_stats.get("production_errors", 0) == 0
                and scalable_stats.get("consumption_errors", 0) == 0
            )

            overall_health = per_device_healthy and scalable_healthy

            logger.debug(
                f"🏥 Health check - Per-device: {per_device_healthy}, Scalable: {scalable_healthy}"
            )

            return overall_health

        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return False

    def get_migration_stats(self) -> Dict:
        """Get migration statistics"""
        return {
            "migration_mode": self.mode.value,
            "migrated_devices": len(self.migrated_devices),
            "migrated_device_list": list(self.migrated_devices),
            "per_device_stats": get_per_device_stats(),
            "scalable_stats": get_scalable_kafka_stats(),
        }

    def print_migration_status(self):
        """Print current migration status"""
        stats = self.get_migration_stats()

        logger.info("\n📊 KAFKA MIGRATION STATUS")
        logger.info("=" * 50)
        logger.info(f"Mode: {stats['migration_mode']}")
        logger.info(f"Migrated Devices: {stats['migrated_devices']}")

        if stats["migrated_devices"] > 0:
            logger.info(f"Device List: {', '.join(stats['migrated_device_list'][:5])}")
            if stats["migrated_devices"] > 5:
                logger.info(f"  ... and {stats['migrated_devices'] - 5} more")

        # Show comparative stats
        per_device_stats = stats["per_device_stats"]
        scalable_stats = stats["scalable_stats"]

        logger.info("\n📈 Performance Comparison:")
        logger.info("Per-Device Architecture:")
        logger.info(
            f"  Messages Produced: {per_device_stats.get('messages_produced', 0)}"
        )
        logger.info(
            f"  Production Rate: {per_device_stats.get('production_rate', 0):.1f}/sec"
        )

        logger.info("Scalable Architecture:")
        logger.info(
            f"  Messages Produced: {scalable_stats.get('messages_produced', 0)}"
        )
        logger.info(
            f"  Production Rate: {scalable_stats.get('production_rate', 0):.1f}/sec"
        )
        logger.info(f"  Active Devices: {scalable_stats.get('active_devices', 0)}")


# Global migration manager instance
kafka_migration_manager = KafkaMigrationManager()


# Public API functions
async def send_kafka_message(device_id: str, batch_data: List[dict]) -> bool:
    """Send message through migration manager"""
    return await kafka_migration_manager.send_message(device_id, batch_data)


def set_kafka_migration_mode(mode: KafkaMigrationMode):
    """Set migration mode"""
    kafka_migration_manager.set_migration_mode(mode)


def migrate_device_to_scalable(device_id: str):
    """Migrate a device to scalable architecture"""
    kafka_migration_manager.migrate_device(device_id)


async def migrate_devices_batch(device_ids: List[str]) -> bool:
    """Migrate a batch of devices"""
    return await kafka_migration_manager.migrate_devices_batch(device_ids)


def get_kafka_migration_stats() -> Dict:
    """Get migration statistics"""
    return kafka_migration_manager.get_migration_stats()


def print_kafka_migration_status():
    """Print migration status"""
    kafka_migration_manager.print_migration_status()


# Migration workflow functions
async def start_dual_write_validation(duration_minutes: int = 10):
    """Start dual write mode for validation"""
    logger.info(f"🔄 Starting dual write validation for {duration_minutes} minutes")

    # Switch to dual write mode
    set_kafka_migration_mode(KafkaMigrationMode.DUAL_WRITE)

    # Monitor for specified duration
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)

    while time.time() < end_time:
        await asyncio.sleep(30)  # Check every 30 seconds
        print_kafka_migration_status()

    logger.info("✅ Dual write validation completed")


async def perform_gradual_migration(device_ids: List[str], batch_size: int = 10):
    """Perform gradual migration of devices"""
    logger.info(f"🚀 Starting gradual migration of {len(device_ids)} devices")

    # Switch to gradual migration mode
    set_kafka_migration_mode(KafkaMigrationMode.GRADUAL_MIGRATION)

    # Migrate in batches
    for i in range(0, len(device_ids), batch_size):
        batch = device_ids[i : i + batch_size]
        logger.info(f"📦 Migrating batch {i//batch_size + 1}: {batch}")

        success = await migrate_devices_batch(batch)
        if not success:
            logger.error(
                f"❌ Batch migration failed, stopping at batch {i//batch_size + 1}"
            )
            break

        # Wait between batches
        await asyncio.sleep(5)

        # Print progress
        print_kafka_migration_status()

    logger.info("✅ Gradual migration completed")


__all__ = [
    "KafkaMigrationMode",
    "send_kafka_message",
    "set_kafka_migration_mode",
    "migrate_device_to_scalable",
    "migrate_devices_batch",
    "get_kafka_migration_stats",
    "print_kafka_migration_status",
    "start_dual_write_validation",
    "perform_gradual_migration",
]
