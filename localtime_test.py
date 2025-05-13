from datetime import datetime, timedelta, timezone

local_time = datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0)
formated_time = local_time.strftime("%Y/%m/%d_%H-%M-%S")

print(formated_time)

print(local_time.isoformat())
print(local_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"))
