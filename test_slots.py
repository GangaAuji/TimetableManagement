from datetime import time, datetime, timedelta

print("=" * 60)
print("UPDATED SCHEDULE: Break 3:00-3:30 PM")
print("=" * 60)
day_start = time(13, 0)  # 1:00 PM
day_end = time(17, 30)   # 5:30 PM
break_start = time(15, 0)  # 3:00 PM (CHANGED from 3:30 PM)
break_duration = 30  # 30 minutes
lecture_minutes = 60  # 60 minutes per lecture

current = datetime.combine(datetime.today(), day_start)
end_dt = datetime.combine(datetime.today(), day_end)
break_start_dt = datetime.combine(datetime.today(), break_start)
break_end_dt = break_start_dt + timedelta(minutes=break_duration)

slots = []
while current + timedelta(minutes=lecture_minutes) <= end_dt:
    slot_end = current + timedelta(minutes=lecture_minutes)
    if break_start_dt and break_duration > 0:
        if current >= break_end_dt:
            slots.append((current.time(), slot_end.time()))
            current = slot_end
            continue
        if slot_end <= break_start_dt:
            slots.append((current.time(), slot_end.time()))
            current = slot_end
            continue
        if current < break_start_dt and (break_start_dt - current).total_seconds() >= lecture_minutes * 60:
            slots.append((current.time(), slot_end.time()))
            current = slot_end
            continue
        current = break_end_dt
        continue
    slots.append((current.time(), slot_end.time()))
    current = slot_end

print(f'Day: 1:00 PM to 5:30 PM')
print(f'Break: 3:00 PM to 3:30 PM')
print(f'Lecture Duration: 60 minutes')
print()
print(f'✅ Total slots per day: {len(slots)}')
for i, s in enumerate(slots, 1):
    print(f'  Session {i}: {s[0].strftime("%I:%M %p")} - {s[1].strftime("%I:%M %p")}')
print()
print(f'📊 Weekly Capacity: {len(slots)} sessions/day × 6 days = {len(slots) * 6} sessions/week')
print()
if len(slots) == 4:
    print("✅ Perfect! This matches your requirement of 4 sessions per day (24 per week)")
else:
    print(f"⚠️  This gives {len(slots)} sessions/day, not 4 as required")
