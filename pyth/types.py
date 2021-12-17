import operator as _op

from enum import Enum as _Enum
from typing import (
  Callable as _Callable,
  NamedTuple as _NamedTuple,
  NewType as _NewType,
  TypeVar as _TypeVar,
)


Count = _NewType('Count', int)
Price = _NewType('Price', int)
PriceDiff = _NewType('PriceDiff', int)
Confidence = _NewType('Confidence', float)

NSecs = _NewType('NSecs', int)
USecs = _NewType('USecs', int)
MSecs = _NewType('MSecs', int)
Seconds = _NewType('Seconds', int)
Minutes = _NewType('Minutes', int)
Hours = _NewType('Hours', int)
Days = _NewType('Days', int)
Years = _NewType('Years', int)

Timestamp = _NewType('Timestamp', NSecs)
TimeUnit = _TypeVar(
  'TimeUnit',
  NSecs,
  USecs,
  MSecs,
  Seconds,
  Minutes,
  Hours,
  Days,
  Years,
)

PriceTime = _NamedTuple('Trade', [
  ('price', Price),
  ('ts', Timestamp),
])

PriceConf = _NamedTuple('PriceConf', [
  ('price', Price),
  ('conf', Confidence),
])

PriceRange = _NamedTuple('PriceRange', [
  ('high', Price),
  ('low', Price),
])

TimeRange = _NamedTuple('TimeRange', [
  ('start', Timestamp),
  ('end', Timestamp),
])

add_time: _Callable[[TimeUnit, TimeUnit], TimeUnit] = _op.add
scale_time: _Callable[[TimeUnit, int], TimeUnit] = _op.mul
inc_timestamp: _Callable[[Timestamp, NSecs], Timestamp] = _op.add
diff_timestamps: _Callable[[Timestamp, Timestamp], NSecs] = _op.sub

NS_PER_US = NSecs(1000)
NS_PER_MS = NSecs(NS_PER_US * 1000)
NS_PER_SEC = NSecs(NS_PER_MS * 1000)
NS_PER_MIN = NSecs(NS_PER_SEC * 60)
NS_PER_HOUR = NSecs(NS_PER_MIN * 60)
NS_PER_DAY = NSecs(NS_PER_HOUR * 24)
NS_PER_YEAR = NSecs(NS_PER_DAY * 365)


class Status(str, _Enum):
  TRADING = 'Trading'
  UNKNOWN = 'Unknown'
