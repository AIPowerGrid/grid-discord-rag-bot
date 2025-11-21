#!/usr/bin/env python3
"""
View bot's current mood and memories from the database.
"""
from conversation_db import get_mood, get_all_memories, format_mood, format_memories, get_recent_happenings, format_recent_happenings
import json

def main():
    print("=" * 60)
    print("🤖 BOT STATE")
    print("=" * 60)
    
    # Get current mood
    print("\n📊 CURRENT MOOD:")
    print("-" * 60)
    mood = get_mood()
    print(f"Mood: {mood['mood']}")
    print(f"Description: {mood['description']}")
    print(f"Intensity: {mood['intensity']:.2f}")
    
    # Get recent happenings
    print("\n🌐 RECENT HAPPENINGS:")
    print("-" * 60)
    happenings = get_recent_happenings()
    if happenings:
        print(happenings)
    else:
        print("(No recent happenings recorded yet)")
    
    # Get all memories
    print("\n💾 MEMORY BANK:")
    print("-" * 60)
    memories = get_all_memories()
    
    if not memories:
        print("No memories stored yet.")
    else:
        print(f"Total memories: {len(memories)}\n")
        for i, mem in enumerate(memories, 1):
            source = mem.get('source', 'unknown')
            updated = mem.get('updated_at', 'unknown')
            print(f"{i}. [{mem['key']}]")
            print(f"   Value: {mem['value']}")
            print(f"   Source: {source}")
            print(f"   Updated: {updated}")
            print()
    
    # Show formatted versions (as bot sees them)
    print("\n📝 FORMATTED (as bot sees in prompts):")
    print("-" * 60)
    print(format_mood())
    print()
    happenings_formatted = format_recent_happenings()
    if happenings_formatted:
        print(happenings_formatted)
        print()
    mem_formatted = format_memories()
    if mem_formatted:
        print(mem_formatted)
    else:
        print("(No memories)")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()

