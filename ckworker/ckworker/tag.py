from cklib.logging import log
from cklib.graph.export import node_from_dict, node_to_dict


def core_tag_tasks_processor(message: dict) -> None:
    task_id = message.get("task_id")
    # task_name = message.get("task_name")
    # task_attrs = message.get("attrs", {})
    task_data = message.get("data", {})
    delete_tags = task_data.get("delete", [])
    update_tags = task_data.get("update", {})
    node_data = task_data.get("node")
    result = "done"
    extra_data = {}

    try:
        node = node_from_dict(node_data)
        for delete_tag in delete_tags:
            del node.tags[delete_tag]

        for k, v in update_tags.items():
            node.tags[k] = v

        node_dict = node_to_dict(node)
        extra_data.update({"data": node_dict})
    except Exception as e:
        log.exception("Error while updating tags")
        result = "error"
        extra_data["error"] = repr(e)

    reply_message = {
        "task_id": task_id,
        "result": result,
    }
    reply_message.update(extra_data)
    return reply_message
