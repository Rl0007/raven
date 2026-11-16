# Copyright (c) 2026, Frappe and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.classes.context_managers import patch_hooks

from raven.raven_bot.slash_commands import press_button, run_slash_command

EXTRA_TEST_RECORD_DEPENDENCIES = ["User", "Raven User"]

ECHO_HANDLER = "raven.raven_bot.doctype.raven_bot_command.test_raven_bot_command.echo_handler"
ECHO_SCRIPT = """
arguments = frappe.form_dict.arguments
frappe.response["message"] = "script echo: " + arguments + " from " + frappe.session.user
"""
COLOUR_SCRIPT = """
interaction = frappe.form_dict
if interaction.pressed:
	frappe.response["message"] = interaction.state["asked"] + " " + interaction.pressed
else:
	frappe.response["message"] = {
		"text": "Pick a colour",
		"buttons": [{"label": "Red", "value": "red"}],
		"state": {"asked": "You picked"},
	}
"""


class IntegrationTestServerScriptCommand(IntegrationTestCase):
	def setUp(self):
		workspace = frappe.get_doc(
			{"doctype": "Raven Workspace", "workspace_name": "Script Command Workspace", "type": "Public"}
		).insert()
		self.channel = frappe.get_doc(
			{
				"doctype": "Raven Channel",
				"channel_name": "script-command-channel",
				"type": "Public",
				"workspace": workspace.name,
			}
		).insert()
		self.bot = frappe.get_doc({"doctype": "Raven Bot", "bot_name": "Script Command Bot"}).insert()
		self.enterContext(patch("frappe.utils.safe_exec.is_safe_exec_enabled", return_value=True))

	def tearDown(self):
		frappe.db.rollback()

	def create_script(self, name, script=ECHO_SCRIPT, script_type="API"):
		return frappe.get_doc(
			{
				"doctype": "Server Script",
				"name": name,
				"script_type": script_type,
				"api_method": name,
				"script": script,
			}
		).insert()

	def create_command(self, command, **handlers):
		return frappe.get_doc(
			{
				"doctype": "Raven Bot Command",
				"command": command,
				"bot": self.bot.name,
				"description": f"{command} command",
				**handlers,
			}
		).insert()

	def run_and_get_bot_message(self, text):
		message = frappe.get_doc(
			{
				"doctype": "Raven Message",
				"channel_id": self.channel.name,
				"message_type": "Text",
				"text": f"<p>{text}</p>",
			}
		).insert()
		run_slash_command(message.name)
		return frappe.get_doc("Raven Message", {"bot": self.bot.name})

	def test_command_replies_with_what_the_script_sets(self):
		self.create_command("test_script", server_script=self.create_script("test_script_echo").name)
		bot_message = self.run_and_get_bot_message("/test_script hello")
		self.assertEqual(bot_message.content, "script echo: hello from Administrator")

	def test_script_buttons_continue_the_flow(self):
		script = self.create_script("test_script_colour", COLOUR_SCRIPT)
		self.create_command("test_script_colour", server_script=script.name)
		bot_message = self.run_and_get_bot_message("/test_script_colour")
		self.assertEqual(bot_message.content, "Pick a colour")
		press_button(bot_message.name, "red")
		bot_message.reload()
		self.assertEqual(bot_message.content, "You picked red")

	def test_disabled_script_does_not_run(self):
		script = self.create_script("test_script_echo")
		self.create_command("test_script", server_script=script.name)
		frappe.db.set_value("Server Script", script.name, "disabled", 1)
		bot_message = self.run_and_get_bot_message("/test_script hello")
		self.assertEqual(bot_message.content, "/test_script is not available right now.")

	def test_command_needs_exactly_one_of_handler_and_script(self):
		script = self.create_script("test_script_echo")
		self.assertRaises(frappe.ValidationError, self.create_command, "test_neither")
		with patch_hooks({"raven_slash_command_handlers": [ECHO_HANDLER]}):
			self.assertRaises(
				frappe.ValidationError,
				self.create_command,
				"test_both",
				handler=ECHO_HANDLER,
				server_script=script.name,
			)

	def test_script_must_be_an_api_script(self):
		script = frappe.get_doc(
			{
				"doctype": "Server Script",
				"name": "test_script_scheduled",
				"script_type": "Scheduler Event",
				"event_frequency": "Daily",
				"script": "pass",
			}
		).insert()
		self.assertRaises(
			frappe.ValidationError, self.create_command, "test_scheduled", server_script=script.name
		)
