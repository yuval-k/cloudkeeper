import logging
from abc import ABC
from argparse import Namespace
from datetime import datetime, timezone, timedelta
from time import sleep
from typing import Dict, List, Tuple

from arango import ArangoServerError, ArangoClient
from arango.database import StandardDatabase
from dateutil.parser import parse
from requests.exceptions import ConnectionError as ArangoConnectionError

from core.analytics import AnalyticsEventSender
from core.db import SystemData
from core.db.arangodb_extensions import ArangoHTTPClient
from core.db.async_arangodb import AsyncArangoDB
from core.db.configdb import config_entity_db
from core.db.entitydb import EventEntityDb
from core.db.graphdb import ArangoGraphDB, GraphDB, EventGraphDB
from core.db.jobdb import job_db
from core.db.modeldb import ModelDb, model_db
from core.db.runningtaskdb import running_task_db
from core.db.subscriberdb import subscriber_db
from core.error import NoSuchGraph
from core.model.adjust_node import AdjustNode
from core.model.typed_model import to_js, from_js
from core.util import Periodic, utc, shutdown_process, uuid_str

log = logging.getLogger(__name__)


class DbAccess(ABC):
    def __init__(
        self,
        arango_database: StandardDatabase,
        event_sender: AnalyticsEventSender,
        adjust_node: AdjustNode,
        model_name: str = "model",
        subscriber_name: str = "subscribers",
        running_task_name: str = "running_tasks",
        job_name: str = "jobs",
        config_entity: str = "configs",
        update_outdated: timedelta = timedelta(minutes=30),
    ):
        self.event_sender = event_sender
        self.database = arango_database
        self.db = AsyncArangoDB(arango_database)
        self.adjust_node = adjust_node
        self.model_db = EventEntityDb(model_db(self.db, model_name), event_sender, model_name)
        self.subscribers_db = EventEntityDb(subscriber_db(self.db, subscriber_name), event_sender, subscriber_name)
        self.running_task_db = running_task_db(self.db, running_task_name)
        self.job_db = job_db(self.db, job_name)
        self.config_entity_db = config_entity_db(self.db, config_entity)
        self.graph_dbs: Dict[str, GraphDB] = {}
        self.update_outdated = update_outdated
        self.cleaner = Periodic("outdated_updates_cleaner", self.check_outdated_updates, timedelta(seconds=60))

    async def start(self) -> None:
        await self.model_db.create_update_schema()
        await self.subscribers_db.create_update_schema()
        await self.running_task_db.create_update_schema()
        await self.job_db.create_update_schema()
        await self.config_entity_db.create_update_schema()
        for graph in self.database.graphs():
            log.info(f'Found graph: {graph["name"]}')
            db = self.get_graph_db(graph["name"])
            await db.create_update_schema()
        await self.cleaner.start()

    async def create_graph(self, name: str) -> GraphDB:
        db = self.get_graph_db(name, no_check=True)
        await db.create_update_schema()
        return db

    async def delete_graph(self, name: str) -> None:
        db = self.database
        if db.has_graph(name):
            db.delete_graph(name, drop_collections=True, ignore_missing=True)
            db.delete_collection(f"{name}_in_progress", ignore_missing=True)
            db.delete_view(f"search_{name}", ignore_missing=True)
            self.graph_dbs.pop(name, None)

    async def list_graphs(self) -> List[str]:
        return [a["name"] for a in self.database.graphs() if not a["name"].endswith("_hs")]

    def get_graph_db(self, name: str, no_check: bool = False) -> GraphDB:
        if name in self.graph_dbs:
            return self.graph_dbs[name]
        else:
            if not no_check and not self.database.has_graph(name):
                raise NoSuchGraph(name)
            graph_db = ArangoGraphDB(self.db, name, self.adjust_node)
            event_db = EventGraphDB(graph_db, self.event_sender)
            self.graph_dbs[name] = event_db
            return event_db

    def get_model_db(self) -> ModelDb:
        return self.model_db

    async def check_outdated_updates(self) -> None:
        now = datetime.now(timezone.utc)
        for db in self.graph_dbs.values():
            for update in await db.list_in_progress_updates():
                created = datetime.fromtimestamp(parse(update["created"]).timestamp(), timezone.utc)
                if (now - created) > self.update_outdated:
                    batch_id = update["id"]
                    log.warning(f"Given update is too old: {batch_id}. Will abort the update.")
                    await db.abort_update(batch_id)

    # Only used during startup.
    # Note: this call uses sleep and will block the current executing thread!
    @classmethod
    def connect(cls, args: Namespace, timeout: timedelta) -> Tuple[bool, SystemData, StandardDatabase]:
        deadline = utc() + timeout
        db = cls.client(args)

        def system_data() -> Tuple[bool, SystemData]:
            def insert_system_data() -> SystemData:
                system = SystemData(uuid_str(), utc(), 1)
                log.info(f"Create new system data entry: {system}")
                db.insert_document("system_data", {"_key": "system", **to_js(system)}, overwrite=True)
                return system

            if not db.has_collection("system_data"):
                db.create_collection("system_data")

            sys_js = db.collection("system_data").get("system")
            return (True, insert_system_data()) if not sys_js else (False, from_js(sys_js, SystemData))

        while True:
            try:
                db.echo()
                created, sys_data = system_data()
                return created, sys_data, db
            except ArangoServerError as ex:
                if utc() > deadline:
                    log.error("Can not connect to database. Giving up.")
                    shutdown_process(1)
                log.warning(f"Problem accessing the graph database: {ex}. Trying again in 5 seconds.")
                sleep(5)
            except ArangoConnectionError:
                log.warning("Can not access database. Trying again in 5 seconds.")
                sleep(5)

    @staticmethod
    def client(args: Namespace) -> StandardDatabase:
        if args.graphdb_type not in "arangodb":
            log.fatal(f"Unknown Graph DB type {args.graphdb_type}")
            shutdown_process(1)

        http_client = ArangoHTTPClient(args.graphdb_request_timeout, not args.graphdb_no_ssl_verify)
        client = ArangoClient(hosts=args.graphdb_server, http_client=http_client)
        return client.db(args.graphdb_database, username=args.graphdb_username, password=args.graphdb_password)
