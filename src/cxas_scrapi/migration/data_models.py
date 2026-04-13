"""Data models for the Intermediate Representation (IR) of DFCX agents."""

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MigrationStatus(str, enum.Enum):
    """Represents the status of a migration component."""

    COMPILED = "Compiled"
    GENERATED = "Generated"
    DEPLOYED = "Deployed"
    FAILED = "Failed"
    ERROR = "Error"
    PENDING = "Pending"


# --- Source DFCX Models ---


class DFCXPageModel(BaseModel):
    """Represents a Page in a Flow."""

    page_id: str
    page_data: Dict[str, Any]


class DFCXFlowModel(BaseModel):
    """Represents a Flow with its Pages."""

    flow: Dict[str, Any]
    pages: List[DFCXPageModel] = Field(default_factory=list)


class DFCXAgentIR(BaseModel):
    """Represents the full extracted state of a DFCX Agent."""

    name: str
    display_name: str
    default_language_code: str
    intents: List[Dict[str, Any]] = Field(default_factory=list)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    entity_types: List[Dict[str, Any]] = Field(default_factory=list)
    webhooks: List[Dict[str, Any]] = Field(default_factory=list)
    flows: List[DFCXFlowModel] = Field(default_factory=list)
    playbooks: List[Dict[str, Any]] = Field(default_factory=list)
    generative_settings: Optional[Dict[str, Any]] = None


# --- Target Migration IR Models ---


class IRMetadata(BaseModel):
    """Metadata for the migration target."""

    app_name: str
    app_id: Optional[str] = None  # From target_app_uuid
    app_resource_name: Optional[str] = None
    default_model: str = "gemini-2.5-flash-001"


class IRTool(BaseModel):
    """Represents a tool in the target IR."""

    id: str  # Short ID (e.g., "tool_billing")
    name: str  # Full resource name (projects/.../tools/...)
    type: str  # "TOOLSET", "TOOL", "PYTHON"
    payload: Dict[str, Any]
    operation_ids: List[str] = Field(default_factory=list)
    status: MigrationStatus = MigrationStatus.COMPILED


class IRAgent(BaseModel):
    """Represents a Generative Agent (Playbook or Flow) in the target IR."""

    type: str  # "FLOW", "PLAYBOOK"
    display_name: str
    description: Optional[str] = None
    instruction: str  # The generated PIF XML
    tools: List[str] = Field(default_factory=list)  # Resource names
    toolsets: List[Dict[str, Any]] = Field(
        default_factory=list
    )  # [{"toolset": ..., "toolIds": []}]
    model_settings: Dict[str, Any] = Field(default_factory=dict)
    raw_data: Optional[Dict[str, Any]] = None  # Original DFCX data
    blueprint: Optional[Dict[str, Any]] = None  # Used by Flows
    callbacks: Optional[Dict[str, Any]] = None  # Used by Flows
    status: MigrationStatus = MigrationStatus.COMPILED
    resource_name: Optional[str] = None  # Populated after deployment


class MigrationIR(BaseModel):
    """The full state of the migration offline workspace."""

    metadata: IRMetadata
    parameters: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    tools: Dict[str, IRTool] = Field(default_factory=dict)
    agents: Dict[str, IRAgent] = Field(default_factory=dict)
    routing_edges: List[Dict[str, Any]] = Field(default_factory=list)
    test_runs: Dict[str, Any] = Field(default_factory=dict)
    optimization_logs: Dict[str, Any] = Field(default_factory=dict)
