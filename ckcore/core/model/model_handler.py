import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List

from plantuml import PlantUML

from core.async_extensions import run_async
from core.db.modeldb import ModelDb
from core.model.model import Model, Kind, ComplexKind
from core.util import exist

log = logging.getLogger(__name__)


class ModelHandler(ABC):
    @abstractmethod
    async def load_model(self) -> Model:
        pass

    @abstractmethod
    async def uml_image(self, show_packages: Optional[List[str]] = None, output: str = "svg") -> bytes:
        pass

    @abstractmethod
    async def update_model(self, kinds: List[Kind]) -> Model:
        pass


class ModelHandlerDB(ModelHandler):
    def __init__(self, db: ModelDb, plantuml_server: str):
        self.db = db
        self.plantuml_server = plantuml_server
        self.__loaded_model: Optional[Model] = None

    async def load_model(self) -> Model:
        if self.__loaded_model:
            return self.__loaded_model
        else:
            kinds = [kind async for kind in self.db.all()]
            model = Model.from_kinds(list(kinds))
            self.__loaded_model = model
            return model

    async def uml_image(self, show_packages: Optional[List[str]] = None, output: str = "svg") -> bytes:
        assert output in ("svg", "png"), "Only svg and png is supported!"
        model = await self.load_model()
        graph = model.graph()

        def node_visible(key: str) -> bool:
            if show_packages is None:
                return True
            else:
                k: Kind = graph.nodes[key]["data"]
                return exist(k.fqn.startswith, show_packages)

        def edge_visible(edge: Tuple[str, str]) -> bool:
            return node_visible(edge[0]) and node_visible(edge[1])

        def class_node(cpx: ComplexKind) -> str:
            props = "\n".join([f"+ {p.name}: {p.kind}" for p in cpx.properties])
            return f"class {cpx.fqn} {{\n{props}\n}}"

        def class_inheritance(edge: Tuple[str, str]) -> str:
            return f"{edge[1]} <|--- {edge[0]}"

        nodes = "\n".join([class_node(graph.nodes[node]["data"]) for node in graph.nodes() if node_visible(node)])
        edges = "\n".join([class_inheritance(edge) for edge in graph.edges() if edge_visible(edge)])
        puml = PlantUML(f"{self.plantuml_server}/{output}/")
        return await run_async(puml.processes, f"@startuml\n{nodes}\n{edges}\n@enduml")  # type: ignore

    async def update_model(self, kinds: List[Kind]) -> Model:
        # load existing model
        model = await self.load_model()
        # make sure the update is valid
        updated = model.update_kinds(kinds)
        # store all updated kinds
        await self.db.update_many(kinds)
        # unset loaded model
        self.__loaded_model = updated
        return updated
