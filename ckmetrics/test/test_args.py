from cklib.args import ArgumentParser
from ckmetrics.__main__ import add_args


def test_args():
    arg_parser = ArgumentParser(
        description="Cloudkeeper Metrics Exporter", env_args_prefix="CKMETRICS_"
    )
    add_args(arg_parser)
    arg_parser.parse_args()
    assert ArgumentParser.args.ckcore_uri == "http://localhost:8900"
    assert ArgumentParser.args.ckcore_ws_uri == "ws://localhost:8900"
    assert ArgumentParser.args.ckcore_graph == "ck"
    assert ArgumentParser.args.timeout == 300
