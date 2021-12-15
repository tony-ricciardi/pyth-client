import numpy as np
NS_PER_YEAR = 365 * 24 * 60 * 60 * 10 ** 9
class candle(object):
    def __init__(self, time, candle_width_minutes):
        self._width_ns = int(candle_width_minutes*60*10**9)
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
    def __init__(self, candle_width_minutes, ncandles, initial_volatility=1.0):
        # volatility model works by aggregating tick level trade data into candles containing high/low price of trades
        # in that candle, along with start and end times of the candle.
        # Empty candles (where we have no fills) are NOT included and the model skips over them, using the last
        # "ncandles" populated candles to make its volatility estimate
        # candle_width_minute is the width in minutes of the aggregation "candles" used in volatility estimate
        # ncandles is the number of trailing candles to average over in volatility estimate
        # initial_volatility is the volatility to use (a high upper limit) when the model starts up and doesn't have
        # any data to use to begin with. defaults to 100% annualized which should be fine for all products. It is
        # really only used at startup
        self._candlelist = []
        self._candle_width_minutes = candle_width_minutes
        self._ncandles = ncandles
        self._initial_volatility = initial_volatility
    def add_trade(self, time, price):
        if not (self._candlelist and self._candlelist[0].check_time(time)):
            self._candlelist = [candle(time, self._candle_width_minutes)] + self._candlelist[:min(len(self._candlelist), self._ncandles)]
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
    def __init__(self, candle_width_minutes, ncandles, min_confidence_interval):
        self.vol_model = VolatilityModel(candle_width_minutes, ncandles)
        self.min_confidence_interval = min_confidence_interval
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
    def get_confidence_interval(self, eval_time, min_slot_time=500*10**6):
        time_since_last_trade = eval_time - self._last_trade_time
        assert time_since_last_trade >= 0
        time_since_last_trade = max(time_since_last_trade, min_slot_time)
        # calculate the volatility-model based confidence interval
        confidence_interval_bps = self.vol_model.volatility * np.sqrt(time_since_last_trade/NS_PER_YEAR)
        confidence_interval_price = max(confidence_interval_bps * self._last_trade_price, self.min_confidence_interval)
        # now check it against the price range traded since the last evaluation (this let's us flare out on microbursts)
        if self._low_price_since_last_eval is not None and self._high_price_since_last_eval is not None:
            confidence_interval_price = max(confidence_interval_price, (self._high_price_since_last_eval - self._low_price_since_last_eval)/2)
        self._low_price_since_last_eval = None
        self._high_price_since_last_eval = None
        return confidence_interval_price
class PricingModel(object):
    # PricingModel has a couple of free parameters
    #
    # candle_width_minutes
    # ncandles
    #       are both passed into Volatility model above to set how wide the candlestick aggregation should
    #       be and how many candlesticks of history to use to estimate volatility. 1 minute candles and
    #       ncandles=20 seem to give reasonable results for the symbols I've looked at
    #
    # min_confidence_interval
    #       is a hardcoded minimum confidence interval to use, to protect against the volatility model returning
    #       too low a value (for instance if we ONLY fill at a single price for a long time because we are ONLY
    #       working orders at that one price, volatility model could read 0...). This is going to want to be
    #       configured per symbol potentially, and should relate to the typical spread in the market.
    #
    # timeout_seconds
    #       pricing model reports status "Trading" with price=last_trades_price and volatility * sqrt time
    #       increasing confidence interval on each slot until timeout_seconds have elapsed without a new trade
    #       at that point we publish status UNKNOWN. I think ~60s is a reasonable number to use for this
    def __init__(self, candle_width_minutes, ncandles, min_confidence_interval, timeout_seconds):
        self.confidence_model = ConfidenceInterval(candle_width_minutes, ncandles, min_confidence_interval)
        self.timeout_ns = timeout_seconds * 10**9
        self._last_trade_price = 0
        self._last_trade_time = 0
        self.status = 'Unknown'
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
