import os
from cklib.args import get_arg_parser, ArgumentParser
from cklib.logging import add_args as logging_add_args
from cklib.jwt import add_args as jwt_add_args


def test_args():
    assert ArgumentParser.args.does_not_exist is None

    os.environ["CLOUDKEEPER_PSK"] = "changeme"
    arg_parser = get_arg_parser()
    logging_add_args(arg_parser)
    jwt_add_args(arg_parser)
    arg_parser.parse_args()
    assert ArgumentParser.args.verbose is False
    assert ArgumentParser.args.psk == "changeme"

    os.environ["CLOUDKEEPER_PSK"] = ""
    os.environ["CLOUDKEEPER_VERBOSE"] = "true"
    os.environ["CLOUDKEEPER_TEST_INT"] = "123"
    os.environ["CLOUDKEEPER_TEST_LIST0"] = "foobar"
    arg_parser = get_arg_parser()
    logging_add_args(arg_parser)
    jwt_add_args(arg_parser)
    arg_parser.add_argument(
        "--test-int",
        dest="test_int",
        type=int,
        default=0,
    )
    arg_parser.add_argument(
        "--test-list",
        dest="test_list",
        type=str,
        default=[],
        nargs="+",
    )

    arg_parser.parse_args()
    assert ArgumentParser.args.verbose is True
    assert ArgumentParser.args.psk is None
    assert ArgumentParser.args.test_int == 123
    assert ArgumentParser.args.test_list[0] == "foobar"
