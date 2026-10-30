from .config import GuardrailConfig, RuntimeConfig, SecurityConfig
from .credentials import CredentialStore, CredentialStoreError
from .dataset import EvaluationDataset, EvaluationExample
from .decision_engine import DecisionEngine
from .embedding_model import EmbeddingModel
from .engine import GuardrailEngine
from .evaluator import EvaluationReport, GuardrailEvaluator
from .middleware import GuardrailMiddleware
from .models import Decision, GuardrailResult, Policy, PolicyRule, SemanticExample
from .normalizer import RequestNormalizer
from .policy_config import PolicyConfigLoader
from .policy_manager import InvalidPolicyError, PolicyManager, RuleCompilationError
from .providers import EmbeddingMetadata, EmbeddingProvider, ProviderError, ProviderRegistry
from .providers import OpenAIEmbeddingProvider
from .chat import (
    ChatMessage,
    GuardedChatClient,
    GuardedChatResponse,
    GuardrailBlockedError,
    OpenAIChatCompletion,
)
from .rule_engine import RuleEngine
from .semantic_engine import SemanticEngine
from .stream_buffer import StreamBuffer
from .streaming_middleware import StreamingGuardrailMiddleware
from .security import AuditEvent, SecurityPipeline
from .vector_store import VectorCompatibilityError, VectorStore
from .operational_store import OperationalStore

try:
    from .api import RuntimeState, app, create_app
except ImportError:
    RuntimeState = None
    app = None
    create_app = None

__all__ = [
    "Decision",
    "DecisionEngine",
    "EmbeddingModel",
    "EvaluationDataset",
    "EvaluationExample",
    "EvaluationReport",
    "GuardrailConfig",
    "RuntimeConfig",
    "SecurityConfig",
    "CredentialStore",
    "CredentialStoreError",
    "GuardrailEngine",
    "GuardrailEvaluator",
    "GuardrailMiddleware",
    "GuardrailResult",
    "Policy",
    "PolicyConfigLoader",
    "PolicyManager",
    "EmbeddingMetadata",
    "EmbeddingProvider",
    "ProviderError",
    "ProviderRegistry",
    "OpenAIEmbeddingProvider",
    "ChatMessage",
    "GuardedChatClient",
    "GuardedChatResponse",
    "GuardrailBlockedError",
    "OpenAIChatCompletion",
    "InvalidPolicyError",
    "RuleCompilationError",
    "PolicyRule",
    "RequestNormalizer",
    "RuleEngine",
    "SemanticEngine",
    "SemanticExample",
    "StreamBuffer",
    "StreamingGuardrailMiddleware",
    "AuditEvent",
    "SecurityPipeline",
    "ThresholdResult",
    "format_top_results",
    "optimize_thresholds",
    "VectorStore",
    "VectorCompatibilityError",
    "OperationalStore",
    "RuntimeState",
    "app",
    "create_app",
]


def __getattr__(name: str):
    if name in {"ThresholdResult", "format_top_results", "optimize_thresholds"}:
        from .threshold_optimizer import ThresholdResult, format_top_results, optimize_thresholds

        return {
            "ThresholdResult": ThresholdResult,
            "format_top_results": format_top_results,
            "optimize_thresholds": optimize_thresholds,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
