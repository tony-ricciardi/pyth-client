from pyth.types import *

from collections import deque
from typing import Deque, Optional

import numpy as np


__all__ = [
  'Candle',
  'ConfidenceModel',
  'HighLowTracker',
  'PricingModel',
  'VolatilityModel',
]


class HighLowTracker:

  def __init__(self):
    self._range: Optional[PriceRange] = None

  @property
  def high(self) -> Price:
    return self._range.high

  @property
  def low(self) -> Price:
    return self._range.low

  @property
  def spread(self) -> Optional[PriceDiff]:
    return None if self._range is None else (self.high - self.low)

  def add_price(self, price: Price):
    if self._range is None:
      high = low = price
    else:
      high = max(self.high, price)
      low = min(self.low, price)
    self._range = PriceRange(high=high, low=low)

  def reset(self):
    self._range = None


class Candle:

  def __init__(self, start_ts: Timestamp, *, width_ns: NSecs):

    self._width_ns = width_ns
    start_ts = self.floor_ts(start_ts)
    end_ts = inc_timestamp(start_ts, self._width_ns)
    self._time_range = TimeRange(start_ts, end_ts)
    self._price_range = HighLowTracker()

    assert self.width_ns > 0, self.width_ns
    assert self.floor_ts(self.start_ts) == self.start_ts
    assert self.floor_ts(self.end_ts) == self.end_ts
    assert self.contains_ts(self.start_ts)
    assert not self.contains_ts(self.end_ts)

  @property
  def start_ts(self) -> Timestamp:
    return self._time_range.start

  @property
  def end_ts(self) -> Timestamp:
    return self._time_range.end

  @property
  def width_ns(self) -> NSecs:
    return self._width_ns

  @property
  def high(self) -> Price:
    return self._price_range.high

  @property
  def low(self) -> Price:
    return self._price_range.low

  def add_price(self, price: Price):
    self._price_range.add_price(price)

  def floor_ts(self, ts: Timestamp) -> Timestamp:
    return Timestamp(NSecs(ts // self._width_ns * self._width_ns))

  def contains_ts(self, ts: Timestamp) -> bool:
    return self.floor_ts(ts) == self.start_ts


class VolatilityModel:
  """
  volatility model works by aggregating tick level trade data into candles containing high/low price of trades
  in that candle, along with start and end times of the candle.
  Empty candles (where we have no fills) are NOT included and the model skips over them, using the last
  "ncandles" populated candles to make its volatility estimate
  candle_width_minute is the width in minutes of the aggregation "candles" used in volatility estimate
  ncandles is the number of trailing candles to average over in volatility estimate
  initial_volatility is the volatility to use (a high upper limit) when the model starts up and doesn't have
  any data to use to begin with. defaults to 100% annualized which should be fine for all products. It is
  really only used at startup
  """

  def __init__(
      self,
      *,
      trail_len: Count,
      width_ns: NSecs,
      default_vol: float = None,
  ):
    if default_vol is None:
      default_vol = 1.0
    assert trail_len > 0, trail_len
    self._candles: Deque[Candle] = deque()
    self._width_ns = width_ns
    self._trail_len = trail_len
    self._default_vol = default_vol
    self._last_trade: Optional[PriceTime] = None

  @property
  def last_trade(self) -> Optional[PriceTime]:
    return self._last_trade

  @property
  def front(self) -> Optional[Candle]:
    return self._candles[0] if self._candles else None

  def is_full(self) -> bool:
    assert len(self._candles) <= self._trail_len + 1
    return len(self._candles) >= self._trail_len + 1

  def _start_candle(self, ts: Timestamp):
    if self._candles:
      if self.is_full():
        self._candles.pop()
      assert self.front.floor_ts(ts) >= self.front.end_ts

    candle = Candle(start_ts=ts, width_ns=self._width_ns)
    self._candles.appendleft(candle)

  def add_trade(self, trade: PriceTime):
    if not self._candles or not self.front.contains_ts(trade.ts):
      self._start_candle(trade.ts)

    assert self.front.contains_ts(trade.ts)
    assert self._last_trade is None or trade.ts >= self._last_trade.ts

    self.front.add_price(trade.price)
    self._last_trade = trade

  def eval(self) -> float:
    if not self.is_full():
      return self._default_vol

    highs = []
    lows = []
    total_ns = NSecs(0)

    for i in range(len(self._candles) - 1):
      cur = self._candles[i]
      prev = self._candles[i + 1]
      highs.append(max(cur.high, prev.high))
      lows.append(min(cur.low, prev.low))
      timespan = cur.end_ts - prev.start_ts
      assert timespan > 0, (cur, prev, timespan)
      total_ns += timespan

    lows = np.array(lows, dtype=float)
    highs = np.array(highs, dtype=float)
    assert lows.shape == highs.shape, (lows, highs)
    assert np.all(0 < lows <= highs), (lows, highs)

    log_price_diffs = np.log(highs / lows)
    assert np.all(log_price_diffs > 0), log_price_diffs

    numer = np.sum(log_price_diffs ** 2) * NS_PER_YEAR
    denom = 4.0 * np.log(2) * total_ns
    assert numer > 0 and denom > 0, (numer, denom)
    return np.sqrt(numer / denom)


class ConfidenceModel:

  def __init__(
      self,
      vol_model: VolatilityModel,
      *,
      min_conf: Confidence,
      min_slot_ns: NSecs = None,
  ):
    if min_slot_ns is None:
      min_slot_ns = scale_time(NS_PER_MS, 500)
    assert min_conf >= 0, min_conf
    assert min_slot_ns >= 0, min_slot_ns
    self._vol_model = vol_model
    self._min_conf = min_conf
    self._min_slot_ns: NSecs = min_slot_ns
    self._range_since_eval = HighLowTracker()

  @property
  def last_trade(self) -> PriceTime:
    return self._vol_model.last_trade

  def add_trade(self, trade: PriceTime):
    self._vol_model.add_trade(trade)
    self._range_since_eval.add_price(trade.price)

  def reset_price_range(self):
    self._range_since_eval.reset()

  def ns_since_last_trade(self, cur_ts: Timestamp) -> NSecs:
    last_ts = self._vol_model.last_trade.ts
    assert last_ts is not None, cur_ts
    delta = diff_timestamps(cur_ts, last_ts)
    assert delta > 0, (cur_ts, delta)
    return max(delta, self._min_slot_ns)

  def eval_at_time(self, ts: Timestamp) -> Confidence:
    conf = self.peek_at_time(ts)
    self.reset_price_range()
    return conf

  def peek_at_time(self, ts: Timestamp) -> Confidence:
    ns_since_last_trade = self.ns_since_last_trade(ts)
    years_since_last_trade = float(ns_since_last_trade) / NS_PER_YEAR

    # Calculate the volatility-model based confidence interval.
    vol = self._vol_model.eval()
    ci_bps = vol * np.sqrt(years_since_last_trade)
    ci_price = ci_bps * self._vol_model.last_trade.price

    # Now check it against the price range traded since the last evaluation.
    # This let's us flare out on microbursts.
    spread = self._range_since_eval.spread
    if spread is not None:
      ci_price = max(ci_price, spread / 2.0)

    return max(ci_price, self._min_conf)


class PricingModel:
  """
  PricingModel has a couple of free parameters

  candle_width_minutes:
  ncandles:
    are both passed into Volatility model above to set how wide the candlestick aggregation should
    be and how many candlesticks of history to use to estimate volatility. 1 minute candles and
    ncandles=20 seem to give reasonable results for the symbols I've looked at

  min_confidence_interval:
    is a hardcoded minimum confidence interval to use, to protect against the volatility model returning
    too low a value (for instance if we ONLY fill at a single price for a long time because we are ONLY
    working orders at that one price, volatility model could read 0...). This is going to want to be
    configured per symbol potentially, and should relate to the typical spread in the market.

  timeout_seconds:
    pricing model reports status "Trading" with price=last_trades_price and volatility * sqrt time
    increasing confidence interval on each slot until timeout_seconds have elapsed without a new trade
    at that point we publish status UNKNOWN. I think ~60s is a reasonable number to use for this
  """

  def __init__(
      self,
      conf_model: ConfidenceModel,
      *,
      timeout_ns: NSecs,
  ):
    self._conf_model = conf_model
    self._timeout_ns = timeout_ns
    self._status: Status = Status.UNKNOWN

  @property
  def last_trade(self) -> PriceTime:
    return self._conf_model.last_trade

  def add_trade(self, trade: PriceTime):
    self._conf_model.add_trade(trade)
    self._status: Status = Status.TRADING

  def is_trading(self) -> bool:
    trading = self._status == Status.TRADING
    assert trading or self._status == Status.UNKNOWN
    return trading

  def eval_at_time(self, ts: Timestamp) -> Optional[PriceConf]:
    ret = self.peek_at_time(ts)
    if ret is None:
      self._status = Status.UNKNOWN
    else:
      self._conf_model.reset_price_range()
    return ret

  def peek_at_time(self, ts: Timestamp) -> Optional[PriceConf]:
    ret = None
    if self.is_trading():
      last_trade = self.last_trade
      if ts - last_trade.ts <= self._timeout_ns:
        conf = self._conf_model.peek_at_time(ts)
        ret = PriceConf(last_trade.price, conf)
    return ret
