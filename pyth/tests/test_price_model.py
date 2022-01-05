from pyth.tests.conftest import BaseTest

from pyth.price_model import PricingModel, NS_PER_SEC

import datetime as dt
import json
import os

import numpy as np
import pandas as pd

from collections import OrderedDict


__all__ = [
    'TestPriceModel',
]


Timestamp = np.uint64
Price = np.int64
Interval = np.float64


TRADE_DTYPES = (
    ('timestamp', Timestamp),
    ('price', Price),
)

EVAL_DTYPES = (
    ('timestamp', Timestamp),
    ('price', Price),
    ('interval', Interval),
)


def dt_to_ns(datetime: dt.datetime):
    return int(datetime.timestamp() * NS_PER_SEC)


def to_df(dtypes, cols):
    dtypes = OrderedDict(dtypes)
    assert len(dtypes) == len(cols)
    cols = OrderedDict(zip(dtypes, cols))
    df = pd.DataFrame.from_dict(cols)
    for key, dtype in dtypes.items():
        assert df[key].dtype == dtype, (key, dtype, df[key].dtype)
    return df


def ts_range(start, end, step):
    assert 0 < step < start < end
    return np.arange(start, end, step, dtype=Timestamp)


def gen_eval_df(
    model: PricingModel,
    trades: pd.DataFrame,
    start_ts: int,
    end_ts: int,
) -> pd.DataFrame:

    eval_times = ts_range(start_ts, end_ts, model.min_slot_ns)
    eval_prices = np.zeros(len(eval_times), dtype=Price)
    eval_confs = np.zeros(len(eval_times), dtype=Interval)
    trade_times = trades['timestamp']
    trade_prices = trades['price']

    trade_i = 0
    for eval_i, eval_time in enumerate(eval_times):
        while trade_i < len(trade_times) and eval_time > trade_times[trade_i]:
            model.add_trade(trade_times[trade_i], price=trade_prices[trade_i])
            trade_i += 1
        price, conf, _valid = model.evaluate(eval_time)
        eval_prices[eval_i] = price
        eval_confs[eval_i] = conf

    return to_df(EVAL_DTYPES, [eval_times, eval_prices, eval_confs])


class TestPriceModel(BaseTest):

    @classmethod
    def get_subdir(cls) -> str:
        return 'price_model'

    @classmethod
    def get_input_pattern(cls) -> str:
        return '*.json'

    def get_subprocess_args(self, input_path: str, tmp_path: str):
        config, trades, evals = self.load_inputs(input_path, tmp_path)

        cmd_args = ['test_price_model']
        for k, v in config.items():
            cmd_args.extend(('--' + k, v))

        for col, arg in (
            (trades['timestamp'], 'trade-times'),
            (trades['price'], 'trade-prices'),
            (evals['timestamp'], 'eval-times'),
            (evals['price'], 'eval-prices'),
            (evals['interval'], 'eval-intervals'),
        ):
            path = os.path.join(tmp_path, arg + '.bin')
            cmd_args.extend(('--' + arg, path))
            with open(path, 'wb') as f:
                f.write(col.values.tobytes())

        return cmd_args

    def get_expected_output(self, output_path: str):
        # No output, just internal assertions.
        return ''

    def load_inputs(self, input_path: str, tmp_path: str):
        input_dir, test_name = os.path.split(os.path.splitext(input_path)[0])
        output_dir = input_dir if self.args.inplace else tmp_path

        with open(input_path) as f:
            config = json.load(f)
            assert isinstance(config, dict)

        seed = config.pop('seed', None)
        rand = np.random.RandomState(int(test_name) if seed is None else seed)

        def pop_int(key: str, default: int):
            val = config.pop(key, default)
            assert isinstance(val, int), (key, val, default)
            return val

        def pop_uint(key: str, default: int):
            val = pop_int(key, default)
            assert val > 0, (key, val, default)
            return val

        def pop_ufloat(key: str, default: float):
            val = config.pop(key, default)
            assert isinstance(val, (int, float)), (key, val, default)
            assert val > 0, (key, val, default)
            return val

        def uniform(low: float, high: float, n: int, dtype):
            assert low < high
            assert n > 0
            return rand.uniform(low, high, n).astype(dtype)

        def rand_timestamp():
            return dt_to_ns(dt.datetime(
                year=2020 + rand.randint(0, 3),
                month=rand.randint(1, 13),
                day=rand.randint(1, 28),
                hour=rand.randint(0, 24),
                minute=rand.randint(0, 60),
                second=rand.randint(0, 60),
            ))

        trade_csv = os.path.join(input_dir, test_name + '.trades.csv')
        if not os.path.exists(trade_csv):
            trade_csv = os.path.join(output_dir, test_name + '.trades.csv')
            self.logger.info('generating ' + trade_csv)

            total_secs = pop_uint('trade_seconds', 30 * 60)
            count = total_secs * pop_uint('trades_per_sec', 100)
            total_ns = total_secs * NS_PER_SEC

            times = uniform(0, total_ns, count, Timestamp)
            times.sort()
            times[0] = 0
            times[-1] = total_ns
            times += pop_uint('trade_start_ts', rand_timestamp())

            price_mid = pop_uint('trade_mid_price', 100)
            price_ivl = pop_ufloat('trade_price_interval', price_mid / 10.)
            prices = uniform(-price_ivl, price_ivl, count, Price)
            prices += price_mid

            trades = to_df(TRADE_DTYPES, [times, prices])
            trades.to_csv(trade_csv, index=False)

        trades = pd.read_csv(trade_csv, dtype=dict(TRADE_DTYPES))
        trade_times = trades['timestamp'].values
        assert np.all(trade_times[1:] > trade_times[:-1])

        eval_csv = os.path.join(input_dir, test_name + '.evals.csv')
        if not os.path.exists(eval_csv):
            eval_csv = os.path.join(output_dir, test_name + '.evals.csv')
            self.logger.info('generating ' + eval_csv)

            def add_rand_ns(base):
                interval = (trade_times[-1] - trade_times[0]) // 10
                assert interval > 0
                assert isinstance(base, Timestamp)
                return int(base) + rand.randint(-interval, interval + 1)

            start_ts = pop_uint('eval_start_ts', add_rand_ns(trade_times[0]))
            end_ts = pop_uint('eval_end_ts', add_rand_ns(trade_times[-1]))

            model = PricingModel(**{
                k.replace('-', '_'): v
                for k, v in config.items()
                if k != 'conf-tolerance'  # only for C++ assertions
            })

            evals = gen_eval_df(model, trades, start_ts, end_ts)
            evals.to_csv(eval_csv, index=False)

        evals = pd.read_csv(eval_csv, dtype=dict(EVAL_DTYPES))
        eval_times = evals['timestamp'].values
        assert np.all(eval_times[1:] >= eval_times[:-1])
        assert np.all(evals['interval'] >= 0)

        return config, trades, evals


if __name__ == '__main__':
    TestPriceModel.main()
