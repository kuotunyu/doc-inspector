"""Safe, user-facing exception types for doc-inspector."""


class DocInspectorError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(DocInspectorError):
    """Required environment configuration is missing or invalid."""


class DocumentInputError(DocInspectorError):
    """The supplied file cannot be accepted or decoded."""


class UnsupportedFileTypeError(DocumentInputError):
    """The file extension or decoded content is unsupported."""


class FileSizeLimitError(DocumentInputError):
    """The file exceeds the configured byte limit."""


class PageLimitError(DocumentInputError):
    """A PDF has more pages than the core extractor accepts."""


class EncryptedPdfError(DocumentInputError):
    """A PDF requires a password and cannot be processed."""


class DocumentDecodeError(DocumentInputError):
    """The document is corrupt, empty, or otherwise undecodable."""


class ProviderInvocationError(DocInspectorError):
    """The selected cloud model could not complete the request."""


class StructuredOutputError(DocInspectorError):
    """The provider response did not validate against the selected schema."""


class RequestLimitError(DocInspectorError):
    """The public deployment request budget has been exhausted."""
