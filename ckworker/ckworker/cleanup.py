from cklib.logging import log
from cklib.args import ArgumentParser
from cklib.core.query import CoreGraph
from cklib.cleaner import Cleaner


def cleanup():
    """Run resource cleanup"""

    log.info("Running cleanup")

    cg = CoreGraph()

    query_filter = ""
    if ArgumentParser.args.collector and len(ArgumentParser.args.collector) > 0:
        clouds = '["' + '", "'.join(ArgumentParser.args.collector) + '"]'
        query_filter = f"and metadata.ancestors.cloud.id in {clouds} "
    query = (
        f"desired.clean == true and metadata.cleaned == false {query_filter}<-[0:]->"
    )

    graph = cg.graph(query)
    cleaner = Cleaner(graph)
    cleaner.cleanup()
    cg.patch_nodes(graph)


def add_args(arg_parser: ArgumentParser) -> None:
    Cleaner.add_args(arg_parser)
