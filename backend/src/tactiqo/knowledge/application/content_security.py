"""Treat retrieved document content as untrusted data, never instructions."""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContentSecurityAssessment:
    """Non-destructive security labels for one evidence fragment."""

    suspicious: bool
    signals: tuple[str, ...]


class DocumentContentSecurityScanner:
    """Detect common control-channel and exfiltration language in evidence."""

    _PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("instruction_override", re.compile(
            r"(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system)"
            r"|(?:تجاهل|تخط(?:ى|ي)|الغ(?:ِ|ي))\s+(?:كل\s+)?(?:التعليمات|الأوامر|السياسات)",
            re.IGNORECASE)),
        ("secret_exfiltration", re.compile(
            r"(?:reveal|print|show|send|exfiltrate).{0,40}(?:secret|token|password|api.?key)"
            r"|(?:اكشف|اطبع|اعرض|ارسل).{0,40}(?:سر|توكن|كلمة\s*مرور|مفتاح)",
            re.IGNORECASE)),
        ("tool_control", re.compile(
            r"(?:call|invoke|execute|run)\s+(?:the\s+)?(?:tool|function|command)"
            r"|(?:شغّل|نفّذ|استدع(?:ي|اء)).{0,30}(?:أداة|اداة|أمر|دالة)",
            re.IGNORECASE)),
        ("role_impersonation", re.compile(
            r"(?:system|assistant|developer)\s*(?:message|instruction|:)"
            r"|(?:رسالة|تعليمات)\s+(?:النظام|المطور|المساعد)", re.IGNORECASE)),
    )

    def assess(self, text: str) -> ContentSecurityAssessment:
        """Return stable labels without mutating or deleting source text."""
        signals = tuple(name for name, pattern in self._PATTERNS if pattern.search(text))
        return ContentSecurityAssessment(suspicious=bool(signals), signals=signals)

    def wrap_as_evidence(self, text: str) -> str:
        """Create an explicit data boundary for model-facing evidence."""
        assessment = self.assess(text)
        labels = ",".join(assessment.signals) if assessment.signals else "none"
        return (
            f'<untrusted_document_evidence security_signals="{labels}">\n'
            f"{text}\n</untrusted_document_evidence>"
        )
