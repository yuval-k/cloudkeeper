import logging
from abc import ABC, abstractmethod
from typing import Optional, List

from core.model.graph_access import Section
from core.model.model import DateTimeKind, DurationKind
from core.model.resolve_in_graph import NodePath
from core.types import Json
from core.util import value_in_path, from_utc

log = logging.getLogger(__name__)


class AdjustNode(ABC):
    @abstractmethod
    def adjust(self, json: Json) -> Json:
        pass


class NoAdjust(AdjustNode):
    def adjust(self, json: Json) -> Json:
        return json


class DirectAdjuster(AdjustNode):

    # this holds a datetime
    expires_value = [[Section.reported, "tags", "cloudkeeper:expires"]]

    # this holds a relative timedelta
    expiration_values = [
        [Section.reported, "tags", "cloudkeeper:expiration"],
        [Section.reported, "tags", "expiration"],
    ]

    def adjust(self, json: Json) -> Json:
        def first_matching(paths: List[List[str]]) -> Optional[str]:
            for path in paths:
                value: Optional[str] = value_in_path(json, path)
                if value:
                    return value
            return None

        try:
            expires_tag = first_matching(self.expires_value)
            expires: Optional[str] = None
            if expires_tag:
                expires = DateTimeKind.from_datetime(expires_tag)
            else:
                expiration_tag = first_matching(self.expiration_values)
                if expiration_tag and expires_tag != "never" and DurationKind.DurationRe.fullmatch(expiration_tag):
                    ctime_str = value_in_path(json, NodePath.reported_ctime)
                    if ctime_str:
                        ctime = from_utc(ctime_str)
                        expires = DateTimeKind.from_duration(expiration_tag, ctime)

            if expires:
                if "metadata" not in json:
                    json["metadata"] = {}
                json["metadata"]["expires"] = expires
        except Exception as ex:
            log.debug(f"Could not parse expiration: {ex}")
        # json is mutated to save memory
        return json
