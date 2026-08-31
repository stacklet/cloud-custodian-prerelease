# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import yaml

from .common import BaseTest
from c7n.resources.cfn import TAG_INELIGIBLE_STACK_STATUSES, _tag_stack

import logging
import time
import json

from unittest import mock


class TestCFN(BaseTest):
    def test_delete(self):
        factory = self.replay_flight_data("test_cfn_delete")
        p = self.load_policy(
            {
                "name": "cfn-delete",
                "resource": "cfn",
                "filters": [{"StackStatus": "ROLLBACK_COMPLETE"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.maxDiff = None
        self.assertEqual(
            sorted([r["StackName"] for r in resources]),
            ["sphere11-db-1", "sphere11-db-2", "sphere11-db-3"],
        )

    def test_delete_with_protection(self):
        stack_name = "c7n-test-delete-with-protection"

        factory = self.replay_flight_data("test_cfn_delete_with_protection")
        client = factory().client("cloudformation")
        cfn_template = {"Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}}}
        client.create_stack(
            StackName=stack_name,
            TemplateBody=json.dumps(cfn_template),
            EnableTerminationProtection=True,
        )
        self.addCleanup(client.delete_stack, StackName=stack_name)
        self.addCleanup(
            client.update_termination_protection,
            StackName=stack_name,
            EnableTerminationProtection=False,
        )
        if self.recording:
            time.sleep(30)

        stacks = client.describe_stacks(StackName=stack_name).get("Stacks")
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), True)
        p = self.load_policy(
            {
                "name": "cfn-delete-force",
                "resource": "cfn",
                "filters": [{"StackName": stack_name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # this should have done nothing.
        stacks = client.describe_stacks(StackName=stack_name).get(
            "Stacks"
        )
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), True)
        self.assertEqual(stacks[0].get("StackStatus"), "CREATE_COMPLETE")

    def test_delete_force(self):
        stack_name = "c7n-test-delete-force"

        factory = self.replay_flight_data("test_cfn_delete_force")
        client = factory().client("cloudformation")
        cfn_template = {"Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}}}
        client.create_stack(
            StackName=stack_name,
            TemplateBody=json.dumps(cfn_template),
            EnableTerminationProtection=True,
        )
        if self.recording:
            time.sleep(30)

        stacks = client.describe_stacks(StackName=stack_name).get("Stacks")
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), True)
        p = self.load_policy(
            {
                "name": "cfn-delete-force",
                "resource": "cfn",
                "filters": [{"StackName": stack_name}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # make sure delete has time to complete
        if self.recording:
            time.sleep(30)

        # deleted stacks must be referenced by StackId
        stacks = client.describe_stacks(StackName=resources[0]["StackId"]).get(
            "Stacks"
        )
        self.assertEqual(stacks[0].get("StackStatus"), "DELETE_COMPLETE")

    def test_query(self):
        factory = self.replay_flight_data("test_cfn_query")
        p = self.load_policy(
            {"name": "cfn-query", "resource": "cfn"}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        for r in resources:
            self.assertTrue("arn" in r['StackId'])
            self.assertTrue("StackName" in r)
            self.assertTrue("Tags" in r)
            self.assertEqual(r["Tags"], [])

    def test_disable_protection(self):
        factory = self.replay_flight_data("test_cfn_disable_protection")
        client = factory().client("cloudformation")
        stacks = client.describe_stacks(StackName="mytopic").get("Stacks")
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), True)
        p = self.load_policy(
            {
                "name": "cfn-disable-protection",
                "resource": "cfn",
                "filters": [{"StackName": "mytopic"}],
                "actions": [{"type": "set-protection", "state": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("cloudformation")
        stacks = client.describe_stacks(StackName=resources[0]["StackName"]).get(
            "Stacks"
        )
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), False)

    def test_cfn_add_tag_with_params(self):
        session_factory = self.replay_flight_data("test_cfn_add_tag_w_params")
        p = self.load_policy(
            {
                "name": "cfn-add-tag",
                "resource": "cfn",
                "filters": [{"StackName": "mosdef2"}],
                "actions": [{"type": "tag", "tags": {"App": "Ftw"}}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("cloudformation")
        rtags = {t["Key"]: t["Value"] for t in resources[0]["Tags"]}
        self.assertEqual(rtags, {"Env": "Dev"})
        tags = {
            t["Key"]: t["Value"]
            for t in client.describe_stacks(StackName=resources[0]["StackName"])[
                "Stacks"
            ][0]["Tags"]
        }
        self.assertEqual(tags, {"Env": "Dev", "App": "Ftw"})

    def test_cfn_add_tag(self):
        session_factory = self.replay_flight_data("test_cfn_add_tag")
        p = self.load_policy(
            {
                "name": "cfn-add-tag",
                "resource": "cfn",
                "filters": [{"tag:DesiredTag": "absent"}],
                "actions": [
                    {"type": "tag", "key": "DesiredTag", "value": "DesiredValue"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("cloudformation")
        tags = client.describe_stacks(StackName=resources[0]["StackName"])["Stacks"][0][
            "Tags"
        ]
        self.assertEqual(
            [tags[0]["Key"], tags[0]["Value"]], ["DesiredTag", "DesiredValue"]
        )

    def test_cfn_remove_tag(self):
        session_factory = self.replay_flight_data("test_cfn_remove_tag")
        p = self.load_policy(
            {
                "name": "cfn-remove-tag",
                "resource": "cfn",
                "filters": [{"tag:DesiredTag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["DesiredTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("cloudformation")
        tags = client.describe_stacks(StackName=resources[0]["StackName"])["Stacks"][0][
            "Tags"
        ]
        self.assertEqual(len(tags), 0)

    def get_tag_action(self, action):
        p = self.load_policy(
            {
                "name": "cfn-skip-ineligible",
                "resource": "cfn",
                "actions": [action],
            }
        )
        return p.resource_manager.actions[0]

    def test_cfn_tag_ineligible_statuses(self):
        # pin the set itself -- the per-status tests below iterate it, so
        # they cannot notice an entry going missing.
        self.assertEqual(
            TAG_INELIGIBLE_STACK_STATUSES,
            {
                "CREATE_FAILED",
                "UPDATE_FAILED",
                "ROLLBACK_COMPLETE",
                "ROLLBACK_FAILED",
                "DELETE_FAILED",
                "UPDATE_ROLLBACK_FAILED",
                "IMPORT_ROLLBACK_FAILED",
                "REVIEW_IN_PROGRESS",
                "UPDATE_ROLLBACK_COMPLETE",
            },
        )

    def test_cfn_add_tag_skips_ineligible_status(self):
        action = self.get_tag_action(
            {"type": "tag", "key": "DesiredTag", "value": "DesiredValue"}
        )
        for status in TAG_INELIGIBLE_STACK_STATUSES:
            stacks = [{"StackName": "stack", "StackStatus": status, "Tags": []}]
            with mock.patch.object(action, "process_resource_set") as mock_prs:
                action.process(stacks)
            mock_prs.assert_not_called()

    def test_cfn_remove_tag_skips_ineligible_status(self):
        action = self.get_tag_action({"type": "remove-tag", "tags": ["DesiredTag"]})
        stacks = [
            {"StackName": "undeletable", "StackStatus": "DELETE_FAILED", "Tags": []},
            {"StackName": "unreviewed", "StackStatus": "REVIEW_IN_PROGRESS", "Tags": []},
        ]
        with mock.patch.object(action, "process_resource_set") as mock_prs:
            action.process(stacks)
        mock_prs.assert_not_called()

    def test_cfn_add_tag_mixed_status(self):
        action = self.get_tag_action(
            {"type": "tag", "key": "DesiredTag", "value": "DesiredValue"}
        )
        stacks = [
            {"StackName": "rolled-back", "StackStatus": "ROLLBACK_COMPLETE", "Tags": []},
            {"StackName": "healthy", "StackStatus": "CREATE_COMPLETE", "Tags": []},
            {"StackName": "reverting", "StackStatus": "UPDATE_ROLLBACK_COMPLETE", "Tags": []},
        ]
        with mock.patch.object(action, "process_resource_set") as mock_prs, \
                mock.patch.object(action, "get_client"):
            action.process(stacks)
        mock_prs.assert_called_once()
        resource_set = mock_prs.call_args[0][1]
        self.assertEqual([s["StackName"] for s in resource_set], ["healthy"])

    def test_cfn_add_tag_skip_warns(self):
        action = self.get_tag_action(
            {"type": "tag", "key": "DesiredTag", "value": "DesiredValue"}
        )
        stacks = [
            {"StackName": "rolled-back", "StackStatus": "ROLLBACK_COMPLETE", "Tags": []},
            {"StackName": "reverting", "StackStatus": "UPDATE_ROLLBACK_COMPLETE", "Tags": []},
            {"StackName": "healthy", "StackStatus": "CREATE_COMPLETE", "Tags": []},
        ]
        log_output = self.capture_logging(
            "custodian.resources.cloudformation", level=logging.WARNING
        )
        with mock.patch.object(action, "process_resource_set"), \
                mock.patch.object(action, "get_client"):
            action.process(stacks)
        self.assertIn("Skipping 2 cfn stack(s)", log_output.getvalue())

    def test_cfn_tag_stack_preserves_notification_topics(self):
        # an empty NotificationARNs list detaches every topic on the stack,
        # so the arns describe_stacks reported have to be passed back.
        client = mock.MagicMock()
        topics = ["arn:aws:sns:us-east-1:644160558196:c7n-stack-events"]
        stack = {
            "StackName": "c7n-notified",
            "StackStatus": "CREATE_COMPLETE",
            "Tags": [],
            "NotificationARNs": topics,
        }
        _tag_stack(client, stack, add=[{"Key": "DesiredTag", "Value": "DesiredValue"}])
        self.assertEqual(client.update_stack.call_args[1]["NotificationARNs"], topics)

    def test_cfn_add_tag_skip_ineligible_no_update(self):
        # the flight data records no UpdateStack response, so the replay
        # raises if any of these stacks reaches the action's api call.
        session_factory = self.replay_flight_data("test_cfn_tag_skip_ineligible")
        p = self.load_policy(
            {
                "name": "cfn-add-tag",
                "resource": "cfn",
                "actions": [
                    {"type": "tag", "key": "DesiredTag", "value": "DesiredValue"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        # the stacks stay visible to filters and inventory policies
        self.assertEqual(
            sorted(r["StackStatus"] for r in resources),
            ["ROLLBACK_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"],
        )

    def test_cfn_template_filter(self):
        session_factory = self.replay_flight_data("test_cfn_template_filter")
        client = session_factory().client("cloudformation")

        stack_name = "c7n-test-template-filter"

        template_body = yaml.dump({
            "Resources": {
                "MyBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "BucketName": "c7n-access-key-test-bucket"
                    }
                }
            },
            "Metadata": {
                "API_KEY": "API_KEY123456789"
            }
        })

        client.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_NAMED_IAM"]
        )
        self.addCleanup(client.delete_stack, StackName=stack_name)

        if self.recording:
            time.sleep(30)

        stacks = client.describe_stacks(StackName=stack_name)["Stacks"]
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0]["StackName"], stack_name)

        policy = self.load_policy(
            {
                "name": "test-cfn-template-filter",
                "resource": "cfn",
                "filters": [
                    {
                        "type": "template",
                        "pattern": "API_KEY[0-9A-Z]",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["StackName"], stack_name)

    def test_cfn_topic_filter(self):
        session_factory = self.replay_flight_data("test_cfn_topic_filter")
        p = self.load_policy({
            'name': 'test-cfn-topic-filter',
            'resource': 'aws.cfn',
            'filters': [{
                'type': 'topic',
                'attrs': [{
                    'type': 'value',
                    'key': 'SubscriptionsConfirmed',
                    'value': 0,
                    'value_type': 'integer'
                }]
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:SnsTopics'][0]['SubscriptionsConfirmed'], '0')
