"""Model package identity and non-transferable qualification tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.model_release import DeviceProfile, ModelPackageManifest

pytestmark = pytest.mark.unit

SHA = "sha256:" + "a" * 64


def _manifest() -> ModelPackageManifest:
    return ModelPackageManifest.model_validate(
        {
            "schema_version": "model_package/1.0.0",
            "package_name": "csight-e3",
            "package_version": "1.0.0",
            "task": "ANY_DEFECT_CLASSIFICATION",
            "artifact_digest": SHA,
            "runtime_image_digest": SHA,
            "dependency_lock_digest": SHA,
            "input_schema_version": "vision_input/1.0.0",
            "output_schema_version": "vision_output/1.0.0",
            "preprocessing_version": "e3-preprocess/1.0.0",
            "threshold_version": "e3-threshold/0.8984375",
            "device_profile": "onprem-cuda",
            "precision": "fp16",
            "max_batch_size": 1,
            "max_context_tokens": None,
            "license_identifier": "Apache-2.0",
            "sbom_digest": SHA,
            "qualifications": [
                {
                    "device_profile": "onprem-cuda",
                    "outcome": "PASS",
                    "dataset_digest": SHA,
                    "result_digest": SHA,
                    "qualified_at": datetime(2026, 8, 29, tzinfo=UTC),
                },
                {
                    "device_profile": "cpu-contract-smoke",
                    "outcome": "PASS",
                    "dataset_digest": SHA,
                    "result_digest": SHA,
                    "qualified_at": datetime(2026, 8, 29, tzinfo=UTC),
                },
            ],
        }
    )


def test_qualification_is_not_transferable_between_device_profiles() -> None:
    manifest = _manifest()

    assert manifest.qualified_for(DeviceProfile.ONPREM_CUDA) is True
    assert manifest.qualified_for(DeviceProfile.CPU_CONTRACT_SMOKE) is False
    assert manifest.qualified_for(DeviceProfile.DEV_MACOS_MPS) is False


def test_duplicate_profile_or_unpinned_digest_is_rejected() -> None:
    manifest = _manifest()
    duplicate = (*manifest.qualifications, manifest.qualifications[0])
    with pytest.raises(ValidationError, match="unique"):
        ModelPackageManifest.model_validate(
            manifest.model_dump(mode="python") | {"qualifications": duplicate}
        )
    with pytest.raises(ValidationError, match="artifact_digest"):
        ModelPackageManifest.model_validate(
            manifest.model_dump(mode="python") | {"artifact_digest": "latest"}
        )
