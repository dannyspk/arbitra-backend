from datetime import datetime,timezone
import csv
fp='var/myx_15m.csv'
with open(fp,'r',encoding='utf8') as f:
    r=csv.reader(f)
    next(r)
    rows=list(r)
start=int(rows[0][0])
end=int(rows[-1][0])
print('rows_data=',len(rows))
print('start_ms=',start)
print('end_ms=',end)
print('start_utc=',datetime.fromtimestamp(start/1000,timezone.utc).isoformat())
print('end_utc=',datetime.fromtimestamp(end/1000,timezone.utc).isoformat())
if len(rows)>1:
    print('interval_min=',(int(rows[1][0])-start)/60000)
