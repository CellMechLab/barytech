#!/usr/bin/env python3
"""
Optimize TimescaleDB hypertable chunk interval for high-throughput ingestion.

Current chunk: 7 days (too large for 10k/sec ingestion)
Recommended: 15-30 minutes (optimal for high-frequency data)

Usage:
    python optimize_timescale_chunks.py
"""

import asyncio
import asyncpg
from datetime import datetime

DATABASE_URL = "postgresql://postgres:calculator1@localhost:5433/schaefer"

async def analyze_current_chunks():
    """Analyze current chunk configuration"""
    print("=" * 70)
    print("📊 TimescaleDB Chunk Analysis")
    print("=" * 70)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    try:
        conn = await asyncpg.connect(dsn=DATABASE_URL)
        
        # Check hypertable info
        hypertables = await conn.fetch("""
            SELECT hypertable_name, num_dimensions 
            FROM timescaledb_information.hypertables;
        """)
        
        print(f"📋 Hypertables found: {len(hypertables)}")
        for ht in hypertables:
            print(f"   - {ht['hypertable_name']} (dimensions: {ht['num_dimensions']})")
        
        # Get chunk interval
        interval = await conn.fetchrow("""
            SELECT h.table_name, d.interval_length 
            FROM _timescaledb_catalog.hypertable h 
            INNER JOIN _timescaledb_catalog.dimension d ON h.id = d.hypertable_id 
            WHERE h.table_name = 'device_data' AND d.column_name = 'timestamp';
        """)
        
        if interval:
            interval_us = interval['interval_length']
            interval_seconds = interval_us / 1_000_000
            interval_minutes = interval_seconds / 60
            interval_hours = interval_minutes / 60
            interval_days = interval_hours / 24
            
            print(f"\n📐 Current chunk interval:")
            print(f"   Microseconds: {interval_us:,}")
            print(f"   Seconds: {interval_seconds:,.0f}")
            print(f"   Minutes: {interval_minutes:,.1f}")
            print(f"   Hours: {interval_hours:,.1f}")
            print(f"   Days: {interval_days:,.1f}")
        
        # Count chunks
        chunks = await conn.fetch("SELECT show_chunks('device_data');")
        print(f"\n📦 Total chunks: {len(chunks)}")
        
        # Get chunk sizes
        if chunks:
            print(f"\n📊 Chunk details:")
            for i, chunk in enumerate(chunks[:5]):  # Show first 5
                chunk_name = chunk['show_chunks']
                size = await conn.fetchval(f"""
                    SELECT pg_size_pretty(pg_total_relation_size('{chunk_name}'));
                """)
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {chunk_name};")
                print(f"   {i+1}. {chunk_name}: {count:,} records, {size}")
            
            if len(chunks) > 5:
                print(f"   ... and {len(chunks) - 5} more chunks")
        
        # Calculate optimal chunk interval
        count = await conn.fetchval("SELECT COUNT(*) FROM device_data;")
        if count > 0:
            latest = await conn.fetchval("SELECT MAX(timestamp) FROM device_data;")
            oldest = await conn.fetchval("SELECT MIN(timestamp) FROM device_data;")
            
            if latest and oldest:
                time_span_seconds = (latest - oldest).total_seconds()
                records_per_second = count / time_span_seconds if time_span_seconds > 0 else 0
                
                print(f"\n📈 Data statistics:")
                print(f"   Total records: {count:,}")
                print(f"   Time span: {time_span_seconds:,.1f} seconds ({time_span_seconds/3600:,.1f} hours)")
                print(f"   Ingestion rate: {records_per_second:,.0f} records/sec")
                
                # Recommend chunk interval based on ingestion rate
                if records_per_second > 5000:
                    recommended_minutes = 15
                elif records_per_second > 1000:
                    recommended_minutes = 30
                elif records_per_second > 100:
                    recommended_minutes = 60
                else:
                    recommended_minutes = 1440  # 1 day
                
                records_per_chunk = records_per_second * recommended_minutes * 60
                
                print(f"\n💡 Recommendations:")
                print(f"   Current chunk interval: {interval_minutes:,.0f} minutes")
                print(f"   Recommended: {recommended_minutes} minutes")
                print(f"   Records per chunk (recommended): {records_per_chunk:,.0f}")
                
                if interval_minutes > recommended_minutes * 2:
                    print(f"\n⚠️  Current chunks are TOO LARGE!")
                    print(f"   Large chunks = slower inserts + slower vacuum")
                    print(f"   Recommended action: Reduce chunk interval to {recommended_minutes} minutes")
                elif interval_minutes < recommended_minutes / 2:
                    print(f"\n⚠️  Current chunks are TOO SMALL!")
                    print(f"   Small chunks = too many chunks + overhead")
                    print(f"   Recommended action: Increase chunk interval to {recommended_minutes} minutes")
                else:
                    print(f"\n✅ Chunk interval is reasonable for your ingestion rate")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def optimize_chunk_interval(minutes=15):
    """
    Change the chunk interval for device_data hypertable.
    
    WARNING: This creates a new chunk interval going forward.
    Existing chunks keep their original interval.
    """
    print("\n" + "=" * 70)
    print(f"⚙️  Optimize Chunk Interval to {minutes} Minutes")
    print("=" * 70)
    
    print(f"\n⚠️  WARNING: This will change chunk interval for NEW chunks only.")
    print(f"   Existing chunks will keep their current interval (7 days).")
    print(f"   New chunks will use {minutes} minutes.")
    print(f"\n   For clean migration, consider:")
    print(f"   1. Export data")
    print(f"   2. Drop and recreate hypertable with new interval")
    print(f"   3. Re-import data")
    
    confirm = input(f"\nType 'CHANGE {minutes}MIN' to change chunk interval: ")
    
    if confirm != f"CHANGE {minutes}MIN":
        print("❌ Cancelled")
        return False
    
    try:
        conn = await asyncpg.connect(dsn=DATABASE_URL)
        
        # Change chunk interval
        print(f"\n🔧 Setting chunk interval to {minutes} minutes...")
        await conn.execute(f"""
            SELECT set_chunk_time_interval('device_data', INTERVAL '{minutes} minutes');
        """)
        
        print(f"✅ Chunk interval updated to {minutes} minutes")
        print(f"\n   New chunks will use {minutes}-minute intervals")
        print(f"   Existing chunks unchanged")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_compression():
    """Check compression settings"""
    print("\n" + "=" * 70)
    print("🗜️  Compression Settings")
    print("=" * 70)
    
    try:
        conn = await asyncpg.connect(dsn=DATABASE_URL)
        
        compression = await conn.fetch("""
            SELECT hypertable_name, compression_enabled 
            FROM timescaledb_information.hypertables;
        """)
        
        for comp in compression:
            enabled = "✅ Enabled" if comp['compression_enabled'] else "❌ Disabled"
            print(f"   {comp['hypertable_name']}: {enabled}")
        
        # Check compression policies
        policies = await conn.fetch("""
            SELECT application_name, schedule_interval, config 
            FROM timescaledb_information.jobs 
            WHERE application_name LIKE '%compression%';
        """)
        
        if policies:
            print(f"\n📋 Compression policies:")
            for p in policies:
                print(f"   - Interval: {p['schedule_interval']}")
                print(f"     Config: {p['config']}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Main function"""
    print("=" * 70)
    print("TimescaleDB Optimization Tool")
    print("=" * 70)
    
    # Analyze current state
    await analyze_current_chunks()
    
    # Check compression
    await check_compression()
    
    print("\n" + "=" * 70)
    print("Options:")
    print("  1. Change chunk interval to 15 minutes (recommended for 10k/sec)")
    print("  2. Change chunk interval to 30 minutes")
    print("  3. Change chunk interval to 60 minutes")
    print("  4. Exit without changes")
    
    choice = input("\nEnter choice (1/2/3/4): ").strip()
    
    if choice == "1":
        await optimize_chunk_interval(15)
    elif choice == "2":
        await optimize_chunk_interval(30)
    elif choice == "3":
        await optimize_chunk_interval(60)
    else:
        print("Exiting without changes.")
    
    print("\n" + "=" * 70)
    print("✅ Analysis complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())







