import numpy as np

NS_PER_US = 1000
NS_PER_MS = NS_PER_US * 1000
NS_PER_SEC = NS_PER_MS * 1000
NS_PER_MIN = NS_PER_SEC * 60
NS_PER_HOUR = NS_PER_MIN * 60
NS_PER_DAY = NS_PER_HOUR * 24
NS_PER_YEAR = NS_PER_DAY * 365


class Candle(object):

    def __init__(self, time, width_secs):
        self._width_ns = width_secs * NS_PER_SEC
        self.starttime = time // self._width_ns * self._width_ns
        self.endtime = self.starttime + self._width_ns
        self.open = None
        self.high = None
        self.low = None
        self.close = None
        self.ntrades = 0

    def add_price(self, price):
        if self.open is None:
            self.open = price
        if self.high is None or price > self.high:
            self.high = price
        if self.low is None or price < self.low:
            self.low = price
        self.close = price
        self.ntrades += 1

    def check_time(self, time):
        return time // self._width_ns * self._width_ns == self.starttime


class VolatilityModel(object):

    def __init__(self, candle_secs, ncandles, initial_volatility=1.0):
        self._candlelist = []
        self._candle_secs = candle_secs
        self._ncandles = ncandles
        self._initial_volatility = initial_volatility

    def add_trade(self, time, price):
        if not (self._candlelist and self._candlelist[0].check_time(time)):
            self._candlelist = [Candle(time, self._candle_secs)] + self._candlelist[:min(len(self._candlelist), self._ncandles)]
        self._candlelist[0].add_price(price)

    @property
    def volatility(self):
        if len(self._candlelist) < self._ncandles:
            return self._initial_volatility
        highs = np.zeros(len(self._candlelist)-1)
        lows = np.zeros(len(self._candlelist)-1)
        dts = np.zeros(len(self._candlelist)-1)
        for i in range(len(self._candlelist)-1):
            highs[i] = max(self._candlelist[i].high, self._candlelist[i+1].high)
            lows[i] = min(self._candlelist[i].low, self._candlelist[i+1].low)
            dts[i] = self._candlelist[i].endtime - self._candlelist[i+1].starttime
        assert np.sum(dts)>0
        v = 1.0/(4.0 * np.log(2)) * np.sum(np.log(highs / lows)**2) * NS_PER_YEAR / np.sum(dts)
        return np.sqrt(v)


class ConfidenceInterval(object):

    def __init__(self, candle_secs, ncandles, min_interval, min_slot_ms):
        self.vol_model = VolatilityModel(candle_secs, ncandles)
        self.min_interval = min_interval
        self.min_slot_ns = min_slot_ms * NS_PER_MS
        self._last_trade_time = 0
        self._last_trade_price = 0
        self._high_price_since_last_eval = None
        self._low_price_since_last_eval = None

    def add_trade(self, trade_time, price):
        self.vol_model.add_trade(trade_time, price)
        self._last_trade_time = trade_time
        self._last_trade_price = price
        if self._low_price_since_last_eval is None or price < self._low_price_since_last_eval:
            self._low_price_since_last_eval = price
        if self._high_price_since_last_eval is None or price > self._high_price_since_last_eval:
            self._high_price_since_last_eval = price

    def get_confidence_interval(self, eval_time):
        time_since_last_trade = eval_time - self._last_trade_time
        assert time_since_last_trade >= 0
        time_since_last_trade = max(time_since_last_trade, self.min_slot_ns)
        # calculate the volatility-model based confidence interval
        confidence_interval_bps = self.vol_model.volatility * np.sqrt(time_since_last_trade/NS_PER_YEAR)
        confidence_interval_price = max(confidence_interval_bps * self._last_trade_price, self.min_interval)
        # now check it against the price range traded since the last evaluation (this let's us flare out on microbursts)
        if self._low_price_since_last_eval is not None and self._high_price_since_last_eval is not None:
            confidence_interval_price = max(confidence_interval_price, (self._high_price_since_last_eval - self._low_price_since_last_eval)/2)
        self._low_price_since_last_eval = None
        self._high_price_since_last_eval = None
        return confidence_interval_price


class PricingModel(object):

    def __init__(
        self,
        *,
        # Match arg names from test_pricing_model.cpp:
        candle_secs=None,
        lookback=None,
        min_interval=None,
        min_slot_ms=None,
        timeout_ms=None,
    ):
        if lookback is None:
            lookback = 20
        if candle_secs is None:
            candle_secs = 60
        if timeout_ms is None:
            timeout_ms = 1000 * 60
        if min_slot_ms is None:
            min_slot_ms = 500
        if min_interval is None:
            min_interval = 0.01

        self.confidence_model = ConfidenceInterval(
            candle_secs=candle_secs,
            ncandles=lookback,
            min_interval=min_interval,
            min_slot_ms=min_slot_ms,
        )

        self.timeout_ns = timeout_ms * NS_PER_MS
        self._last_trade_price = 0
        self._last_trade_time = 0
        self.status = 'Unknown'

    @property
    def min_slot_ns(self):
        return self.confidence_model.min_slot_ns

    def add_trade(self, trade_time, price):
        self.confidence_model.add_trade(trade_time, price)
        self._last_trade_price = price
        self._last_trade_time = trade_time
        self.status = 'Trading'

    def evaluate(self, eval_time):
        price = 0
        confidence_interval = 0
        if self.status != 'Unknown':
            if eval_time - self._last_trade_time > self.timeout_ns:
                self.status = 'Unknown'
            else:
                confidence_interval = self.confidence_model.get_confidence_interval(eval_time)
                price = self._last_trade_price
        return price, confidence_interval, self.status == 'Trading'
