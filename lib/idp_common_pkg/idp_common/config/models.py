# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Pydantic models for IDP configuration.

These models provide type-safe access to configuration data and can be used
as type hints throughout the codebase.

Usage:
    from idp_common.config.models import IDPConfig

    config_dict = get_config()
    config = IDPConfig.model_validate(config_dict)

    # Type-safe access
    if config.extraction.agentic.enabled:
        model = config.extraction.model
"""

from typing import Any, Dict, List, Optional, Union, Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator, Discriminator


class ImageConfig(BaseModel):
    """Image processing configuration"""

    target_width: Optional[int] = Field(
        default=None, description="Target width for images"
    )
    target_height: Optional[int] = Field(
        default=None, description="Target height for images"
    )
    dpi: Optional[int] = Field(default=None, description="DPI for image rendering")
    preprocessing: Optional[bool] = Field(
        default=None, description="Enable image preprocessing"
    )

    @field_validator("target_width", "target_height", mode="before")
    @classmethod
    def parse_dimensions(cls, v: Any) -> Optional[int]:
        """Parse dimensions from string or number, treating empty strings as None"""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, str):
            return int(v) if v else None
        return int(v)

    @field_validator("dpi", mode="before")
    @classmethod
    def parse_dpi(cls, v: Any) -> Optional[int]:
        """Parse DPI from string or number"""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, str):
            return int(v) if v else None
        return int(v)

    @field_validator("preprocessing", mode="before")
    @classmethod
    def parse_preprocessing(cls, v: Any) -> Optional[bool]:
        """Parse preprocessing bool from string or bool"""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)


class AgenticConfig(BaseModel):
    """Agentic extraction configuration"""

    enabled: bool = Field(default=False, description="Enable agentic extraction")
    review_agent: bool = Field(default=False, description="Enable review agent")


class ExtractionConfig(BaseModel):
    """Document extraction configuration"""

    model: str = Field(
        default="us.amazon.nova-pro-v1:0",
        description="Bedrock model ID for extraction",
    )
    system_prompt: str = Field(
        default="You are a document assistant. Respond only with JSON. Never make up data, only provide data found in the document being provided.",
        description="System prompt for extraction",
    )
    task_prompt: str = Field(
        default="", description="Task prompt template for extraction"
    )
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    top_p: float = Field(default=0.1, ge=0.0, le=1.0)
    top_k: float = Field(default=5.0, ge=0.0)
    max_tokens: int = Field(default=10000, gt=0)
    image: ImageConfig = Field(default_factory=ImageConfig)
    agentic: AgenticConfig = Field(default_factory=AgenticConfig)
    custom_prompt_lambda_arn: Optional[str] = Field(
        default=None, description="ARN of custom prompt Lambda"
    )

    @field_validator("temperature", "top_p", "top_k", mode="before")
    @classmethod
    def parse_float(cls, v: Any) -> float:
        """Parse float from string or number"""
        if isinstance(v, str):
            return float(v) if v else 0.0
        return float(v)

    @field_validator("max_tokens", mode="before")
    @classmethod
    def parse_int(cls, v: Any) -> int:
        """Parse int from string or number"""
        if isinstance(v, str):
            return int(v) if v else 0
        return int(v)


class ClassificationConfig(BaseModel):
    """Document classification configuration"""

    model: str = Field(
        default="us.amazon.nova-pro-v1:0",
        description="Bedrock model ID for classification",
    )
    system_prompt: str = Field(
        default="", description="System prompt for classification"
    )
    task_prompt: str = Field(
        default="", description="Task prompt template for classification"
    )
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    top_p: float = Field(default=0.1, ge=0.0, le=1.0)
    top_k: float = Field(default=5.0, ge=0.0)
    max_tokens: int = Field(default=4096, gt=0)
    maxPagesForClassification: Union[int, str] = Field(
        default=1, description="Max pages to use for classification (int or 'ALL')"
    )
    classificationMethod: str = Field(default="multimodalPageLevelClassification")
    image: ImageConfig = Field(default_factory=ImageConfig)

    @field_validator("temperature", "top_p", "top_k", mode="before")
    @classmethod
    def parse_float(cls, v: Any) -> float:
        """Parse float from string or number"""
        if isinstance(v, str):
            return float(v) if v else 0.0
        return float(v)

    @field_validator("max_tokens", mode="before")
    @classmethod
    def parse_int(cls, v: Any) -> int:
        """Parse int from string or number"""
        if isinstance(v, str):
            return int(v) if v else 0
        return int(v)

    @field_validator("maxPagesForClassification", mode="before")
    @classmethod
    def parse_max_pages(cls, v: Any) -> Union[int, str]:
        """Parse maxPagesForClassification - can be int or 'ALL'"""
        if isinstance(v, str):
            if v.upper() == "ALL":
                return "ALL"
            return int(v) if v else 1
        return int(v)


class GranularAssessmentConfig(BaseModel):
    """Granular assessment configuration"""

    enabled: bool = Field(default=False, description="Enable granular assessment")
    list_batch_size: int = Field(default=1, gt=0)
    simple_batch_size: int = Field(default=3, gt=0)
    max_workers: int = Field(default=20, gt=0)

    @field_validator(
        "list_batch_size", "simple_batch_size", "max_workers", mode="before"
    )
    @classmethod
    def parse_int(cls, v: Any) -> int:
        """Parse int from string or number"""
        if isinstance(v, str):
            return int(v) if v else 0
        return int(v)


class AssessmentConfig(BaseModel):
    """Document assessment configuration"""

    enabled: bool = Field(default=True, description="Enable assessment")
    model: Optional[str] = Field(
        default=None, description="Bedrock model ID for assessment"
    )
    system_prompt: str = Field(default="", description="System prompt for assessment")
    task_prompt: str = Field(
        default="", description="Task prompt template for assessment"
    )
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    top_p: float = Field(default=0.1, ge=0.0, le=1.0)
    top_k: float = Field(default=5.0, ge=0.0)
    max_tokens: int = Field(default=10000, gt=0)
    default_confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    validation_enabled: bool = Field(default=False, description="Enable validation")
    image: ImageConfig = Field(default_factory=ImageConfig)
    granular: GranularAssessmentConfig = Field(default_factory=GranularAssessmentConfig)

    @field_validator(
        "temperature", "top_p", "top_k", "default_confidence_threshold", mode="before"
    )
    @classmethod
    def parse_float(cls, v: Any) -> float:
        """Parse float from string or number"""
        if isinstance(v, str):
            return float(v) if v else 0.0
        return float(v)

    @field_validator("max_tokens", mode="before")
    @classmethod
    def parse_int(cls, v: Any) -> int:
        """Parse int from string or number"""
        if isinstance(v, str):
            return int(v) if v else 0
        return int(v)


class SummarizationConfig(BaseModel):
    """Document summarization configuration"""

    enabled: bool = Field(default=False, description="Enable summarization")
    model: str = Field(
        default="us.amazon.nova-premier-v1:0",
        description="Bedrock model ID for summarization",
    )
    system_prompt: str = Field(
        default="", description="System prompt for summarization"
    )
    task_prompt: str = Field(
        default="", description="Task prompt template for summarization"
    )
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    top_p: float = Field(default=0.1, ge=0.0, le=1.0)
    top_k: float = Field(default=5.0, ge=0.0)
    max_tokens: int = Field(default=4096, gt=0)

    @field_validator("temperature", "top_p", "top_k", mode="before")
    @classmethod
    def parse_float(cls, v: Any) -> float:
        """Parse float from string or number"""
        if isinstance(v, str):
            return float(v) if v else 0.0
        return float(v)

    @field_validator("max_tokens", mode="before")
    @classmethod
    def parse_int(cls, v: Any) -> int:
        """Parse int from string or number"""
        if isinstance(v, str):
            return int(v) if v else 0
        return int(v)


class OCRFeature(BaseModel):
    """OCR feature configuration"""

    name: str = Field(description="Feature name (e.g., LAYOUT, TABLES, FORMS)")


class OCRConfig(BaseModel):
    """OCR configuration"""

    backend: str = Field(
        default="textract", description="OCR backend (textract or bedrock)"
    )
    model_id: Optional[str] = Field(
        default=None, description="Bedrock model ID for OCR (if backend=bedrock)"
    )
    system_prompt: Optional[str] = Field(
        default=None, description="System prompt for Bedrock OCR"
    )
    task_prompt: Optional[str] = Field(
        default=None, description="Task prompt for Bedrock OCR"
    )
    features: List[OCRFeature] = Field(
        default_factory=list, description="Textract features to enable"
    )
    max_workers: int = Field(default=20, gt=0, description="Max concurrent workers")
    image: ImageConfig = Field(default_factory=ImageConfig)

    @field_validator("max_workers", mode="before")
    @classmethod
    def parse_max_workers(cls, v: Any) -> int:
        """Parse max_workers from string or number"""
        if isinstance(v, str):
            return int(v) if v else 20
        return int(v)


class ErrorAnalyzerConfig(BaseModel):
    """Error analyzer agent configuration"""

    model_id: str = Field(
        default="us.anthropic.claude-sonnet-4-20250514-v1:0",
        description="Bedrock model ID for error analyzer",
    )


class AgentsConfig(BaseModel):
    """Agents configuration"""

    error_analyzer: Optional[ErrorAnalyzerConfig] = Field(default=None)


class PricingUnit(BaseModel):
    """Pricing unit configuration"""

    name: str
    price: float


class PricingItem(BaseModel):
    """Pricing item configuration"""

    name: str
    units: List[PricingUnit]


class CriteriaValidationConfig(BaseModel):
    """Criteria validation configuration"""

    model: str = Field(
        default="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
        description="Bedrock model ID for criteria validation",
    )
    system_prompt: str = Field(default="", description="System prompt")
    task_prompt: str = Field(default="", description="Task prompt")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    top_p: float = Field(default=0.01, ge=0.0, le=1.0)
    top_k: float = Field(default=20.0, ge=0.0)
    max_tokens: int = Field(default=4096, gt=0)
    semaphore: int = Field(
        default=3, gt=0, description="Number of concurrent API calls"
    )
    max_chunk_size: int = Field(
        default=180000, gt=0, description="Maximum tokens per chunk"
    )
    token_size: int = Field(default=4, gt=0, description="Average characters per token")
    overlap_percentage: int = Field(
        default=10, ge=0, le=100, description="Chunk overlap percentage"
    )
    response_prefix: str = Field(
        default="<response>", description="Response prefix marker"
    )

    @field_validator("temperature", "top_p", "top_k", mode="before")
    @classmethod
    def parse_float(cls, v: Any) -> float:
        """Parse float from string or number"""
        if isinstance(v, str):
            return float(v) if v else 0.0
        return float(v)

    @field_validator(
        "max_tokens",
        "semaphore",
        "max_chunk_size",
        "token_size",
        "overlap_percentage",
        mode="before",
    )
    @classmethod
    def parse_int(cls, v: Any) -> int:
        """Parse int from string or number"""
        if isinstance(v, str):
            return int(v) if v else 0
        return int(v)


class EvaluationLLMMethodConfig(BaseModel):
    """Evaluation LLM method configuration"""

    top_p: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, gt=0)
    top_k: float = Field(default=5.0, ge=0.0)
    task_prompt: str = Field(default="", description="Task prompt for evaluation")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    model: str = Field(
        default="us.anthropic.claude-3-haiku-20240307-v1:0",
        description="Bedrock model ID for evaluation",
    )
    system_prompt: str = Field(default="", description="System prompt for evaluation")

    @field_validator("temperature", "top_p", "top_k", mode="before")
    @classmethod
    def parse_float(cls, v: Any) -> float:
        """Parse float from string or number"""
        if isinstance(v, str):
            return float(v) if v else 0.0
        return float(v)

    @field_validator("max_tokens", mode="before")
    @classmethod
    def parse_int(cls, v: Any) -> int:
        """Parse int from string or number"""
        if isinstance(v, str):
            return int(v) if v else 0
        return int(v)


class EvaluationConfig(BaseModel):
    """Evaluation configuration for assessment"""

    llm_method: EvaluationLLMMethodConfig = Field(
        default_factory=EvaluationLLMMethodConfig,
        description="LLM method configuration for evaluation",
    )


class DiscoveryModelConfig(BaseModel):
    """Discovery model configuration for class extraction"""

    model_id: str = Field(
        default="us.amazon.nova-pro-v1:0", description="Bedrock model ID for discovery"
    )
    system_prompt: str = Field(default="", description="System prompt for discovery")
    temperature: float = Field(default=1.0, ge=0.0, le=1.0)
    top_p: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=10000, gt=0)
    user_prompt: str = Field(
        default="", description="User prompt template for discovery"
    )

    @field_validator("temperature", "top_p", mode="before")
    @classmethod
    def parse_float(cls, v: Any) -> float:
        """Parse float from string or number"""
        if isinstance(v, str):
            return float(v) if v else 0.0
        return float(v)

    @field_validator("max_tokens", mode="before")
    @classmethod
    def parse_int(cls, v: Any) -> int:
        """Parse int from string or number"""
        if isinstance(v, str):
            return int(v) if v else 0
        return int(v)


class DiscoveryConfig(BaseModel):
    """Discovery configuration"""

    without_ground_truth: DiscoveryModelConfig = Field(
        default_factory=DiscoveryModelConfig,
        description="Configuration for discovery without ground truth",
    )
    with_ground_truth: DiscoveryModelConfig = Field(
        default_factory=DiscoveryModelConfig,
        description="Configuration for discovery with ground truth",
    )


class SchemaConfig(BaseModel):
    """
    Schema configuration model.

    This represents the JSON Schema configuration type stored in DynamoDB.
    It contains the structure/definition of document schemas.
    """

    config_type: Literal["Schema"] = Field(
        default="Schema", description="Discriminator for config type"
    )

    # Schema config contains the JSON Schema format
    type: str = Field(default="object", description="JSON Schema type")
    required: List[str] = Field(default_factory=list, description="Required properties")
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="Schema properties definitions"
    )
    order: Optional[str] = Field(default=None, description="Display order")

    model_config = ConfigDict(
        extra="allow",  # Allow additional JSON Schema fields
        validate_assignment=True,
    )


class IDPConfig(BaseModel):
    """
    Complete IDP configuration model.

    This model provides type-safe access to IDP configuration and handles
    automatic conversion of string representations (e.g., "0.5" -> 0.5).

    Example:
        config_dict = get_config()
        config = IDPConfig.model_validate(config_dict)

        if config.extraction.agentic.enabled:
            temperature = config.extraction.temperature
    """

    config_type: Literal["Default", "Custom"] = Field(
        default="Default", description="Discriminator for config type"
    )

    notes: Optional[str] = Field(default=None, description="Configuration notes")
    ocr: OCRConfig = Field(default_factory=OCRConfig, description="OCR configuration")
    classification: ClassificationConfig = Field(
        default_factory=lambda: ClassificationConfig(model="us.amazon.nova-pro-v1:0"),
        description="Classification configuration",
    )
    extraction: ExtractionConfig = Field(
        default_factory=ExtractionConfig, description="Extraction configuration"
    )
    assessment: AssessmentConfig = Field(
        default_factory=AssessmentConfig, description="Assessment configuration"
    )
    summarization: SummarizationConfig = Field(
        default_factory=lambda: SummarizationConfig(
            model="us.amazon.nova-premier-v1:0"
        ),
        description="Summarization configuration",
    )
    criteria_validation: CriteriaValidationConfig = Field(
        default_factory=CriteriaValidationConfig,
        description="Criteria validation configuration",
    )
    agents: AgentsConfig = Field(
        default_factory=AgentsConfig, description="Agents configuration"
    )
    pricing: List[PricingItem] = Field(
        default_factory=list, description="Pricing configuration"
    )
    classes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Document class definitions (JSON Schema)"
    )
    discovery: DiscoveryConfig = Field(
        default_factory=DiscoveryConfig, description="Discovery configuration"
    )
    evaluation: EvaluationConfig = Field(
        default_factory=EvaluationConfig, description="Evaluation configuration"
    )

    model_config = ConfigDict(
        # Do not allow extra fields - all config should be explicit
        extra="forbid",
        # Validate on assignment
        validate_assignment=True,
    )


class ConfigMetadata(BaseModel):
    """Metadata for configuration records"""

    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="Update timestamp")
    version: Optional[str] = Field(default=None, description="Configuration version")


class ConfigurationRecord(BaseModel):
    """
    DynamoDB storage model for IDP configurations.

    This model wraps IDPConfig and handles serialization/deserialization
    to/from DynamoDB, including the critical string conversion for storage.

    Example:
        # Create from IDPConfig
        config = IDPConfig(...)
        record = ConfigurationRecord(
            configuration_type="Default",
            config=config
        )

        # Serialize to DynamoDB
        item = record.to_dynamodb_item()

        # Deserialize from DynamoDB
        record = ConfigurationRecord.from_dynamodb_item(item)
        idp_config = record.config
    """

    configuration_type: str = Field(
        description="Configuration type (Schema, Default, Custom)"
    )
    config: Annotated[Union[SchemaConfig, IDPConfig], Discriminator("config_type")] = (
        Field(
            description="The configuration - SchemaConfig for Schema type, IDPConfig for Default/Custom"
        )
    )
    metadata: Optional[ConfigMetadata] = Field(
        default=None, description="Optional metadata about the configuration"
    )

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """
        Convert to DynamoDB item format.

        This method:
        1. Exports config as a Python dict
        2. Removes the config_type discriminator (not needed in DynamoDB)
        3. Stringifies values (preserving booleans, converting numbers to strings)
        4. Adds the Configuration partition key

        Returns:
            Dict suitable for DynamoDB put_item() with:
            - Configuration: str (partition key)
            - All config fields stringified (except booleans)
        """
        # Get config as dict using Pydantic's model_dump
        config_dict = self.config.model_dump(mode="python")

        # Remove the discriminator field - it's only for Pydantic, not DynamoDB
        config_dict.pop("config_type", None)

        # Stringify values (preserve booleans, convert numbers to strings)
        stringified = self._stringify_values(config_dict)

        # Build DynamoDB item
        item = {"Configuration": self.configuration_type, **stringified}

        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "ConfigurationRecord":
        """
        Create ConfigurationRecord from DynamoDB item.

        This method:
        1. Extracts the Configuration key
        2. Removes DynamoDB metadata
        3. Auto-migrates legacy format if needed
        4. Validates into IDPConfig (Pydantic handles type conversions)

        Args:
            item: Raw DynamoDB item dict

        Returns:
            ConfigurationRecord with validated IDPConfig

        Raises:
            ValueError: If Configuration key is missing
        """
        import logging

        logger = logging.getLogger(__name__)

        # Extract configuration type
        config_type = item.get("Configuration")
        if not config_type:
            raise ValueError("DynamoDB item missing 'Configuration' key")

        # Remove DynamoDB metadata keys
        config_data = {k: v for k, v in item.items() if k != "Configuration"}

        # Add config_type discriminator for Pydantic
        config_data["config_type"] = config_type

        # Auto-migrate legacy format if needed
        if config_data.get("classes"):
            from .migration import is_legacy_format, migrate_legacy_to_schema

            if is_legacy_format(config_data["classes"]):
                logger.info(
                    f"Migrating {config_type} configuration to JSON Schema format"
                )
                config_data["classes"] = migrate_legacy_to_schema(
                    config_data["classes"]
                )

        # Parse into appropriate config type - Pydantic discriminator handles this automatically
        config = cls.model_validate(
            {"configuration_type": config_type, "config": config_data}
        ).config

        return cls(configuration_type=config_type, config=config)

    @staticmethod
    def _stringify_values(obj: Any) -> Any:
        """
        Recursively convert values to strings for DynamoDB storage.

        Strategy:
        - Preserve booleans as native bool (CRITICAL - string "False" is truthy in Python)
        - Preserve None as NULL
        - Convert numbers to strings (avoids Decimal conversion issues)
        - Recursively process dicts and lists

        Args:
            obj: Value to stringify

        Returns:
            Stringified value suitable for DynamoDB storage
        """
        # Preserve None (NULL type in DynamoDB)
        if obj is None:
            return None

        # Preserve booleans (BOOL type in DynamoDB)
        # CRITICAL: MUST check bool before int, since bool is subclass of int
        # Booleans must stay native because string "False" evaluates as truthy
        elif isinstance(obj, bool):
            return obj

        # Recursively process dicts (M type in DynamoDB)
        elif isinstance(obj, dict):
            return {k: ConfigurationRecord._stringify_values(v) for k, v in obj.items()}

        # Recursively process lists (L type in DynamoDB)
        elif isinstance(obj, list):
            return [ConfigurationRecord._stringify_values(item) for item in obj]

        # Convert everything else to string (numbers, Decimals, custom objects, etc.)
        else:
            return str(obj)
