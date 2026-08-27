"""Provider-native defect classes mapped to CSight's canonical taxonomy."""

from types import MappingProxyType

from app.platform.analysis import DefectType

KAPUT_TAXONOMY_VERSION = "kaputt-7-v1"
CSIGHT_VISION_TAXONOMY_VERSION = "csight-defect-v1"
KAPUT_ANY_DEFECT_TAXONOMY_VERSION = "kaputt-any-defect-binary-v1"
CSIGHT_ANY_DEFECT_ASSESSMENT_VERSION = "csight-any-defect-assessment-v1"

_KAPUT_TO_CSIGHT = MappingProxyType(
    {
        "penetration": DefectType.CRACK,
        "deformation": DefectType.DENT,
        "actuation": DefectType.FUNCTIONAL_FAILURE,
        "deconstruction": DefectType.BREAKAGE,
        "spillage": DefectType.LEAKAGE,
        "superficial": DefectType.SURFACE_DAMAGE,
        "missing_unit": DefectType.MISSING_COMPONENT,
    }
)


def map_model_class(class_name: str) -> DefectType:
    """Map a model-native label without exposing its numeric ID as a business type."""

    return _KAPUT_TO_CSIGHT.get(class_name.strip().casefold(), DefectType.UNKNOWN)


__all__ = [
    "CSIGHT_ANY_DEFECT_ASSESSMENT_VERSION",
    "CSIGHT_VISION_TAXONOMY_VERSION",
    "KAPUT_ANY_DEFECT_TAXONOMY_VERSION",
    "KAPUT_TAXONOMY_VERSION",
    "map_model_class",
]
