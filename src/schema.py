"""Extraction schema for reporting tickets (Bug + Change Request).

Domain pipeline:
  SAP Fiori  →  Databricks (Data Pull)  →  Power BI report
                     ↕
              Financial specification

Fix / change deployment rule:
  implement fix  →  deploy to DEV  →  approval  →  deploy to PROD
  (never skip straight to PROD)

A ticket is usually filed against a report that exists on DEV and/or PROD.
Root-cause analysis must reconcile:
  - SAP Fiori vs Databricks
  - Databricks vs Power BI
  - Power BI report vs specification (report may simply not match requirements)
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TicketType(str, Enum):
    BUG = "bug"
    CHANGE_REQUEST = "change_request"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DeployStage(str, Enum):
    """Report environment the ticket refers to."""

    DEV = "dev"
    PROD = "prod"
    BOTH = "both"
    UNKNOWN = "unknown"


class PipelineStage(str, Enum):
    """Where the discrepancy / request is primarily located."""

    SAP_FIORI = "sap_fiori"
    DATABRICKS = "databricks"
    POWER_BI_REPORT = "power_bi_report"
    SPECIFICATION = "specification"
    UNKNOWN = "unknown"


class IssueCategory(str, Enum):
    DATA_MISMATCH = "data_mismatch"
    SPEC_MISMATCH = "spec_mismatch"
    REFRESH_FAILURE = "refresh_failure"
    TRANSFORMATION_LOGIC = "transform_logic"
    FILTER_RLS = "filter_rls"
    PERFORMANCE = "performance"
    ENHANCEMENT = "enhancement"
    OTHER = "other"


class TeamRole(str, Enum):
    REPORT_DEVELOPER = "report_developer"
    FINANCIAL_ANALYST = "financial_analyst"
    DATA_PULL = "data_pull"
    UNKNOWN = "unknown"


class DeploymentStatus(str, Enum):
    """Where the fix/change sits in the deploy pipeline."""

    NOT_STARTED = "not_started"
    IN_DEVELOPMENT = "in_development"
    DEPLOYED_TO_DEV = "deployed_to_dev"
    PENDING_APPROVAL = "pending_approval"
    APPROVED_FOR_PROD = "approved_for_prod"
    DEPLOYED_TO_PROD = "deployed_to_prod"
    UNKNOWN = "unknown"


class ReportRef(BaseModel):
    """Power BI report the ticket is about."""

    name: Optional[str] = Field(default=None, description="Report / .pbix name")
    deploy_stage: DeployStage = Field(
        description="DEV, PROD, both, or unknown"
    )
    dataset_name: Optional[str] = Field(
        default=None, description="Power BI dataset name if mentioned"
    )


class SapFioriRef(BaseModel):
    """SAP Fiori source used by the report / data pull."""

    app_name: Optional[str] = Field(
        default=None, description="Fiori app / tile name if mentioned"
    )
    transaction_or_cds: Optional[str] = Field(
        default=None,
        description="SAP transaction, CDS view, or extractor id if mentioned",
    )


class SpecificationRef(BaseModel):
    """Business specification the report must follow."""

    spec_id: Optional[str] = Field(
        default=None, description="Spec id/code if mentioned, e.g. SPEC-FIN-014"
    )
    version: Optional[str] = Field(default=None, description="Spec version if mentioned")
    title: Optional[str] = Field(default=None, description="Spec title if mentioned")


class Ownership(BaseModel):
    """Who owns which part of the report lifecycle."""

    report_developer: Optional[str] = Field(
        default=None,
        description="Developer responsible for the Power BI report",
    )
    financial_analyst: Optional[str] = Field(
        default=None,
        description="Financial analyst responsible for the specification",
    )
    data_pull_owner: Optional[str] = Field(
        default=None,
        description="Data Pull team member/owner for SAP → Databricks load",
    )
    primary_assignee_role: TeamRole = Field(
        default=TeamRole.UNKNOWN,
        description="Role that should primarily pick up this ticket",
    )


class ReconciliationCheck(BaseModel):
    """Mandatory reconciliation logic for every ticket.

    Even Change Requests should state which comparisons are relevant.
    Spec comparison matters: the report may be 'wrong' because it does
    not match requirements, not because SAP/Databricks numbers differ.
    """

    compare_sap_vs_databricks: bool = Field(
        description="True if SAP Fiori figures must be checked against Databricks"
    )
    compare_databricks_vs_power_bi: bool = Field(
        description="True if Databricks must be checked against the Power BI report"
    )
    compare_report_vs_spec: bool = Field(
        description=(
            "True if the Power BI report must be checked against the specification "
            "(spec mismatch can be the root cause)"
        )
    )
    mismatch_suspected_at: PipelineStage = Field(
        description="Stage where the mismatch / change is suspected"
    )
    notes: Optional[str] = Field(
        default=None,
        description="What to compare, metrics, filters, period, etc.",
    )


class DeploymentPipeline(BaseModel):
    """Mandatory release path after a fix or change request is implemented.

    Rule: deploy to DEV first → get approval → only then deploy to PROD.
    Direct PROD deploys without DEV + approval are not allowed.
    """

    status: DeploymentStatus = Field(
        description="Current position in the DEV → approval → PROD pipeline"
    )
    requires_dev_deploy_first: bool = Field(
        description="True if fix/change must be deployed to DEV before PROD"
    )
    awaiting_approval: bool = Field(
        description="True if DEV deploy is done and PROD is blocked on approval"
    )
    approved_for_prod: Optional[bool] = Field(
        default=None,
        description="True/False if an approval decision is known; null if N/A",
    )
    approver_role: Optional[TeamRole] = Field(
        default=None,
        description="Who approves promotion to PROD (usually financial_analyst)",
    )
    deployed_to_dev: Optional[bool] = Field(
        default=None, description="Whether the fix is already on DEV"
    )
    deployed_to_prod: Optional[bool] = Field(
        default=None, description="Whether the fix is already on PROD"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Deploy/approval notes from the ticket text",
    )


class TicketExtraction(BaseModel):
    """Structured fields extracted from a raw Jira ticket text."""

    ticket_type: TicketType = Field(
        description="bug or change_request"
    )
    summary: str = Field(description="Clean one-line summary")
    priority: Priority = Field(description="Inferred priority")
    issue_category: IssueCategory = Field(
        description="High-level category of the ticket"
    )
    report: ReportRef = Field(
        description="Report and DEV/PROD environment this ticket belongs to"
    )
    sap_fiori: SapFioriRef = Field(
        default_factory=SapFioriRef,
        description="SAP Fiori source references",
    )
    specification: SpecificationRef = Field(
        default_factory=SpecificationRef,
        description="Specification the report was built from",
    )
    ownership: Ownership = Field(
        description="Developers, financial analysts, Data Pull ownership"
    )
    reconciliation: ReconciliationCheck = Field(
        description=(
            "Mandatory: which pipeline stages and the spec must be reconciled "
            "to find the root cause (SAP, Databricks, Power BI, specification)"
        )
    )
    deployment: DeploymentPipeline = Field(
        description=(
            "Mandatory: fix/change release path — DEV deploy, approval, then PROD"
        )
    )
    repro_steps: list[str] = Field(
        default_factory=list,
        description="Steps to reproduce or validate; empty if unknown",
    )
    labels: list[str] = Field(
        default_factory=list,
        description="Short topical labels, lowercase kebab-case",
    )
    is_blocker: bool = Field(
        default=False,
        description="True if this blocks PROD reporting, close, or release",
    )
    confidence_notes: Optional[str] = Field(
        default=None,
        description="Uncertainty / missing fields",
    )


# Backward-compatible alias used in early drafts
BugExtraction = TicketExtraction
