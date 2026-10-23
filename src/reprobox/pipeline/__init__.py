"""Pipeline package coordinating reproduction steps and lifecycle."""

from reprobox.pipeline.cases import CaseFixture
from reprobox.pipeline.orchestrator import PipelineResult, run_pipeline
from reprobox.pipeline.recovery import RecoveryHandler, RecoveryResult
from reprobox.pipeline.verification import ClassificationResult, parse_and_classify_junit

__all__ = [
    "CaseFixture",
    "PipelineResult",
    "run_pipeline",
    "RecoveryHandler",
    "RecoveryResult",
    "ClassificationResult",
    "parse_and_classify_junit",
]
