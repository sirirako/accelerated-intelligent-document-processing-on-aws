# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Unit tests for PublishOperation enterprise artifact bucket hardening flags.

These tests verify that:
1. PublishOperation.build() accepts artifacts_bucket_kms_key_arn and artifacts_bucket_tags
2. The params are applied via boto3 S3 put_bucket_encryption / put_bucket_tagging calls
3. idp-cli publish exposes --artifacts-bucket-kms-key-arn and --artifacts-bucket-tags
4. The CLI flags are passed through to client.publish.build()
"""

import inspect
import unittest
from unittest.mock import MagicMock, patch


class TestPublishBuildSignature(unittest.TestCase):
    """Verify that PublishOperation.build() has the enterprise params in its signature."""

    def test_build_accepts_kms_key_arn(self):
        """build() must accept artifacts_bucket_kms_key_arn, defaulting to None."""
        from idp_sdk.operations.publish import PublishOperation

        sig = inspect.signature(PublishOperation.build)
        self.assertIn("artifacts_bucket_kms_key_arn", sig.parameters)
        self.assertIsNone(sig.parameters["artifacts_bucket_kms_key_arn"].default)

    def test_build_accepts_artifacts_bucket_tags(self):
        """build() must accept artifacts_bucket_tags, defaulting to None."""
        from idp_sdk.operations.publish import PublishOperation

        sig = inspect.signature(PublishOperation.build)
        self.assertIn("artifacts_bucket_tags", sig.parameters)
        self.assertIsNone(sig.parameters["artifacts_bucket_tags"].default)


class TestPublishBuildAppliesEnterpriseHardening(unittest.TestCase):
    """Verify that enterprise flags are applied via boto3 S3 calls after the build."""

    def _call_build_and_get_s3_mock(self, **extra_kwargs):
        """Call publish.build() with IDPPublisher and boto3 mocked; return mock S3 client."""
        from idp_sdk.operations.publish import PublishOperation

        mock_publisher = MagicMock()
        mock_publisher.run = MagicMock()

        mock_client = MagicMock()
        mock_client._region = "us-east-1"
        op = PublishOperation(mock_client)

        mock_s3 = MagicMock()

        with (
            patch("idp_sdk.operations.publish.boto3") as mock_boto3,
            patch("idp_sdk._core.publish.IDPPublisher", return_value=mock_publisher),
            patch("os.path.exists", return_value=True),
            patch("os.chdir"),
            patch("os.getcwd", return_value="/fake/dir"),
            patch("builtins.open", unittest.mock.mock_open(read_data="0.5.4")),
        ):
            mock_sts = MagicMock()
            mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
            mock_boto3.client.side_effect = lambda svc, **kw: (
                mock_sts if svc == "sts" else mock_s3
            )
            mock_boto3.Session.return_value.region_name = "us-east-1"

            try:
                op.build(
                    source_dir=".",
                    bucket="my-bucket",
                    prefix="idp",
                    region="us-east-1",
                    **extra_kwargs,
                )
            except Exception:
                pass

        return mock_s3

    def test_kms_key_arn_calls_put_bucket_encryption(self):
        """put_bucket_encryption should be called with the KMS ARN."""
        mock_s3 = self._call_build_and_get_s3_mock(
            artifacts_bucket_kms_key_arn="arn:aws:kms:us-east-1:123:key/abc"
        )
        mock_s3.put_bucket_encryption.assert_called_once()
        call_kwargs = mock_s3.put_bucket_encryption.call_args.kwargs
        self.assertEqual(call_kwargs["Bucket"], "my-bucket-us-east-1")
        rules = call_kwargs["ServerSideEncryptionConfiguration"]["Rules"]
        self.assertEqual(
            rules[0]["ApplyServerSideEncryptionByDefault"]["KMSMasterKeyID"],
            "arn:aws:kms:us-east-1:123:key/abc",
        )
        self.assertEqual(
            rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"],
            "aws:kms",
        )

    def test_tags_calls_put_bucket_tagging(self):
        """put_bucket_tagging should be called with the parsed tag set."""
        mock_s3 = self._call_build_and_get_s3_mock(
            artifacts_bucket_tags="CostCenter=123,Project=IDP,Environment=production"
        )
        mock_s3.put_bucket_tagging.assert_called_once()
        call_kwargs = mock_s3.put_bucket_tagging.call_args.kwargs
        self.assertEqual(call_kwargs["Bucket"], "my-bucket-us-east-1")
        tag_set = call_kwargs["Tagging"]["TagSet"]
        self.assertIn({"Key": "CostCenter", "Value": "123"}, tag_set)
        self.assertIn({"Key": "Project", "Value": "IDP"}, tag_set)
        self.assertIn({"Key": "Environment", "Value": "production"}, tag_set)

    def test_both_enterprise_flags_call_both_s3_apis(self):
        """Both put_bucket_encryption and put_bucket_tagging should be called."""
        mock_s3 = self._call_build_and_get_s3_mock(
            artifacts_bucket_kms_key_arn="arn:aws:kms:us-east-1:123:key/abc",
            artifacts_bucket_tags="CostCenter=123,Project=IDP",
        )
        mock_s3.put_bucket_encryption.assert_called_once()
        mock_s3.put_bucket_tagging.assert_called_once()

    def test_no_enterprise_calls_when_flags_omitted(self):
        """Neither put_bucket_encryption nor put_bucket_tagging should be called."""
        mock_s3 = self._call_build_and_get_s3_mock()
        mock_s3.put_bucket_encryption.assert_not_called()
        mock_s3.put_bucket_tagging.assert_not_called()


class TestPublishCLIEnterpriseFlags(unittest.TestCase):
    """Verify that idp-cli publish exposes and correctly wires the enterprise flags."""

    def test_cli_help_shows_kms_key_arn_option(self):
        """idp-cli publish --help must show --artifacts-bucket-kms-key-arn."""
        from click.testing import CliRunner
        from idp_cli.cli import publish

        runner = CliRunner()
        result = runner.invoke(publish, ["--help"])
        self.assertIn("--artifacts-bucket-kms-key-arn", result.output)

    def test_cli_help_shows_artifacts_bucket_tags_option(self):
        """idp-cli publish --help must show --artifacts-bucket-tags."""
        from click.testing import CliRunner
        from idp_cli.cli import publish

        runner = CliRunner()
        result = runner.invoke(publish, ["--help"])
        self.assertIn("--artifacts-bucket-tags", result.output)

    def _invoke_publish(self, extra_args=None):
        """Invoke idp-cli publish with a mocked IDPClient; return build() call kwargs."""
        from click.testing import CliRunner
        from idp_cli.cli import publish

        with patch("idp_cli.cli.IDPClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            mock_result = MagicMock()
            mock_result.success = True
            mock_result.template_url = "https://s3.amazonaws.com/b/t.yaml"
            mock_result.headless_template_url = None
            mock_client.publish.build.return_value = mock_result
            mock_client.publish.print_deployment_urls = MagicMock()

            base_args = ["--region", "us-east-1"]
            runner = CliRunner()
            runner.invoke(publish, base_args + (extra_args or []))

            if mock_client.publish.build.called:
                return mock_client.publish.build.call_args.kwargs
        return {}

    def test_kms_key_arn_forwarded_to_build(self):
        """--artifacts-bucket-kms-key-arn should be passed as artifacts_bucket_kms_key_arn."""
        kwargs = self._invoke_publish(
            [
                "--artifacts-bucket-kms-key-arn",
                "arn:aws:kms:us-east-1:123:key/abc",
            ]
        )
        self.assertEqual(
            kwargs.get("artifacts_bucket_kms_key_arn"),
            "arn:aws:kms:us-east-1:123:key/abc",
        )

    def test_artifacts_bucket_tags_forwarded_to_build(self):
        """--artifacts-bucket-tags should be passed as artifacts_bucket_tags."""
        kwargs = self._invoke_publish(
            [
                "--artifacts-bucket-tags",
                "CostCenter=123,Project=IDP,Environment=production",
            ]
        )
        self.assertEqual(
            kwargs.get("artifacts_bucket_tags"),
            "CostCenter=123,Project=IDP,Environment=production",
        )

    def test_both_flags_forwarded_together(self):
        """Both enterprise flags should be forwarded in the same call."""
        kwargs = self._invoke_publish(
            [
                "--artifacts-bucket-kms-key-arn",
                "arn:aws:kms:us-east-1:123:key/abc",
                "--artifacts-bucket-tags",
                "CostCenter=123,Project=IDP",
            ]
        )
        self.assertEqual(
            kwargs.get("artifacts_bucket_kms_key_arn"),
            "arn:aws:kms:us-east-1:123:key/abc",
        )
        self.assertEqual(
            kwargs.get("artifacts_bucket_tags"), "CostCenter=123,Project=IDP"
        )

    def test_none_passed_when_flags_omitted(self):
        """When enterprise flags are absent, None should be passed to build()."""
        kwargs = self._invoke_publish()
        self.assertIsNone(kwargs.get("artifacts_bucket_kms_key_arn"))
        self.assertIsNone(kwargs.get("artifacts_bucket_tags"))


if __name__ == "__main__":
    unittest.main()
