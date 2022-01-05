import argparse
import glob
import inspect
import json
import logging
import logging.config
import os
import shutil
import subprocess
import time

from dataclasses import dataclass
from os import fdopen
from shutil import rmtree
from subprocess import DEVNULL, Popen, check_call, check_output
from tempfile import mkdtemp, mkstemp

import pytest


__all__ = [
    'BaseTest',
]

__this_file = os.path.abspath(__file__)
__this_dir = os.path.dirname(__this_file)


@dataclass(frozen=True)
class Args:

    inplace: bool = False
    verbose: bool = False
    tmpdir: str = None
    keeptmp: bool = None

    @property
    def loglevel(self):
        return logging.DEBUG if self.verbose else logging.INFO

    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser()
        parser.add_argument('--inplace', action='store_true')
        parser.add_argument('--verbose', '-v', action='store_true')
        parser.add_argument('--tmpdir')
        parser.add_argument('--keeptmp', action='store_true')
        return parser

    @classmethod
    def parse(cls):
        kwargs = vars(cls.get_parser().parse_args())
        return cls(**kwargs)


class BaseTest:

    _args = Args()
    _logger = logging.getLogger('pyth.tests')

    @property
    def args(self):
        return self._args

    @property
    def logger(self):
        return self._logger

    @classmethod
    def init_logger(cls, args: Args):
        logging.basicConfig(level=args.loglevel)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        funcs = cls.gen_test_funcs()
        for func in funcs:
            setattr(cls, func.__name__, func)

    @classmethod
    def gen_test_funcs(cls):
        paths = cls.get_input_paths()
        return [cls.get_test_method(path) for path in paths]

    @classmethod
    def get_subdir(cls) -> str:
        raise NotImplementedError()

    @classmethod
    def get_absdir(cls) -> str:
        path = os.path.abspath(inspect.getfile(cls))
        return os.path.join(os.path.dirname(path), cls.get_subdir())

    @classmethod
    def get_input_pattern(cls) -> str:
        raise NotImplementedError()

    @classmethod
    def get_input_paths(cls):
        pattern = os.path.join(cls.get_absdir(), cls.get_input_pattern())
        return glob.glob(pattern)

    @classmethod
    def get_output_path(cls, input_path: str) -> str:
        base, _ = os.path.splitext(input_path)
        return base + '.result'

    @classmethod
    def get_test_id(cls, path: str) -> str:
        test_id, _ = os.path.splitext(os.path.basename(path))
        return test_id

    @classmethod
    def get_test_method(cls, input_path: str):

        # tmp_path is a builtin pytest fixture (type pathlib.Path):
        # https://docs.pytest.org/en/6.2.x/reference.html#std-fixture-tmp_path
        def test_func(self: BaseTest, tmp_path: str):
            output_path = self.get_output_path(input_path)
            self.run_test(input_path, output_path, str(tmp_path))

        test_id = cls.get_test_id(input_path)
        test_func.__name__ = 'test_' + test_id
        return test_func

    @classmethod
    def main(cls):
        cls._args = cls._args.parse()
        cls.init_logger(cls._args)
        cls().run_tests()

    def run_tests(self):
        clsname = self.__class__.__name__
        tmp_root = mkdtemp(dir=self.args.tmpdir)
        try:
            for name, member in inspect.getmembers(self):
                if name.startswith('test_') and callable(member):
                    self.logger.info(f'running {clsname}.{name}')
                    tmp_path = os.path.join(tmp_root, name)
                    os.mkdir(tmp_path)
                    member(tmp_path=tmp_path)
        finally:
            if not self.args.keeptmp:
                shutil.rmtree(tmp_root)

    def get_subprocess_args(self, input_path: str, tmp_path: str):
        cmd = 'test_' + self.get_subdir()
        return [cmd, input_path]

    def gen_output(self, input_path: str, tmp_path: str) -> str:
        args = self.get_subprocess_args(input_path, tmp_path)
        self.logger.debug(' '.join(args))
        output = subprocess.check_output(args)
        return output.decode()

    def get_expected_output(self, output_path: str):
        with open(output_path, 'r') as f:
            return f.read()

    def run_test(self, input_path: str, output_path: str, tmp_path: str):
        expected = self.get_expected_output(output_path)
        actual = self.gen_output(input_path, tmp_path)

        if self.args.inplace:
            if actual != expected:
                with open(output_path, 'w') as f:
                    f.write(actual)
        else:
            assert actual == expected


PRODUCTS = {
    'BTC': {
        'symbol': 'BTC/USD',
        'asset_type': 'Crypto',
        'country': 'US',
        'quote_currency': 'USD',
        'tenor': 'Spot',
    },
    'ETH': {
        'symbol': 'ETH/USD',
        'asset_type': 'Crypto',
        'country': 'US',
        'quote_currency': 'USD',
        'tenor': 'Spot',
    },
    'LTC': {
        'symbol': 'LTC/USD',
        'asset_type': 'Crypto',
        'country': 'US',
        'quote_currency': 'USD',
        'tenor': 'Spot',
    },
}


@pytest.fixture(scope='session')
def solana_test_validator():

    ledger_dir = mkdtemp(prefix='stv_')
    cmd = [
        'solana-test-validator',
        '--rpc-port', '8899',
        '--ledger', ledger_dir,
    ]
    kwargs = {
        'stdin': DEVNULL,
        'stdout': DEVNULL,
        'stderr': DEVNULL,
    }
    with Popen(cmd, **kwargs) as p:
        time.sleep(3)
        yield
        p.terminate()
    rmtree(ledger_dir)


@pytest.fixture(scope='session')
def solana_keygen():

    cfg_dir = mkdtemp(prefix='cfg_')
    path = os.path.join(cfg_dir, 'id.json')
    cmd = ['solana-keygen', 'new', '--no-passphrase', '--outfile', path]
    output = check_output(cmd)
    output = output.decode('ascii')
    output = output.splitlines()
    output = [line for line in output if 'pubkey' in line][0]
    output = output.split('pubkey: ')[1]
    yield output, path
    rmtree(cfg_dir)


@pytest.fixture(scope='session')
def solana_airdrop(solana_test_validator, solana_keygen):

    cmd = [
        'solana', 'airdrop', '100', solana_keygen[0],
        '--commitment', 'finalized',
        '--url', 'localhost',
        '--keypair', solana_keygen[1],
    ]
    check_call(cmd)


@pytest.fixture(scope='session')
def solana_program_deploy(
    solana_test_validator, solana_keygen, solana_airdrop
):

    cmd = [
        'solana', 'program', 'deploy',
        os.path.abspath(
            os.path.join(__this_dir, '..', '..', 'target', 'oracle.so')
        ),
        '--commitment', 'finalized',
        '--url', 'localhost',
        '--keypair', solana_keygen[1],
    ]
    output = check_output(cmd)
    output = output.decode('ascii')
    output = output.splitlines()
    output = [line for line in output if 'Program Id' in line][0]
    output = output.split('Program Id: ')[1]
    return output


@pytest.fixture(scope='session')
def pyth_dir():

    path = mkdtemp(prefix='pythd_')
    yield path
    rmtree(path)


@pytest.fixture(scope='session')
def pyth_publish_key(solana_keygen, pyth_dir):

    path = os.path.join(pyth_dir, 'publish_key_pair.json')
    os.symlink(solana_keygen[1], path)


@pytest.fixture(scope='session')
def pyth_program_key(solana_program_deploy, pyth_dir):

    pyth_path = os.path.join(pyth_dir, 'program_key.json')
    with open(pyth_path, 'w') as f:
        f.write(solana_program_deploy)


@pytest.fixture(scope='session')
def pyth_init_mapping(
    solana_test_validator, pyth_dir, pyth_publish_key, pyth_program_key
):

    cmd = [
        'pyth_admin', 'init_mapping',
        '-r', 'localhost',
        '-k', pyth_dir,
        '-c', 'finalized',
    ]
    check_call(cmd)


@pytest.fixture(scope='session')
def pyth_add_product(solana_test_validator, pyth_dir, pyth_init_mapping):

    result = {}
    for product in PRODUCTS.keys():
        cmd = [
            'pyth_admin', 'add_product',
            '-r', 'localhost',
            '-k', pyth_dir,
            '-c', 'finalized',
        ]
        output = check_output(cmd)
        output = output.decode('ascii')
        output = output.splitlines()
        result[product] = output[0]
    return result


@pytest.fixture(scope='session')
def pyth_init_product(solana_test_validator, pyth_dir, pyth_add_product):

    products = []
    for product in pyth_add_product.keys():
        products.append({
            'account': pyth_add_product[product],
            'attr_dict': PRODUCTS[product],
        })
    fd, path = mkstemp(suffix='.json', prefix='products_')
    with fdopen(fd, 'w') as f:
        json.dump(products, f)
    cmd = [
        'pyth_admin', 'upd_product', path,
        '-r', 'localhost',
        '-k', pyth_dir,
        '-c', 'finalized',
    ]
    check_call(cmd)
    os.remove(path)
    return pyth_add_product


@pytest.fixture(scope='session')
def pyth_add_price(solana_test_validator, pyth_dir, pyth_init_product):

    result = {}
    for product, key in pyth_init_product.items():
        cmd = [
            'pyth_admin', 'add_price',
            key, 'price', '-e', '-5',
            '-r', 'localhost',
            '-k', pyth_dir,
            '-c', 'finalized',
            '-n',
        ]
        output = check_output(cmd)
        output = output.decode('ascii')
        output = output.splitlines()
        result[product] = output[0]
    return result


@pytest.fixture(scope='session')
def pyth_add_publisher(
    solana_test_validator, solana_keygen, pyth_dir, pyth_add_price
):

    for product, key in pyth_add_price.items():
        cmd = [
            'pyth_admin', 'add_publisher',
            solana_keygen[0], key,
            '-r', 'localhost',
            '-k', pyth_dir,
            '-c', 'finalized',
            '-n',
        ]
        check_call(cmd)
    return pyth_add_price


@pytest.fixture(scope='function')
def pyth_init_price(solana_test_validator, pyth_dir, pyth_add_publisher):

    for product, key in pyth_add_publisher.items():
        cmd = [
            'pyth_admin', 'init_price',
            key, '-e', '-5',
            '-r', 'localhost',
            '-k', pyth_dir,
            '-c', 'finalized',
            '-n',
        ]
        check_call(cmd)
    return pyth_add_publisher


@pytest.fixture(scope='session')
def pythd(solana_test_validator, pyth_dir):

    cmd = [
        'pythd',
        '-r', 'localhost',
        '-k', pyth_dir,
        '-x',
        '-m', 'finalized',
        '-d',
    ]
    kwargs = {
        'stdin': DEVNULL,
        'stdout': DEVNULL,
        'stderr': DEVNULL,
    }
    with Popen(cmd, **kwargs) as p:
        time.sleep(3)
        yield
        p.terminate()
