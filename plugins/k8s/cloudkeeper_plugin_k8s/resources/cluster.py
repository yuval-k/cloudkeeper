from .common import KubernetesResource
from cklib.baseresources import BaseAccount
from typing import ClassVar
from dataclasses import dataclass


@dataclass(eq=False)
class KubernetesCluster(KubernetesResource, BaseAccount):
    kind: ClassVar[str] = "kubernetes_cluster"
