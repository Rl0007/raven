# Copyright (c) 2026, Frappe and Contributors
# See license.txt

import frappe
from frappe import _
from frappe.tests import IntegrationTestCase
from frappe.tests.classes.context_managers import patch_hooks

from raven.raven_bot.slash_commands import (
	SlashCommand,
	get_slash_commands,
	press_button,
	run_slash_command,
)

EXTRA_TEST_RECORD_DEPENDENCIES = ["User", "Raven User"]

TEST_MODULE = "raven.raven_bot.doctype.raven_bot_command.test_raven_bot_command"
ECHO_HANDLER = f"{TEST_MODULE}.echo_handler"
FAILING_HANDLER = f"{TEST_MODULE}.failing_handler"
REFUSING_HANDLER = f"{TEST_MODULE}.refusing_handler"
COLOUR_HANDLER = f"{TEST_MODULE}.colour_handler"
ALLOWED_HANDLERS = {
	"raven_slash_command_handlers": [ECHO_HANDLER, FAILING_HANDLER, REFUSING_HANDLER, COLOUR_HANDLER]
}


def echo_handler(interaction):
	return f"echo: {interaction.arguments}"


def failing_handler(interaction):
	raise ZeroDivisionError


def refusing_handler(interaction):
	frappe.throw(_("box name is required"))


def colour_handler(interaction):
	if interaction.pressed:
		return f"{interaction.state['asked']} {interaction.pressed}"
	buttons = [{"label": "Red", "value": "red"}, {"label": "Blue", "value": "blue"}]
	return {"text": "Pick a colour", "buttons": buttons, "state": {"asked": "You picked"}}


class IntegrationTestRavenBotCommand(IntegrationTestCase):
	def setUp(self):
		self.workspace = frappe.get_doc(
			{"doctype": "Raven Workspace", "workspace_name": "Slash Test Workspace", "type": "Public"}
		).insert()
		self.channel = self.create_channel("slash-test-channel")
		self.other_channel = self.create_channel("slash-other-channel")
		self.bot = frappe.get_doc({"doctype": "Raven Bot", "bot_name": "Slash Test Bot"}).insert()

	def tearDown(self):
		frappe.db.rollback()

	def create_channel(self, channel_name):
		return frappe.get_doc(
			{
				"doctype": "Raven Channel",
				"channel_name": channel_name,
				"type": "Public",
				"workspace": self.workspace.name,
			}
		).insert()

	def create_command(self, command, handler=ECHO_HANDLER, channels=None):
		with patch_hooks(ALLOWED_HANDLERS):
			return frappe.get_doc(
				{
					"doctype": "Raven Bot Command",
					"command": command,
					"bot": self.bot.name,
					"description": f"{command} command",
					"handler": handler,
					"channels": [{"channel": channel} for channel in channels or []],
				}
			).insert()

	def send(self, text, channel=None):
		return frappe.get_doc(
			{
				"doctype": "Raven Message",
				"channel_id": (channel or self.channel).name,
				"message_type": "Text",
				"text": f"<p>{text}</p>",
			}
		).insert()

	def run_and_get_reply(self, message):
		with patch_hooks(ALLOWED_HANDLERS):
			run_slash_command(message.name)
		return frappe.get_all(
			"Raven Message",
			filters={"channel_id": message.channel_id, "is_bot_message": 1, "bot": self.bot.name},
			pluck="content",
		)

	def test_command_name_is_normalised_and_validated(self):
		self.assertEqual(self.create_command("/Test_Deploy").name, "test_deploy")
		self.assertRaises(frappe.ValidationError, self.create_command, "test deploy")

	def test_handler_must_be_declared_in_hooks(self):
		command = frappe.get_doc(
			{
				"doctype": "Raven Bot Command",
				"command": "sneaky",
				"bot": self.bot.name,
				"description": "not allowed",
				"handler": "frappe.db.sql",
			}
		)
		self.assertRaises(frappe.ValidationError, command.insert)

	def test_command_replies_with_handler_output(self):
		self.create_command("test_echo")
		self.assertEqual(
			self.run_and_get_reply(self.send("/test_echo hello world")), ["echo: hello world"]
		)

	def test_plain_and_unknown_messages_are_not_commands(self):
		self.create_command("test_echo")
		for text in ("echo hello", "/unknown hello", "see a/echo b"):
			self.assertIsNone(SlashCommand(self.send(text)).get_command(), text)

	def test_disabled_command_is_ignored(self):
		frappe.db.set_value("Raven Bot Command", self.create_command("test_echo").name, "enabled", 0)
		self.assertIsNone(SlashCommand(self.send("/test_echo hi")).get_command())

	def test_channel_restriction(self):
		self.create_command("test_echo", channels=[self.channel.name])
		self.assertIsNotNone(SlashCommand(self.send("/test_echo hi")).get_command())
		self.assertIsNone(SlashCommand(self.send("/test_echo hi", self.other_channel)).get_command())
		listed = [row["command"] for row in get_slash_commands(self.other_channel.name)]
		self.assertNotIn("test_echo", listed)

	def test_validation_error_is_sent_back_as_reply(self):
		self.create_command("test_start", handler=REFUSING_HANDLER)
		self.assertEqual(self.run_and_get_reply(self.send("/test_start")), ["box name is required"])

	def test_crashing_handler_is_logged_and_does_not_raise(self):
		self.create_command("test_crash", handler=FAILING_HANDLER)
		error_logs_before = frappe.db.count("Error Log")
		self.assertEqual(
			self.run_and_get_reply(self.send("/test_crash")),
			["Something went wrong while running /test_crash."],
		)
		self.assertEqual(frappe.db.count("Error Log"), error_logs_before + 1)

	def test_handler_removed_from_hooks_does_not_run(self):
		self.create_command("test_echo")
		run_slash_command(self.send("/test_echo hi").name)
		reply = frappe.get_all("Raven Message", filters={"bot": self.bot.name}, pluck="content")
		self.assertEqual(reply, ["/test_echo is not available right now."])

	def start_colour_flow(self):
		self.create_command("test_colour", handler=COLOUR_HANDLER)
		with patch_hooks(ALLOWED_HANDLERS):
			run_slash_command(self.send("/test_colour").name)
		return frappe.get_doc("Raven Message", {"bot": self.bot.name})

	def test_button_reply_continues_the_flow_in_place(self):
		bot_message = self.start_colour_flow()
		self.assertEqual(bot_message.content, "Pick a colour")
		self.assertIn('"value": "red"', bot_message.json)
		with patch_hooks(ALLOWED_HANDLERS):
			press_button(bot_message.name, "red")
		bot_message.reload()
		self.assertEqual(bot_message.content, "You picked red")
		self.assertFalse(bot_message.is_edited)
		self.assertIsNone(bot_message.json)
		self.assertRaises(frappe.ValidationError, press_button, bot_message.name, "blue")

	def test_only_the_command_author_can_press(self):
		bot_message = self.start_colour_flow()
		frappe.set_user("test@example.com")
		try:
			self.assertRaises(frappe.PermissionError, press_button, bot_message.name, "red")
		finally:
			frappe.set_user("Administrator")

	def test_unknown_button_value_is_rejected(self):
		bot_message = self.start_colour_flow()
		self.assertRaises(frappe.ValidationError, press_button, bot_message.name, "green")
